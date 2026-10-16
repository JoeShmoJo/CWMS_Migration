# -*- coding: utf-8 -*-
"""
Extract selected ResSim results from a simulation.dss into CSV files, one CSV
per group (reservoirs, limits, junctions, diversions, rules).

Runs on a DESKTOP Python 3 with pydsstools and pandas (the hydro39 conda
environment), not inside ResSim. Paste the path to simulation.dss into DSS_PATH
below, then:
    conda activate hydro39
    python model_check/extract_dss.py

A path given on the command line overrides DSS_PATH.

Output goes to model_check/output/<simulation>_<alternative>_<date>/, e.g.
output/Script_Cleanup_Test_Temp1Day_2026-09-25/. For each group it writes:
    <group>.csv          Date, then one column per series, named "<B> <C>"
    <group>_series.csv   one row per column: its full pathname and units
and run_info.json, which check_model.py reads to find the alternative's configs.

Records are chosen by the rules in SELECTIONS, matched against every pathname
in the file, so a new reservoir or junction is picked up without editing this
script. Run catalog_dss.py to see what a file holds.
"""

import datetime
import glob
import shutil
import json
import os
import re
import sys
from collections import OrderedDict

import numpy as np
import pandas as pd
from pydsstools.heclib.dss import HecDss

################################################################################
# USER INPUT

# Paste the full path to simulation.dss between the quotes. Keep the r in front:
# it stops Python reading the backslashes in a Windows path as escape codes.
DSS_PATH = r""

# The F part of the simulation's own results, e.g. "Temp1Day--0". Leave blank
# to use the most common F part in the file, which is the simulation's output
# when it holds one alternative. Inputs and observed data use other F parts.
F_PART = ""

# ResSim stamps a daily value at 24:00, which pydsstools reports as 00:00 on
# the NEXT day. True labels each row with the day the value belongs to.
# Check the first row against ResSim after changing this.
DAILY_AS_DATE = True

# Where the output folders go. Blank means model_check/output next to this
# script (or the current folder, when run somewhere that cannot tell).
OUTPUT_ROOT = r""

# Where to look for modelReport_<alternative>.json (the rule stack), relative
# to the simulation folder, in order: the watershed's rss folder, then the
# simulation folder itself
MODEL_REPORT_DIRS = ["..", "."]

# Each group becomes one CSV. Each rule selects series by:
#   b             regular expression the whole B part must match
#   c             list of C parts to take
#   only_if_has   (optional) take a B only if it also has this C part
#   pool_exists   (optional) take a B only if "<B>-Pool" exists, i.e. B is a reservoir
#   rule_of_reservoir (optional) take a B only if it is "<reservoir>-<rule>"
#   exclude       (optional) regular expression; a B that contains a match is skipped
SELECTIONS = OrderedDict([
    ("reservoirs", [
        {"b": r".+-Pool", "c": ["Flow-IN", "Flow-OUT", "Elev"]},
        # The top of each zone ("<reservoir>-<zone>"), to tell which zone the
        # pool was in and so which rule stack applied
        {"b": r".+", "c": ["Elev-ZONE"], "rule_of_reservoir": True},
    ]),
    # The combined min and max limit ResSim applied at each reservoir, each
    # step, plus the mainstem minimum flow targets
    ("limits", [
        {"b": r".+", "c": ["Flow-MINLIM", "Flow-MAXLIM"], "pool_exists": True},
        {"b": r"Min_Flow_Target_.+", "c": ["Flow-Min"]},
    ]),
    # Control points with a local flow defined
    ("junctions", [
        {"b": r".+", "c": ["Flow-Local", "Flow-CUMLOC", "Flow"],
         "only_if_has": "Flow-Local"},
    ]),
    # What each diversion actually moved, and what DiversionFromCSV asked for
    # (its rule is named after the element, so the B part is "<name>-<name>")
    ("diversions", [
        {"b": r"(?:Diversion|Return) \d+(?: up| down)?", "c": ["Flow-DECISION"]},
        {"b": r"((?:Diversion|Return) \d+(?: up| down)?)-\1", "c": ["Flow-SPEC"]},
    ]),
    # The value every reservoir rule returned each step. A scripted rule is
    # saved as Flow-SPEC whatever type it returned; built-in rules as
    # Flow-MIN or Flow-MAX. "<zone>-ZBOp Rule" is the release the zone's guide
    # curve asks for; the inactive zone's and the [DUMMY] setup rules are left out.
    ("rules", [
        {"b": r".+", "c": ["Flow-SPEC", "Flow-MIN", "Flow-MAX"],
         "rule_of_reservoir": True, "exclude": r"Inactive-ZBOp Rule|\[DUMMY\]"},
    ]),
])

################################################################################
# FUNCTION DEFINITIONS

# DSS stores a missing value as about -3.4e38
MISSING_BELOW = -1.0e37


