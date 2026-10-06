# -*- coding: utf-8 -*-
"""
Extract selected ResSim results from a simulation.dss into CSV files, one CSV
per group (reservoirs, limits, junctions, diversions).

Runs on a DESKTOP Python 3 with pydsstools and pandas (the hydro39 conda
environment), not inside ResSim. Paste the path to simulation.dss into DSS_PATH
below, then:
    conda activate hydro39
    python data/scripts/_migration/extract_dss.py

A path given on the command line overrides DSS_PATH.

For each group it writes, next to the DSS file:
    <group>.csv          Date, then one column per series, named "<B> <C>"
    <group>_series.csv   one row per column: its full pathname and units

Records are chosen by the rules in SELECTIONS, matched against every pathname
in the file, so a new reservoir or junction is picked up without editing this
script. Run catalog_dss.py to see what a file holds.
"""

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

# Each group becomes one CSV. Each rule selects series by:
#   b             regular expression the whole B part must match
#   c             list of C parts to take
#   only_if_has   (optional) take a B only if it also has this C part
#   pool_exists   (optional) take a B only if "<B>-Pool" exists, i.e. B is a reservoir
SELECTIONS = OrderedDict([
    ("reservoirs", [
        {"b": r".+-Pool", "c": ["Flow-IN", "Flow-OUT", "Elev"]},
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
            for c in rule["c"]:
                if c in cByB[b] and (b, c) not in chosen:
                    chosen.append((b, c))
    return chosen


def readSeries(fid, blockPaths):
    """Read every date block of one series into a pandas Series, and its units."""
    pieces = []
    units = ""
    for path in sorted(blockPaths):
        ts = fid.read_ts(path, trim_missing=True)
        values = np.array(ts.values, dtype=float)
        values[values < MISSING_BELOW] = np.nan
        nodata = getattr(ts, "nodata", None)
        if nodata is not None and len(nodata) == len(values):
            values[np.array(nodata, dtype=bool)] = np.nan
        pieces.append(pd.Series(values, index=pd.to_datetime(list(ts.pytimes))))
        units = units or getattr(ts, "units", "") or ""
    if not pieces:
        return pd.Series(dtype=float), units
    data = pd.concat(pieces)
    data = data[~data.index.duplicated(keep="last")].sort_index()
    return data, units


def _asDates(index):
    """Relabel 24:00 daily stamps (reported as next-day 00:00) as the day itself."""
    if len(index) and (index.hour == 0).all() and (index.minute == 0).all():
        return (index - pd.Timedelta(days=1)).date
    return index


def main():
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
    outDir = os.path.dirname(os.path.abspath(dssPath))

    fid = HecDss.Open(dssPath)
    try:
        pathnames = fid.getPathnameList("/*/*/*/*/*/*/", sort=1)
        fPart = F_PART or mostCommonF(pathnames)
        series = groupByseries(pathnames, fPart)
        print("F part %s: %d series in %s" % (fPart, len(series), dssPath))

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


if __name__ == "__main__":
    main()