def _splitPath(pathname):
    """'/A/B/C/D/E/F/' -> (A, B, C, D, E, F), or None if it is not six parts."""
    parts = pathname.split("/")
    if len(parts) != 8:
        return None
    return tuple(parts[1:7])


def groupByseries(pathnames, fPart):
    """
    {(B, C): [full pathnames, one per date block]} for the given F part.
    Only B and C are kept as the key: within one F part they name a series.
    """
    series = OrderedDict()
    for pathname in pathnames:
        parts = _splitPath(pathname)
        if parts is None or parts[5] != fPart:
            continue
        key = (parts[1], parts[2])
        series.setdefault(key, []).append(pathname)
    return series


def mostCommonF(pathnames):
    counts = {}
    for pathname in pathnames:
        parts = _splitPath(pathname)
        if parts is not None:
            counts[parts[5]] = counts.get(parts[5], 0) + 1
    if not counts:
        return ""
    return max(counts, key=counts.get)


def _naturalKey(text):
    """Sort "Diversion 2" before "Diversion 10"."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text)]


def _isReservoirRule(b, cByB):
    """True for "<reservoir>-<rule>", where "<reservoir>-Pool" exists."""
    if "-" not in b or b.endswith("-Pool"):
        return False
    return (b.split("-", 1)[0] + "-Pool") in cByB


def _outputRoot():
    if OUTPUT_ROOT:
        return OUTPUT_ROOT
    here = globals().get("__file__")
    if here:
        return os.path.join(os.path.dirname(os.path.abspath(here)), "output")
    return os.path.join(os.getcwd(), "output")


def alternativeName(fPart):
    """ResSim's F part is the alternative plus a run suffix: "Temp1Day--0" -> "Temp1Day"."""
    return re.sub(r"-+\d*$", "", fPart) or fPart


def selectSeries(seriesKeys, rules):
    """The (B, C) keys the rules pick, in a stable order: by B, then rule C order."""
    cByB = {}
    for b, c in seriesKeys:
        cByB.setdefault(b, set()).add(c)
    chosen = []
    for rule in rules:
        pattern = re.compile(rule["b"])
        for b in sorted(cByB, key=_naturalKey):
            if not pattern.fullmatch(b):
                continue
            if "only_if_has" in rule and rule["only_if_has"] not in cByB[b]:
                continue
            if rule.get("pool_exists") and (b + "-Pool") not in cByB:
                continue
            if rule.get("rule_of_reservoir") and not _isReservoirRule(b, cByB):
                continue
            if "exclude" in rule and re.search(rule["exclude"], b):
                continue
            for c in rule["c"]:
                if c in cByB[b] and (b, c) not in chosen:
                    chosen.append((b, c))
    return chosen


def readSeries(fid, blockPaths):
    """
    Read every date block of one series into a pandas Series, and its units.
    A block with no values at all is skipped: with trim_missing, pydsstools
    trims it to nothing and returns None for its times. A block that fails to
    read is reported and skipped rather than stopping the whole extract.
    """
    pieces = []
    units = ""
    for path in sorted(blockPaths):
        try:
            ts = fid.read_ts(path, trim_missing=True)
        except Exception as e:
            print("    could not read %s: %s" % (path, e))
            continue
        if ts is None or ts.pytimes is None or ts.values is None:
            continue
        times = list(ts.pytimes)
        if not times:
            continue
        values = np.array(ts.values, dtype=float)
        values[values < MISSING_BELOW] = np.nan
        nodata = getattr(ts, "nodata", None)
        if nodata is not None and len(nodata) == len(values):
            values[np.array(nodata, dtype=bool)] = np.nan
        pieces.append(pd.Series(values, index=pd.to_datetime(times)))
        units = units or getattr(ts, "units", "") or ""
    if not pieces:
        # A date index even when empty, or concat can turn the whole table's
        # index into a plain Index on some pandas versions
        return pd.Series(dtype=float, index=pd.DatetimeIndex([])), units
    data = pd.concat(pieces)
    data = data[~data.index.duplicated(keep="last")].sort_index()
    return data, units


def _asDates(index):
    """Relabel 24:00 daily stamps (reported as next-day 00:00) as the day itself."""
    index = pd.DatetimeIndex(pd.to_datetime(index))
    if len(index) and (index.hour == 0).all() and (index.minute == 0).all():
        return (index - pd.Timedelta(days=1)).date
    return index


def fPartFor(pathnames, alternative):
    """The F part of an alternative's results: the most common one that starts with its name."""
    counts = {}
    for p in pathnames:
        parts = _splitPath(p)
        if parts and parts[5].lower().startswith(alternative.lower()):
            counts[parts[5]] = counts.get(parts[5], 0) + 1
    if not counts:
        found = sorted(set(_splitPath(p)[5] for p in pathnames if _splitPath(p)))
        sys.exit("No results for alternative %r in this DSS file. F parts found:\n  %s"
                 % (alternative, "\n  ".join(found[:40])))
    return max(counts, key=counts.get)


def copyModelReport(simDir, alternative, outDir):
    """
    Alternative_Setup writes modelReport_<alternative>.json on every compute:
    the active operation set's rules, zone by zone, in stack order. Look for
    it in MODEL_REPORT_DIRS (relative to the simulation folder) and copy it
    along as modelReport.json. A watershed without it just gets no rule stack.
    """
    for rel in MODEL_REPORT_DIRS:
        folder = os.path.normpath(os.path.join(simDir, rel))
        exact = os.path.join(folder, "modelReport_%s.json" % alternative)
        reports = glob.glob(os.path.join(folder, "modelReport_*.json"))
        source = exact if os.path.isfile(exact) else (reports[0] if len(reports) == 1 else None)
        if source:
            try:
                shutil.copyfile(source, os.path.join(outDir, "modelReport.json"))
                print("Rule stack from %s" % source)
            except (IOError, OSError) as e:
                print("Could not copy %s (%s): the rule stack will not be shown" % (source, e))
            return
    print("No modelReport_%s.json found (looked in %s): the rule stack will not be shown"
          % (alternative, ", ".join(os.path.normpath(os.path.join(simDir, r)) for r in MODEL_REPORT_DIRS)))


def main(dssPath=None, alternative=None):
    """
    Extract one alternative's results to CSV and return the output folder.
    run_model_check.py passes dssPath and alternative; otherwise DSS_PATH or
    the command line, and F_PART or the most common F part.
    """
    if dssPath is None:
        dssPath = DSS_PATH
        # Jupyter and VS Code's interactive window pass their own "--f=kernel.json"
        # argument, so only a bare argument counts as a path
        args = [a for a in sys.argv[1:] if not a.startswith("-")]
        if args:
            dssPath = args[0]
    dssPath = dssPath.strip().strip('"')
    if not dssPath:
        sys.exit("No DSS file given. Paste the path to simulation.dss into "
                 "DSS_PATH at the top of extract_dss.py, or pass it on the "
                 "command line.")
    if not os.path.isfile(dssPath):
        sys.exit("DSS file not found: %s" % dssPath)
    dssPath = os.path.abspath(dssPath)
    simDir = os.path.dirname(dssPath)
    simulation = os.path.basename(simDir)

    fid = HecDss.Open(dssPath)
    try:
        pathnames = fid.getPathnameList("/*/*/*/*/*/*/", sort=1)
        if alternative:
            fPart = fPartFor(pathnames, alternative)
        else:
            fPart = F_PART or mostCommonF(pathnames)
        series = groupByseries(pathnames, fPart)
        print("F part %s: %d series in %s" % (fPart, len(series), dssPath))

        alternative = alternative or alternativeName(fPart)
        today = datetime.date.today().isoformat()
        outDir = os.path.join(_outputRoot(), "%s_%s_%s" % (simulation, alternative, today))
        if not os.path.isdir(outDir):
            os.makedirs(outDir)
        # The watershed is two folders above rss/<simulation>/simulation.dss
        runInfo = {"dss_path": dssPath, "simulation": simulation,
                   "alternative": alternative, "f_part": fPart,
                   "watershed_dir": os.path.dirname(os.path.dirname(simDir)),
                   "extracted": today}
        with open(os.path.join(outDir, "run_info.json"), "w") as fh:
            json.dump(runInfo, fh, indent=2)
        print("Writing to %s" % outDir)

        for group, rules in SELECTIONS.items():
            chosen = selectSeries(series.keys(), rules)
            if not chosen:
                print("%-11s nothing matched, no file written" % group)
                continue
            columns = OrderedDict()
            info = []
            for b, c in chosen:
                name = "%s %s" % (b, c)
                data, units = readSeries(fid, series[(b, c)])
                columns[name] = data
                if data.empty:
                    print("    no values: %s" % name)
                info.append({"column": name, "B": b, "C": c, "units": units,
                             "n_values": int(data.notna().sum()),
                             "example_path": series[(b, c)][0]})
            table = pd.concat(columns, axis=1).sort_index()
            if DAILY_AS_DATE:
                table.index = _asDates(table.index)
            table.index.name = "Date"

            outPath = os.path.join(outDir, "%s.csv" % group)
            table.to_csv(outPath)
            pd.DataFrame(info).to_csv(
                os.path.join(outDir, "%s_series.csv" % group), index=False)
            print("%-11s %4d columns x %6d rows  %6.1f MB  %s"
                  % (group, table.shape[1], table.shape[0],
                     os.path.getsize(outPath) / 1e6, outPath))
    finally:
        fid.close()
    copyModelReport(simDir, alternative, outDir)
    return outDir


if __name__ == "__main__":
    main()
