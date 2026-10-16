# -*- coding: utf-8 -*-
"""
Diagnostics for one ResSim run: compare what the model did against the config
CSVs its scripted rules read, and plot it.

Runs on a DESKTOP Python 3 with pandas and plotly (the hydro39 conda
environment), after extract_dss.py has written an output folder:
    conda activate hydro39
    python model_check/check_model.py

It checks the newest folder in model_check/output unless RUN_DIR says otherwise,
and writes into that folder:
    report.html               summary tables for every check, with links to plots
    <check>_summary.csv       one row per reservoir, diversion or rule
    release_decisions/<reservoir>.csv
                              per day: elevation, inflow, outflow, min and max
                              limit, and the value every rule asked for
    plots/Reservoir - <name>.html
                              one page per reservoir, three panels: elevation, rule curve
                              and FIRO target; outflow, limits and every rule's
                              value; and each rule's status every day (in control,
                              capped, held up, or set by another rule). The release
                              decision table sits under the plot, cells shaded by
                              status: click a day to find its row, click a row to
                              mark the day. Only outflow and the limits start
                              shown on the flow panel; the legend turns on the rest.
                              "Open table in its own window" moves the table to a
                              window of its own, e.g. on a second screen.
    plots/Control points.html every control point's flow against its limits, a
                              status bar each (in range, above max, below min),
                              and a daily table of upstream releases and the
                              rules in control, linked like the reservoir pages
    Pick an element from the dropdown; click legend entries to hide or show them.

The checks:

FIRO_SPACE   Is the pool at the FIRO_SPACE elevation (achieving), and did the
             outflow follow the FIRO rule (targeting)? A day off target is
             "explained" when the outflow was pinned at the reservoir's min
             limit (it could not release less, so it could not fill) or at its
             max limit (it could not release more, so it could not draft).
MinFlow      Did MinFlowPlusWithdrawal ask for minimum flow + withdrawal from
             the config, and was it released? A shortfall is "explained" when
             the reservoir's max limit was below the requirement that day.
Diversions   Did DiversionFromCSV write the config value to its rule?
RuleControl  How many days each rule's value equalled the outflow (needs rules.csv)
Conflicts    Rules that wanted a different release, and the rule or outlet capacity
             that stopped them (needs rules.csv). See decideReleases.

The config files are the ones the run's alternative points at in
scripts/alt_config/ (<alternative>.txt over _default.txt), read from the
watershed if it is on this machine, otherwise from this repository.
"""

import glob
import json
import os
import re
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

################################################################################
# USER INPUT

# An output folder written by extract_dss.py. Blank means the newest one.
RUN_DIR = r""

# The folder holding scripts/ (a watershed, or this repo's data folder). Blank
# means the watershed recorded in run_info.json if it exists on this machine,
# otherwise this repository's data folder.
CONFIG_ROOT = r""

# First date to check. Blank means the first day with diversion results, which
# skips ResSim's lookback days at the start of the file.
START_DATE = ""
# Last date to check. Blank means the end of the run. With START_DATE, looks at
# part of a long run, which keeps the plot pages small.
END_DATE = ""

# Tolerances for calling two numbers the same
ELEV_TOL_FT = 1.0          # pool vs FIRO_SPACE target
FLOW_TOL_CFS = 5.0         # flows: this many cfs, or FLOW_TOL_FRAC, whichever is larger
FLOW_TOL_FRAC = 0.02
RULE_TOL_CFS = 0.5         # a rule's own output vs the config it read

FIRO_RULE_NAME = "FIRO_SPACE"

# The rule name MinFlowPlusWithdrawal has in the model, and reservoirs whose
# requirement is met at a downstream project (as TARGET_MET_AT in the script)
MINFLOW_RULE_NAME = "Combined Min Trib"
MINFLOW_TARGET_MET_AT = {"Green Peter": "Foster"}
# Other min-flow rules worth comparing to the same config, by name fragment
MINFLOW_OTHER_RULE_PATTERN = "MinTrib"

# Headroom check (optional; run_headroom in model_check_config.txt): on steps a
# reservoir is held back by a control point's max rule and is above its rule
# curve, how far the point's flow stayed under its maximum once that release
# arrived. Writes CSVs only.
HEADROOM = False
HEADROOM_LAG_STEPS = 1       # steps for a release to reach the control point
HEADROOM_MIN_CFS = 250.0     # room below this is not counted

# Flood flows at the control points (Table 2), next to this script
CONTROL_POINT_LIMITS = "control_point_limits.csv"

# A max limit at or above this is "no limit" (ResSim reports outlet capacity)
NO_LIMIT_CFS = 1.0e5

CFS_DAY_TO_AF = 86400.0 / 43560.0

# Length of the run's time step in days, set from the data in main(). Counts
# of steps become days with it, and flows become volumes.
STEP_DAYS = 1.0

################################################################################
# LOADING


def _here():
    here = globals().get("__file__")
    return os.path.dirname(os.path.abspath(here)) if here else os.getcwd()


def findRunDir():
    if RUN_DIR:
        return RUN_DIR
    runs = [d for d in glob.glob(os.path.join(_here(), "output", "*"))
            if os.path.isfile(os.path.join(d, "run_info.json"))]
    if not runs:
        sys.exit("No output folder with run_info.json under %s. Run "
                 "extract_dss.py first, or set RUN_DIR."
                 % os.path.join(_here(), "output"))
    return max(runs, key=os.path.getmtime)


def findConfigRoot(runInfo):
    if CONFIG_ROOT:
        return CONFIG_ROOT
    watershed = runInfo.get("watershed_dir", "")
    if watershed and os.path.isdir(os.path.join(watershed, "scripts")):
        return watershed
    # model_check sits in the repo root (configs under data/scripts) or was
    # copied into a watershed's scripts folder (configs under scripts)
    folder = _here()
    for _ in range(4):
        folder = os.path.dirname(folder)
        for root in (folder, os.path.join(folder, "data")):
            if os.path.isdir(os.path.join(root, "scripts", "alt_config")):
                return root
    sys.exit("Could not find scripts/alt_config above %s. Set CONFIG_ROOT to "
             "the folder that contains scripts." % _here())


def loadGroups(runDir):
    """{group: DataFrame indexed by date} for every CSV extract_dss.py wrote."""
    groups = {}
    for name in ("reservoirs", "limits", "junctions", "diversions", "rules"):
        path = os.path.join(runDir, name + ".csv")
        if os.path.isfile(path):
            groups[name] = pd.read_csv(path, index_col=0, parse_dates=True)
    return groups


def readAltConfig(configRoot, alternative):
    """alt_config keys: _default.txt, overridden by <alternative>.txt."""
    values = {}
    for name in ("_default.txt", "%s.txt" % alternative):
        path = os.path.join(configRoot, "scripts", "alt_config", name)
        if not os.path.isfile(path):
            continue
        for line in open(path):
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def configPath(configRoot, altConfig, key, default):
    rel = altConfig.get(key, default)
    return os.path.join(configRoot, *rel.replace("\\", "/").split("/"))


def _norm(name):
    return re.sub(r"\s+", " ", str(name)).strip().lower()


def readDailyConfig(path):
    """A generic-year Month,Day,<element>... CSV, as {normalized name: (name, Series)}."""
    table = pd.read_csv(path, comment="#", skipinitialspace=True)
    table.columns = [str(c).strip() for c in table.columns]
    table = table.set_index(["Month", "Day"])
    out = {}
    for column in table.columns:
        if _norm(column) in ("notes", ""):
            continue
        out[_norm(column)] = (column, pd.to_numeric(table[column], errors="coerce"))
    return out


def onDates(configSeries, dates):
    """Look a generic-year series up for real dates. 29 Feb uses 28 Feb."""
    keys = [(d.month, 28 if (d.month == 2 and d.day == 29) else d.day) for d in dates]
    return pd.Series(configSeries.reindex(keys).values, index=dates, dtype=float)


def onDatesInterpolated(configSeries, dates):
    """
    Like onDates, but a sub-daily step interpolates between the previous day's
    value and today's by the time of day, as FIRO_SPACE.py does: each day's
    value holds at the end of the day. Results stamp 2400 as the next day's
    00:00, which is the previous day's value. Daily steps are unchanged.
    """
    if STEP_DAYS >= 1.0:
        return onDates(configSeries, dates)
    today = onDates(configSeries, dates)
    yesterday = onDates(configSeries, dates - pd.Timedelta(days=1))
    yesterday.index = dates
    frac = pd.Series((dates.hour * 60 + dates.minute) / 1440.0, index=dates)
    out = yesterday + (today - yesterday) * frac
    # 00:00 is the end of the previous day
    out[frac == 0] = yesterday[frac == 0]
    return out.where(today.notna() & yesterday.notna(), today)


def col(groups, group, name):
    """A column from an extract group, or None."""
    table = groups.get(group)
    if table is None or name not in table.columns:
        return None
    return table[name]


def flowTol(values):
    return np.maximum(FLOW_TOL_CFS, FLOW_TOL_FRAC * np.abs(values))


def _days(steps):
    """A count of time steps (a boolean Series, or a number) in days."""
    n = float(steps.sum() if hasattr(steps, "sum") else steps) * STEP_DAYS
    return int(round(n)) if STEP_DAYS == 1.0 else round(n, 2)


def _pct(part, whole):
    return round(100.0 * part / whole, 1) if whole else np.nan


################################################################################
# CHECKS


def checkFiro(groups, configFile, dates):
    """One summary row per reservoir in the config, and its traces for the reservoir plot."""
    rows, plots = [], {}
    for key, (name, cfg) in sorted(readDailyConfig(configFile).items()):
        target = onDatesInterpolated(cfg, dates)
        elev = col(groups, "reservoirs", "%s-Pool Elev" % name)
        if target.notna().sum() == 0 or elev is None:
            continue
        elev = elev.reindex(dates)
        out = col(groups, "reservoirs", "%s-Pool Flow-OUT" % name).reindex(dates)
        minLim = col(groups, "limits", "%s Flow-MINLIM" % name).reindex(dates)
        maxLim = col(groups, "limits", "%s Flow-MAXLIM" % name).reindex(dates)
        ruleVal = col(groups, "rules", "%s-%s Flow-SPEC" % (name, FIRO_RULE_NAME))

        ok = target.notna() & elev.notna()
        dev = elev - target
        above = ok & (dev > ELEV_TOL_FT)
        below = ok & (dev < -ELEV_TOL_FT)
        atMax = out >= maxLim - flowTol(maxLim)
        atMin = out <= minLim + flowTol(minLim)
        row = {
            "reservoir": name,
            "days_with_target": _days(ok),
            "within_%.1fft_pct" % ELEV_TOL_FT: _pct((ok & ~above & ~below).sum(), ok.sum()),
            "mean_dev_ft": round(dev[ok].mean(), 2),
            "max_above_ft": round(dev[ok].max(), 2),
            "max_below_ft": round(dev[ok].min(), 2),
            "days_above": _days(above),
            "above_at_max_limit": _days((above & atMax)),
            "above_unexplained": _days((above & ~atMax)),
            "days_below": _days(below),
            "below_at_min_limit": _days((below & atMin)),
            "below_unexplained": _days((below & ~atMin)),
        }

        if "rules" not in groups:
            row["rule_attached"] = "unknown (no rules.csv)"
        elif ruleVal is None:
            row["rule_attached"] = "no"
        else:
            row["rule_attached"] = "yes"
            ruleVal = ruleVal.reindex(dates)
            # FIRO_SPACE.py always returns a MAX: followed when the outflow
            # did not exceed it
            active = ok & ruleVal.notna()
            followed = (out <= ruleVal + flowTol(ruleVal)) & active
            row["rule_followed_pct"] = _pct(followed.sum(), active.sum())
            row["rule_overridden_days"] = _days((active & ~followed))
        rows.append(row)

        plots[name] = [
            ("FIRO_SPACE target", target, "y1", {"color": "#d62728", "group": "elev"}),
        ]
    return pd.DataFrame(rows), plots


def checkMinFlow(groups, minFlowFile, withdrawalFile, dates):
    minFlow = readDailyConfig(minFlowFile)
    withdrawal = readDailyConfig(withdrawalFile)
    rows, plots = [], {}
    for key in sorted(set(minFlow) | set(withdrawal)):
        name = (minFlow.get(key) or withdrawal.get(key))[0]
        mf = onDates(minFlow[key][1], dates) if key in minFlow else pd.Series(np.nan, index=dates)
        wd = onDates(withdrawal[key][1], dates) if key in withdrawal else pd.Series(np.nan, index=dates)
        # As the rule does: blank in one file is zero, blank in both is no requirement
        required = mf.fillna(0) + wd.fillna(0)
        required[mf.isna() & wd.isna()] = np.nan
        if required.notna().sum() == 0:
            continue

        releasedAt = MINFLOW_TARGET_MET_AT.get(name, name)
        out = col(groups, "reservoirs", "%s-Pool Flow-OUT" % releasedAt)
        if out is None:
            continue
        out = out.reindex(dates)
        maxLim = col(groups, "limits", "%s Flow-MAXLIM" % releasedAt).reindex(dates)
        minLim = col(groups, "limits", "%s Flow-MINLIM" % releasedAt).reindex(dates)
        ruleVal = col(groups, "rules", "%s-%s Flow-SPEC" % (name, MINFLOW_RULE_NAME))

        req = required.notna() & out.notna()
        short = req & (out < required - flowTol(required))
        maxBelow = maxLim < required - flowTol(required)
        row = {
            "reservoir": name,
            "released_at": releasedAt,
            "days_with_requirement": _days(req),
            "mean_required_cfs": round(required[req].mean(), 1),
            "days_short": _days(short),
            "short_max_limit_below": _days((short & maxBelow)),
            "short_unexplained": _days((short & ~maxBelow)),
            "shortfall_af": round(((required - out).clip(lower=0)[short]).sum() * CFS_DAY_TO_AF * STEP_DAYS, 0),
        }
        # The min limit only reflects this requirement where it is released
        if releasedAt == name:
            row["min_limit_below_required_days"] = int(
                (req & (minLim < required - flowTol(required))).sum())
        else:
            row["min_limit_below_required_days"] = "n/a (via %s)" % releasedAt
        if "rules" not in groups:
            row["rule_attached"] = "unknown (no rules.csv)"
        elif ruleVal is None:
            row["rule_attached"] = "no"
        else:
            row["rule_attached"] = "yes"
            ruleVal = ruleVal.reindex(dates)
            if releasedAt == name:
                both = req & ruleVal.notna()
                matches = both & ((ruleVal - required).abs() <= RULE_TOL_CFS)
                row["rule_matches_config_pct"] = _pct(matches.sum(), both.sum())
            else:
                # The rule backs its release out of a mass balance downstream,
                # so its own value is not the config number
                row["rule_matches_config_pct"] = "n/a (via %s)" % releasedAt

        # Any other min-flow rule on this reservoir, compared to the same numbers
        other = [c for c in groups.get("rules", pd.DataFrame()).columns
                 if c.startswith(name + "-") and MINFLOW_OTHER_RULE_PATTERN in c]
        for c in other:
            both = req & groups["rules"][c].reindex(dates).notna()
            matches = both & ((groups["rules"][c].reindex(dates) - required).abs() <= RULE_TOL_CFS)
            row["other_rule"] = c
            row["other_rule_matches_config_pct"] = _pct(matches.sum(), both.sum())
        rows.append(row)

    # Nothing for the plots: where the rule is attached its value (Combined Min
    # Trib) is the config, as rule_matches_config_pct checks, so a config line
    # would only repeat it
    return pd.DataFrame(rows), plots


def checkDiversions(groups, configFile, dates):
    """Did DiversionFromCSV write the config value to its rule each day?"""
    rows = []
    for key, (name, cfg) in readDailyConfig(configFile).items():
        expected = onDates(cfg, dates).fillna(0.0)    # blank is no diversion
        spec = col(groups, "diversions", "%s-%s Flow-SPEC" % (name, name))
        if spec is None:
            rows.append({"element": name, "rule_in_results": "no"})
            continue
        spec = spec.reindex(dates)
        ok = spec.notna()
        diff = (spec - expected).abs()[ok]
        rows.append({"element": name, "rule_in_results": "yes",
                     "days": _days(ok),
                     "matches_config_pct": _pct((diff <= RULE_TOL_CFS).sum(), ok.sum()),
                     "days_different": _days((diff > RULE_TOL_CFS)),
                     "max_difference_cfs": round(diff.max(), 1) if len(diff) else np.nan})
    order = {n: i for i, n in enumerate(sorted(
        [r["element"] for r in rows],
        key=lambda t: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", t)]))}
    table = pd.DataFrame(rows)
    if len(table):
        table = table.sort_values("element", key=lambda s: s.map(order))
    return table, {}


################################################################################
# RESERVOIR AND CONTROL POINT PLOTS

# Rules are coloured by what ResSim saved them as: built-in MIN and MAX rules,
# scripted rules (saved as SPEC whatever type they returned), and the release
# each zone's guide curve asks for ("<zone>-ZBOp Rule", also SPEC)
RULE_KINDS = [
    ("Flow-MIN", "min", "Min rules",
     ["#1f77b4", "#17becf", "#2ca02c", "#6baed6", "#31a354", "#3182bd", "#74c476", "#08519c"]),
    ("Flow-MAX", "max", "Max rules",
     ["#d62728", "#ff7f0e", "#8c564b", "#e377c2", "#fd8d3c", "#843c39", "#e6550d", "#ad494a"]),
    ("Flow-SPEC", "script", "Scripted rules",
     ["#9467bd", "#bcbd22", "#7b4173", "#637939", "#ce6dbd", "#8c6d31", "#a55194", "#b5cf6b"]),
    (None, "guide", "Guide curve release", ["#444444", "#888888"]),
    (None, "none", "In the stack, no results", ["#bbbbbb"]),
]
LEGEND_GROUPS = {"elev": "Elevation (ft)", "flow": "Flow (cfs)", "config": "Config",
                 "min": "Min rules", "max": "Max rules", "script": "Scripted rules",
                 "guide": "Guide curve release", "none": "In the stack, no results",
                 "decision": "Release decisions"}

# How each rule stood against the release that day, in the decisions panel
STATUS_STYLE = [
    ("in control", "In control", "#2ca02c"),
    ("capped", "Wanted more, capped", "#d62728"),
    ("held up", "Wanted less, held up", "#1f77b4"),
    ("set by other", "Release set by another rule", "#aaaaaa"),
]


def reservoirNames(groups):
    return [c[:-len("-Pool Elev")] for c in groups["reservoirs"].columns
            if c.endswith("-Pool Elev")]


def reservoirRules(groups, name, dates):
    """
    [(label, kind, Series)] for every rule at a reservoir. With the model
    report, the rules are the ones in the operation set's stack, top first
    (the zone the pool spent longest in, then rules only in other zones), each
    with its values from the results, empty if it never returned one. A rule
    left in the DSS from an earlier run but no longer in the stack is left out.
    Without the report, every rule in the results that has values.
    """
    table = groups.get("rules")
    found = []
    if table is not None:
        for suffix, kind, _, _ in RULE_KINDS:
            if suffix is None:
                continue
            for c in table.columns:
                if c.startswith(name + "-") and c.endswith(" " + suffix):
                    values = table[c].reindex(dates)
                    label = c[len(name) + 1:-len(suffix) - 1]
                    zone = re.match(r"%s-(.+)-ZBOp Rule$" % re.escape(name), label)
                    if zone:
                        found.append(("Guide release, %s zone" % zone.group(1), "guide", values))
                    else:
                        found.append((label, kind, values))
    zones = groups.get("stack", {}).get(name)
    if zones:
        rulesIn = dict(zones)
        out, seen = [], set()
        for zone in zoneOrder(groups, name, dates):
            for rule in rulesIn.get(zone, []):
                if rule in seen:
                    continue
                seen.add(rule)
                # Results name some rules with their outlet ("Dam-Max
                # Evacuation Release"); the stack does not
                match = [f for f in found if f[1] != "guide" and (f[0] == rule or f[0].endswith("-" + rule))]
                out.append(match[0] if match else (rule, "none", pd.Series(np.nan, index=dates)))
        # Guide releases last, as what the reservoir does when no rule acts
        out += [f for f in found if f[1] == "guide" and f[2].notna().any()]
        return out
    out = [f for f in found if f[2].notna().any()]
    # Guide releases first: what the reservoir does when nothing else acts
    return sorted(out, key=lambda r: r[1] != "guide")


def loadStack(runDir):
    """
    {reservoir: [(zone, [rules top first])]} from the modelReport JSON that
    Alternative_Setup writes next to simulation.dss on every compute, and
    extract_dss.py copies into the output folder. Zones run bottom up. The
    "<zone>-ZBOp Rule" guide rules and [DUMMY] setup rules are left out.
    """
    path = os.path.join(runDir, "modelReport.json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        report = json.load(fh)
    stack = {}
    for resv in report.get("operations", []):
        zones = []
        for zone in resv.get("zones", []):
            rules = [r for r in zone.get("rules", [])
                     if not r.endswith("-ZBOp Rule") and not r.startswith("[DUMMY]")]
            zones.append((zone.get("zone_name", ""), rules))
        stack[resv.get("reservoir", "")] = zones
    return stack


def stackPosition(zones, zone, label):
    """1-based place of a rule in a zone's stack, or None. Results name some
    rules with their outlet ("Dam-Max Evacuation Release"); the stack does not."""
    for name, rules in zones:
        if name != zone:
            continue
        for i, rule in enumerate(rules):
            if label == rule or label.endswith("-" + rule):
                return i + 1
    return None


def activeZone(groups, name, dates):
    """
    The zone the pool was in each step, from the previous step's elevation and
    each zone's top ("<reservoir>-<zone> Elev-ZONE"): the lowest zone whose top
    is above the pool. None without the stack or the zone elevations.
    """
    zones = groups.get("stack", {}).get(name)
    elev = col(groups, "reservoirs", "%s-Pool Elev" % name)
    if not zones or elev is None:
        return None
    elev = elev.reindex(dates)
    prev = elev.shift(1).fillna(elev)
    zone = pd.Series(zones[-1][0], index=dates, dtype=object)
    for zname, _ in reversed(zones[:-1]):
        top = col(groups, "reservoirs", "%s-%s Elev-ZONE" % (name, zname))
        if top is None:
            return None
        zone[prev <= top.reindex(dates)] = zname
    return zone


def zoneOrder(groups, name, dates):
    """Zone names, the one the pool spent longest in first."""
    zones = groups.get("stack", {}).get(name, [])
    active = activeZone(groups, name, dates)
    counts = active.value_counts() if active is not None else pd.Series(dtype=int)
    return sorted([z for z, _ in zones], key=lambda z: -counts.get(z, 0))


def ruleStack(groups, dates):
    """One row per rule per zone per reservoir, top of the stack first."""
    rows = []
    for name in reservoirNames(groups):
        zones = groups.get("stack", {}).get(name)
        if not zones:
            continue
        active = activeZone(groups, name, dates)
        labels = [r[0] for r in reservoirRules(groups, name, dates)]
        for zone, rules in reversed(zones):
            if not rules:
                continue
            share = _pct((active == zone).sum(), len(active)) if active is not None else np.nan
            for i, rule in enumerate(rules):
                rows.append({"reservoir": name, "zone": zone, "pool_in_zone_pct": share,
                             "position": i + 1, "rule": rule,
                             "in_results": "yes" if any(l == rule or l.endswith("-" + rule) for l in labels) else "no"})
    return pd.DataFrame(rows)


def _near(a, b):
    return (a - b).abs() <= flowTol(b)


def _names(rules, test):
    """Per day, the labels of the rules for which test(values) is true, joined."""
    names = None
    for label, kind, values in rules:
        hit = test(kind, values).fillna(False)
        part = pd.Series(np.where(hit, label, ""), index=values.index)
        names = part if names is None else names.str.cat(part, sep="; ")
    if names is None:
        return None
    return names.str.replace(r"(; )+", "; ", regex=True).str.strip("; ")


def decideReleases(dates, elev, inflow, out, minLim, maxLim, rules):
    """
    The release decision for each day: the limits and the rules that set them,
    the rules in control, and every rule that wanted a different release and
    what stopped it. Returns the day-by-day table (the values: pool, limits,
    and what every rule asked for), each rule's status each day, and the
    rules that set the limits and the rules in control.

    A rule's value is compared with the outflow:
      equal                              in control
      above, outflow at the max limit    capped by the rule(s) that set the max
                                         limit, or by outlet capacity if none did
      below, outflow at the min limit    held up by the rule(s) that set the min limit
      otherwise                          the release was set by another rule
    A built-in min rule below the outflow, or max rule above it, is simply
    satisfied and not shown. Needs no knowledge of rule priority.
    """
    noMax = maxLim.isna() | (maxLim >= NO_LIMIT_CFS)
    noMin = minLim.isna() | (minLim <= FLOW_TOL_CFS)
    atMax = ~noMax & (out >= maxLim - flowTol(maxLim))
    atMin = ~noMin & (out <= minLim + flowTol(minLim))
    empty = pd.Series("", index=dates, dtype=object)

    maxBy = _names(rules, lambda k, v: (k in ("max", "script")) & _near(v, maxLim)) if rules else empty
    maxBy = maxBy.where(maxBy != "", "outlet capacity").where(~noMax, "")
    minBy = _names(rules, lambda k, v: (k in ("min", "script")) & _near(v, minLim)) if rules else empty
    minBy = minBy.where(~noMin, "")
    inControl = _names(rules, lambda k, v: _near(v, out)) if rules else empty

    statuses = []
    for label, kind, v in rules:
        ok = v.notna() & out.notna()
        above = ok & (v > out + flowTol(v))
        below = ok & (v < out - flowTol(v))
        status = pd.Series(np.nan, index=dates, dtype=object)
        status[ok & _near(v, out)] = "in control"
        if kind != "max":
            status[above & atMax] = "capped"
        if kind != "min":
            status[below & atMin] = "held up"
        if kind in ("script", "guide"):
            status[(above & ~atMax) | (below & ~atMin)] = "set by other"
        text = pd.Series("", index=dates, dtype=object)
        for key, verb, by in (("capped", "capped by", maxBy), ("held up", "held up by", minBy),
                              ("set by other", "set by", inControl)):
            m = status == key
            if m.any():
                text[m] = ("%s wanted " % label + v[m].map("{:,.0f}".format) + " cfs, released "
                           + out[m].map("{:,.0f}".format) + ": " + verb + " "
                           + by[m].where(by[m] != "", "no matching rule"))
        m = status == "in control"
        if m.any():
            text[m] = label + " in control at " + v[m].map("{:,.0f}".format) + " cfs"
        statuses.append((label, kind, v, status, text))

    columns = {"Elevation": elev.round(2), "Inflow": inflow.round(0), "Outflow": out.round(0),
               "Min limit": minLim.round(0), "Max limit": maxLim.where(~noMax).round(0)}
    for label, kind, v, status, text in statuses:
        columns[label] = v.round(0)
    table = pd.DataFrame(columns, index=dates)
    table.index.name = "Date"
    reasons = pd.DataFrame({"Min set by": minBy, "Max set by": maxBy, "In control": inControl},
                           index=dates)
    return table, statuses, reasons


def reservoirPlots(groups, dates, extras):
    """
    Elevation, flow and release decisions for every reservoir. Returns the
    plots, a table of how many days each rule was in control, a table of the
    conflicts, and each reservoir's daily release decision table.
    """
    plots, rows, conflictRows, decisions, inControl = {}, [], [], {}, {}
    for name in reservoirNames(groups):
        elev = col(groups, "reservoirs", "%s-Pool Elev" % name).reindex(dates)
        out = col(groups, "reservoirs", "%s-Pool Flow-OUT" % name).reindex(dates)
        inflow = col(groups, "reservoirs", "%s-Pool Flow-IN" % name)
        ruleCurve = col(groups, "reservoirs", "%s-Rule Curve Elev-ZONE" % name)
        minLim = col(groups, "limits", "%s Flow-MINLIM" % name)
        maxLim = col(groups, "limits", "%s Flow-MAXLIM" % name)
        minLim = minLim.reindex(dates) if minLim is not None else pd.Series(np.nan, index=dates)
        maxLim = maxLim.reindex(dates) if maxLim is not None else pd.Series(np.nan, index=dates)
        rules = reservoirRules(groups, name, dates)
        inflow = inflow.reindex(dates) if inflow is not None else pd.Series(np.nan, index=dates)
        table, statuses, reasons = decideReleases(dates, elev, inflow, out, minLim, maxLim, rules)
        zone = activeZone(groups, name, dates)
        inZone = {}
        if zone is not None:
            # After Date, Elevation, Inflow and Outflow, which stay in place
            table.insert(3, "Zone", zone)
            zones = groups["stack"][name]
            for label, kind, v, st, text in statuses:
                if kind != "guide":
                    inZone[label] = zone.map(lambda z: stackPosition(zones, z, label) is not None)
        decisions[name] = (table, statuses, inZone)
        inControl[name] = reasons["In control"]

        traces = [("Pool elevation", elev, "y1", {"color": "#1f77b4", "group": "elev"})]
        if ruleCurve is not None:
            traces.append(("Rule curve", ruleCurve.reindex(dates), "y1",
                           {"color": "#444444", "group": "elev"}))
        traces += [t for t in extras.get(name, []) if t[2] == "y1"]
        hover = ("in control: " + reasons["In control"]).where(reasons["In control"] != "", "")
        # Outflow and the limits are shown to start with; everything else on
        # the flow panel starts hidden, a click away in the legend
        traces.append(("Outflow", out, "y2", {"color": "#000000", "width": 2.5, "group": "flow",
                                              "hovertext": hover}))
        traces.append(("Inflow", inflow, "y2",
                       {"color": "#999999", "width": 1, "group": "flow", "hidden": True}))
        traces.append(("Min limit (all rules)", minLim, "y2",
                       {"color": "#1f77b4", "dash": "dash", "group": "flow"}))
        traces.append(("Max limit (all rules)", maxLim.where(maxLim < NO_LIMIT_CFS), "y2",
                       {"color": "#d62728", "dash": "dash", "group": "flow"}))
        traces += [(l, v, a, dict(st, hidden=True)) for l, v, a, st in extras.get(name, []) if a == "y2"]

        used = {}
        for label, kind, values, status, text in statuses:
            palette = [k[3] for k in RULE_KINDS if k[1] == kind][0]
            color = palette[used.get(kind, 0) % len(palette)]
            used[kind] = used.get(kind, 0) + 1
            active = out.notna() & values.notna()
            hit = status == "in control"
            traces.append(("%s (%s)" % (label, kind), values.where(values < NO_LIMIT_CFS), "y2",
                           {"color": color, "width": 1.2, "group": kind, "hidden": True}))
            rows.append({"reservoir": name, "rule": label, "saved_as": kind,
                         "days_with_value": _days(active),
                         "days_in_control": _days(hit),
                         "in_control_pct": _pct(hit.sum(), active.sum())})
            for key, verb, by in (("capped", "capped by", reasons["Max set by"]),
                                  ("held up", "held up by", reasons["Min set by"])):
                m = status == key
                if not m.any():
                    continue
                gap = (values - out).abs()[m]
                for who, days in by[m].value_counts().items():
                    sel = m & (by == who)
                    conflictRows.append({"reservoir": name, "rule": label, "saved_as": kind,
                                         "outcome": key, "by": who or "(not found)",
                                         "days": _days(days),
                                         "volume_af": round(gap[sel[m]].sum() * CFS_DAY_TO_AF * STEP_DAYS, 0)})
        if rules:
            free = out.notna() & (reasons["In control"] == "")
            rows.append({"reservoir": name, "rule": "(no rule equals the outflow)", "saved_as": "",
                         "days_with_value": _days(out.notna()),
                         "days_in_control": _days(free),
                         "in_control_pct": _pct(free.sum(), out.notna().sum())})

        # Decisions panel: one row per rule, a bar per run of steps with the
        # same status, so it only breaks where the status changes. Each run is
        # two points (start, and the start of the next step), which packs
        # smaller than a mark a day. One trace per status carries its colour.
        # With the model report every rule in the stack gets a row, empty if it
        # never acted: that it never did is worth seeing
        hasStack = bool(groups.get("stack", {}).get(name))
        strip = [st[0] for st in statuses if hasStack or st[3].notna().any()][::-1]
        stepEnd = pd.Series(dates[1:].append(pd.DatetimeIndex([dates[-1] + (dates[-1] - dates[-2])]))
                            if len(dates) > 1 else dates, index=dates)
        for key, legend, color in STATUS_STYLE:
            xs, ys = [], []
            for label, kind, values, status, text in statuses:
                run = (status != status.shift()).cumsum()
                for _, part in status[status == key].groupby(run[status == key]):
                    row = float(strip.index(label))
                    xs += [part.index[0], stepEnd[part.index[-1]], stepEnd[part.index[-1]]]
                    ys += [row, row, np.nan]
            if xs:
                traces.append((legend, pd.Series(ys, index=pd.DatetimeIndex(xs)), "y3",
                               {"color": color, "width": 9, "group": "decision", "hoverinfo": "skip"}))
        plots[name] = {"traces": traces, "categories": strip}
    return plots, pd.DataFrame(rows), pd.DataFrame(conflictRows), decisions, inControl


def loadControlPointLimits():
    """control_point_limits.csv (Table 2 flood flows) by junction, or {} if missing."""
    path = os.path.join(_here(), CONTROL_POINT_LIMITS)
    if not os.path.isfile(path):
        print("No %s: control point plots will have no flood limits" % path)
        return {}
    table = pd.read_csv(path, comment="#", skipinitialspace=True)
    return {str(r["junction"]).strip(): r for _, r in table.iterrows()}


def mainstemMinTargets(files, dates):
    """
    {"Salem": [(label, Series)], "Albany": [...]} from the BiOp minimum flow
    tables MainstemFlowAugSV reads (minFlowTargetCSV_Salem/_Albany): one line
    per distinct row, since the water year type that picks between them is an
    input the results do not carry. Each date's value holds until the next date.
    """
    out = {}
    for place in ("Salem", "Albany"):
        path = files.get("%s min flow" % place)
        if not path or not os.path.isfile(path):
            continue
        table = pd.read_csv(path, comment="#", skipinitialspace=True, encoding="utf-8-sig")
        table.columns = [str(c).strip() for c in table.columns]
        steps = []
        for c in table.columns[1:]:
            day = pd.to_datetime("2001" + c, format="%Y%d%b", errors="coerce")
            if pd.notna(day):
                steps.append(((day.month, day.day), c))
        steps.sort()
        keys = [(d.month, d.day) for d in dates]
        # The table's row for each date: the last step on or before it
        which = []
        for k in keys:
            col_ = steps[0][1]
            for when, c in steps:
                if when <= k:
                    col_ = c
            which.append(col_)
        lines, seen = [], []
        for _, row in table.iterrows():
            values = tuple(float(row[c]) for _, c in steps)
            if values in seen:
                # Same targets as an earlier row: widen its label instead
                i = seen.index(values)
                lines[i][0][1] = row.iloc[0]
                continue
            seen.append(values)
            series = pd.Series([float(row[c]) for c in which], index=dates)
            lines.append(([row.iloc[0], row.iloc[0]], series))
        labelled = []
        for (lo, hi), series in lines:
            wy = ("%g" % lo) if lo == hi else "%g to %g" % (lo, hi)
            labelled.append(("%s BiOp minimum, WY type %s" % (place, wy), series))
        out[place] = labelled
    return out


CP_STATUS = [("ok", "In range", "#2ca02c", 1), ("over", "Above maximum", "#d62728", 2),
             ("under", "Below minimum", "#1f77b4", 3)]
CP_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2",
             "#7f7f7f", "#bcbd22", "#17becf", "#393b79", "#637939"]
CP_KEY = """<span style="background:#dff2df;padding:0 4px">in range</span>
<span style="background:#fbdcdc;padding:0 4px">above maximum</span>
<span style="background:#dce8f7;padding:0 4px">below minimum</span>
<span style="background:#fff1b8;font-weight:600;padding:0 4px">reservoir releasing for this point</span>"""


def placeName(stationName):
    """"Willamette River at Salem" -> "Salem"."""
    m = re.search(r"\b(?:at|near|nr)\s+(.+)$", str(stationName))
    return m.group(1).strip() if m else str(stationName)


CP_LIMITS = [("regulation_goal_cfs", "regulation goal"), ("action_cfs", "action stage"),
             ("flood_cfs", "flood stage"), ("major_flood_cfs", "major flood stage")]


def cpLimitLines(r):
    """[(label, cfs)] for a control point's limits, lowest first; limits with
    the same flow share a label ("regulation goal / action stage")."""
    byValue = {}
    for key, label in CP_LIMITS:
        v = r.get(key)
        if pd.notna(v):
            byValue.setdefault(float(v), []).append(label)
    return [(" / ".join(labels), v) for v, labels in sorted(byValue.items())]


def controlPointStatus(groups, dates, limits, minTargets, inControl):
    """
    For every control point in control_point_limits.csv, in its order (basin
    by basin, upstream first): its flow against its limits, a status each day
    (above the regulation goal, below the minimum, or in range), the plot's
    traces, its daily table and a summary row.

    The maximum is the regulation goal, or the action flow where no goal is
    given. The minimum, at Salem and Albany only, is the lowest BiOp target for
    the day across water year types: below it is below every target.
    """
    table = groups.get("junctions")
    flowTraces, labels, statuses, tables, rows = [], [], [], {}, []
    if table is None:
        return None
    # Junctions with a real (not all-zero) local flow but no limits in the CSV
    # come after it: flows and table, but no status to judge
    points = list(limits.items())
    for c in table.columns:
        name = c[:-len(" Flow-Local")] if c.endswith(" Flow-Local") else None
        if name and name not in limits and not name.endswith("_IN") and (table[c].abs() > 0).any():
            points.append((name, {"station_name": name, "basin": "No limits", "reservoirs": ""}))
    for i, (junction, r) in enumerate(points):
        flow = table.get(junction + " Flow")
        if flow is None:
            continue
        flow = flow.reindex(dates)
        cumLocal = table.get(junction + " Flow-CUMLOC")
        place = placeName(r["station_name"])
        color = CP_COLORS[i % len(CP_COLORS)]
        goal = r.get("regulation_goal_cfs")
        action = r.get("action_cfs")
        maxFlow = float(goal) if pd.notna(goal) else (float(action) if pd.notna(action) else None)
        maxLine = pd.Series(maxFlow, index=dates) if maxFlow is not None else None
        lines = minTargets.get(place, [])
        minLine = pd.concat([l[1] for l in lines], axis=1).min(axis=1) if lines else None

        status = pd.Series("ok", index=dates, dtype=object)
        status[flow.isna()] = np.nan
        if minLine is not None:
            status[(minLine > 0) & (flow < minLine - flowTol(minLine))] = "under"
        if maxLine is not None:
            status[flow > maxLine + flowTol(maxLine)] = "over"
        if maxLine is not None or minLine is not None:
            labels.append("%s: %s" % (r["basin"], place))
            statuses.append(status)
        else:
            status[:] = np.nan

        shown = place == "Salem"
        style = {"group": place, "hidden": not shown}
        flowTraces.append(("%s flow" % place, flow, "y1", dict(style, color=color, width=2)))
        if cumLocal is not None:
            flowTraces.append(("%s cumulative local flow" % place, cumLocal.reindex(dates), "y1",
                               dict(style, color=color, width=1.2)))
        # Every distinct limit: the reservoirs regulate to different ones at
        # different times. Limits with the same flow share one line.
        limitLines = cpLimitLines(r)
        dashes = ["dash", "dashdot", "longdash", "12px,4px,2px,4px,2px,4px"]
        for j, (label, value) in enumerate(limitLines):
            flowTraces.append(("%s %s (%s cfs)" % (place, label, "{:,.0f}".format(value)),
                               pd.Series(value, index=dates), "y1",
                               dict(style, color=color, dash=dashes[j % len(dashes)], width=1.5)))
        for label, line in lines:
            flowTraces.append((label, line, "y1", dict(style, color=color, dash="dot", width=1.5)))

        # The daily table: the point's flow and limits, then each upstream
        # reservoir's release and the rules in control there
        keys = [place.lower()] + (["mainstemflowaug"] if place in ("Salem", "Albany") else [])
        cols = {"Flow": flow.round(0),
                "Cumulative local": cumLocal.reindex(dates).round(0) if cumLocal is not None else np.nan,
                "Minimum": minLine.round(0) if minLine is not None else np.nan}
        for label, value in limitLines:
            cols[label[0].upper() + label[1:]] = pd.Series(value, index=dates)
        codes = {"Flow": status.map({k: c for k, _, _, c in CP_STATUS}).fillna(0).astype(int)}
        # The limit the flow is over shades red too, the minimum blue when under it
        for label, value in limitLines:
            codes[label[0].upper() + label[1:]] = (flow > value + flowTol(pd.Series(value, index=dates))).map({True: 2, False: 0})
        if minLine is not None:
            codes["Minimum"] = ((minLine > 0) & (flow < minLine - flowTol(minLine))).map({True: 3, False: 0})
        nFixed = len(cols)
        for res in [x.strip() for x in str(r.get("reservoirs", "")).split(";") if x.strip()]:
            out = col(groups, "reservoirs", "%s-Pool Flow-OUT" % res)
            if out is None:
                continue
            out = out.reindex(dates)
            ruleText = inControl.get(res, pd.Series("", index=dates)).reindex(dates).fillna("")
            cols[res] = out.map(lambda v: "" if pd.isna(v) else "{:,.0f}".format(v)) + \
                ruleText.map(lambda t: (" · " + t) if t else "")
            forHere = ruleText.str.lower().map(lambda t: any(k in t for k in keys))
            codes[res] = forHere.map({True: 6, False: 0})
        t = pd.DataFrame(cols, index=dates)
        t.index.name = "Date"
        tables[place] = (t, pd.DataFrame(codes, index=dates).reindex(columns=t.columns).fillna(0).astype(int),
                         nFixed)

        over = status == "over"
        under = status == "under"
        if maxLine is None and minLine is None:
            continue
        rows.append({"basin": r["basin"], "control_point": place, "junction": junction,
                     "maximum_cfs": maxFlow, "days_above_max": _days(over),
                     "largest_excess_cfs": round((flow - maxLine)[over].max(), 0) if over.any() else 0,
                     "days_below_min": _days(under) if minLine is not None else "n/a",
                     "largest_shortfall_cfs": (round((minLine - flow)[under].max(), 0) if under.any() else 0)
                     if minLine is not None else "n/a"})

    # Status panel: a bar per control point, breaking only where its status changes
    cats = labels[::-1]
    stepEnd = pd.Series(dates[1:].append(pd.DatetimeIndex([dates[-1] + (dates[-1] - dates[-2])]))
                        if len(dates) > 1 else dates, index=dates)
    strip = []
    for key, legend, color, _ in CP_STATUS:
        xs, ys = [], []
        for label, status in zip(labels, statuses):
            run = (status != status.shift()).cumsum()
            for _, part in status[status == key].groupby(run[status == key]):
                row = float(cats.index(label))
                xs += [part.index[0], stepEnd[part.index[-1]], stepEnd[part.index[-1]]]
                ys += [row, row, np.nan]
        if xs:
            strip.append((legend, pd.Series(ys, index=pd.DatetimeIndex(xs)), "y2",
                          {"color": color, "width": 9, "group": "status", "hoverinfo": "skip"}))
    plot = {"All": {"traces": flowTraces + strip, "categories": cats}}
    return plot, tables, pd.DataFrame(rows)


def headroomCheck(groups, dates, limits, inControl):
    """
    For every upstream reservoir held back by a control point's max rule (a
    built-in MAX rule in control whose name contains the point's place name;
    scripted rules are left out, since the results cannot say whether they
    acted as a maximum), step by step:
    the release, the point's flow now and HEADROOM_LAG_STEPS later (when the
    release arrives), the room left under the maximum then, whether the pool
    was above its rule curve (so had water to move), and how the point's
    cumulative local flow changed meanwhile. Room that tracks a falling local
    flow suggests the rule assumes today's local flow persists; room shared by
    reservoirs held back together suggests they each leave space for the other.
    Returns the daily rows and a summary.
    """
    table = groups.get("junctions")
    daily, summary = [], []
    if table is None:
        return pd.DataFrame(), pd.DataFrame()
    lag = HEADROOM_LAG_STEPS
    for junction, r in limits.items():
        flow = table.get(junction + " Flow")
        goal, action = r.get("regulation_goal_cfs"), r.get("action_cfs")
        maxFlow = float(goal) if pd.notna(goal) else (float(action) if pd.notna(action) else None)
        if flow is None or maxFlow is None:
            continue
        place = placeName(r["station_name"])
        flow = flow.reindex(dates)
        arrive = flow.shift(-lag)
        room = maxFlow - arrive
        cumLocal = table.get(junction + " Flow-CUMLOC")
        localChange = (cumLocal.reindex(dates).shift(-lag) - cumLocal.reindex(dates)) if cumLocal is not None else None
        anyMissed = pd.Series(False, index=dates)
        for res in [x.strip() for x in str(r.get("reservoirs", "")).split(";") if x.strip()]:
            text = inControl.get(res)
            out = col(groups, "reservoirs", "%s-Pool Flow-OUT" % res)
            if text is None or out is None:
                continue
            text = text.reindex(dates).fillna("")
            maxRules = [label for label, kind, _ in reservoirRules(groups, res, dates)
                        if kind == "max" and place.lower() in label.lower()]
            if not maxRules:
                continue
            held = text.map(lambda t: any(m in t.split("; ") for m in maxRules))
            if not held.any():
                continue
            elev = col(groups, "reservoirs", "%s-Pool Elev" % res)
            curve = col(groups, "reservoirs", "%s-Rule Curve Elev-ZONE" % res)
            if elev is not None and curve is not None:
                above = elev.reindex(dates) > curve.reindex(dates)
            else:
                above = pd.Series(True, index=dates)
            missed = held & above & (room > HEADROOM_MIN_CFS)
            anyMissed |= missed
            for d in dates[held]:
                daily.append({"date": d, "control_point": place, "reservoir": res,
                              "release_cfs": round(out.reindex(dates)[d], 0),
                              "rules_in_control": text[d],
                              "limit_cfs": maxFlow,
                              "flow_now_cfs": round(flow[d], 0),
                              "flow_when_release_arrives_cfs": round(arrive[d], 0) if pd.notna(arrive[d]) else np.nan,
                              "room_cfs": round(room[d], 0) if pd.notna(room[d]) else np.nan,
                              "above_rule_curve": bool(above[d]),
                              "cum_local_change_cfs": round(localChange[d], 0) if localChange is not None and pd.notna(localChange[d]) else np.nan,
                              "room_counted": bool(missed[d])})
            summary.append({"control_point": place, "reservoir": res,
                            "days_held_back": _days(held),
                            "days_held_back_above_rule_curve": _days(held & above),
                            "days_with_room": _days(missed),
                            "mean_room_cfs": round(room[missed].mean(), 0) if missed.any() else 0,
                            "largest_room_cfs": round(room[missed].max(), 0) if missed.any() else 0,
                            "mean_cum_local_change_cfs": round(localChange[missed].mean(), 0)
                            if localChange is not None and missed.any() else np.nan})
        if anyMissed.any():
            # The room is the point's to share, so its volume is counted once
            summary.append({"control_point": place, "reservoir": "(all upstream)",
                            "days_with_room": _days(anyMissed),
                            "mean_room_cfs": round(room[anyMissed].mean(), 0),
                            "largest_room_cfs": round(room[anyMissed].max(), 0),
                            "room_volume_af": round(room[anyMissed].sum() * CFS_DAY_TO_AF * STEP_DAYS, 0),
                            "mean_cum_local_change_cfs": round(localChange[anyMissed].mean(), 0)
                            if localChange is not None else np.nan})
    return pd.DataFrame(daily), pd.DataFrame(summary)


def controlPointFile():
    return "Control points.html"


def writeControlPointPage(path, title, plot, tables):
    """All control points and their limits over a status bar each, with the
    chosen point's daily table underneath, linked by clicking."""
    fig, owner = stackedFigure(plot, ["Flow (cfs)", "Control point status"], rowHeights=[0.7, 0.3])
    cats = plot["All"]["categories"]
    fig.update_yaxes(tickmode="array", tickvals=list(range(len(cats))), ticktext=cats,
                     range=[-0.5, max(len(cats), 1) - 0.5], showgrid=False, row=2, col=1)
    # A legend click turns a whole control point (flow and limits) on or off
    fig.update_layout(height=950, margin={"t": 20}, legend={"groupclick": "toggleitem"})
    plotHtml = fig.to_html(full_html=False, include_plotlyjs="directory", div_id="plot")
    data = {}
    for name, (t, codes, freeze) in tables.items():
        t = t.reset_index()
        t["Date"] = _stamps(pd.DatetimeIndex(t["Date"]))
        codes = codes.reset_index(drop=True)
        codes.insert(0, "Date", 0)
        t = t.astype(object).where(t.notna(), None)
        data[name] = {"columns": list(t.columns), "data": t.values.tolist(),
                      "status": codes.values.tolist(), "priority": [None] * len(t.columns),
                      # Date, flows and limits stay put while the reservoirs scroll
                      "freeze": freeze + 1}    # and the date
    names = list(tables.keys())
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(RESERVOIR_PAGE % {
            "title": title, "plot": plotHtml,
            "pagelabel": "Control points", "sellabel": "Table for", "key": CP_KEY,
            "strip": json.dumps("yaxis2"), "channel": json.dumps("controlPointTable"),
            "tablelabel": json.dumps("Control point"),
            "owner": json.dumps([[o, s_] for o, s_ in owner]),
            "cats": json.dumps({"All": cats}),
            # Each trace's control point, so picking one in the list shows it
            "groups": json.dumps([t.legendgroup for t in fig.data]),
            "tables": json.dumps(data, default=float),
            "all": json.dumps(names),
            "files": json.dumps({n: controlPointFile() for n in names})})


def _stamps(index):
    """Date strings for plots and tables: the time too, only for sub-daily data."""
    daily = bool(((index.hour == 0) & (index.minute == 0)).all())
    return index.strftime("%Y-%m-%d" if daily else "%Y-%m-%d %H:%M")


def _traces(plot):
    return plot["traces"] if isinstance(plot, dict) else plot


def stackedFigure(plots, panels, rowHeights=None):
    """
    Every element's traces in one figure, all hidden but the first. Axis "y1",
    "y2", ... puts a trace in that panel, stacked top to bottom on shared dates.
    A trace's style may name its legend group, carry hover text, or start
    hidden. Returns the figure and, per trace, (element, visibility when shown).
    """
    fig = make_subplots(rows=len(panels), cols=1, shared_xaxes=True, vertical_spacing=0.03,
                        row_heights=rowHeights)
    owner = []
    for name, plot in plots.items():
        for label, series, axis, style in _traces(plot):
            if series is None:
                continue
            style = dict(style)
            mode = style.pop("mode", "lines")
            color = style.pop("color", None)
            row = min(int(axis[1:]), len(panels))
            group = style.pop("group", None)
            text = style.pop("hovertext", None)
            hidden = style.pop("hidden", False)
            template = style.pop("hovertemplate", None)
            extra = {}
            if template and text is None:
                extra["hovertemplate"] = template
            if "showlegend" in style:
                extra["showlegend"] = style.pop("showlegend")
            if "hoverinfo" in style:
                extra["hoverinfo"] = style.pop("hoverinfo")
            if group:
                extra.update({"legendgroup": group, "legendgrouptitle_text": LEGEND_GROUPS.get(group, group)})
            if text is not None:
                extra["hovertext"] = list(text.values)
                extra["hovertemplate"] = template or "%{y:,.0f}  %{hovertext}"
            x = _stamps(series.index) if isinstance(series.index, pd.DatetimeIndex) else series.index
            if mode == "markers":
                marker = {"color": color, "size": style.pop("size", 6)}
                if "symbol" in style:
                    marker["symbol"] = style.pop("symbol")
                trace = go.Scatter(x=x, y=series.values, name=label, mode=mode,
                                   marker=marker, visible=False, **extra)
            else:
                trace = go.Scatter(x=x, y=series.values, name=label, mode=mode,
                                   line=dict(color=color, **style), visible=False, **extra)
            fig.add_trace(trace, row=row, col=1)
            owner.append((name, "legendonly" if hidden else True))
    first = next(iter(plots), None)
    for trace, (o, shown) in zip(fig.data, owner):
        trace.visible = shown if o == first else False
    for i, title in enumerate(panels):
        fig.update_yaxes(title_text=title, row=i + 1, col=1)
    fig.update_layout(hovermode="x unified", legend={"groupclick": "toggleitem"},
                      hoverlabel={"namelength": -1})
    return fig, owner


def dropdownFigure(title, plots, panels, rowHeights=None):
    """A stacked figure with a dropdown to pick the element shown."""
    fig, owner = stackedFigure(plots, panels, rowHeights)
    names = list(plots.keys())
    buttons = [{"label": name, "method": "update",
                "args": [{"visible": [shown if o == name else False for o, shown in owner]},
                         {"title": "%s: %s" % (title, name)}]} for name in names]
    fig.update_layout(
        title="%s: %s" % (title, names[0]) if names else title,
        updatemenus=[{"buttons": buttons, "x": 1, "xanchor": "right", "y": 1.06, "yanchor": "bottom"}],
        height=950 if len(panels) > 1 else 600)
    return fig


RESERVOIR_KEY = """<span style="background:#dff2df;padding:0 4px">in control</span>
<span style="background:#fbdcdc;padding:0 4px">wanted more, capped</span>
<span style="background:#dce8f7;padding:0 4px">wanted less, held up</span>
<span style="background:#eeeeee;padding:0 4px">set by another rule</span>
<span style="color:#aaa;padding:0 4px">not in this zone's stack</span>"""

RESERVOIR_PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>%(pagelabel)s: %(title)s</title>
<style>
body{font-family:sans-serif;margin:0 16px;background:#fff;color:#222}
#bar{position:sticky;top:0;background:#fff;z-index:5;padding:8px 0;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
#bar select{font-size:15px;padding:3px}
#chips button{margin:2px 4px 2px 0;padding:2px 8px;border:1px solid #bbb;border-radius:10px;background:#f6f6f6;color:#666;cursor:pointer}
#chips button.on{background:#dfe9f7;border-color:#6b8fc7;color:#111;font-weight:600}
#tablebox{height:32vh;overflow:auto;border:1px solid #ccc}
table{border-collapse:separate;border-spacing:0;font-size:12px;width:100%%}
th{position:sticky;top:0;background:#f0f0f0;z-index:1}
td,th{border-right:1px solid #ddd;border-bottom:1px solid #ddd;padding:2px 6px;vertical-align:bottom}
th{font-weight:600;text-align:right;min-width:52px;max-width:110px}
td{text-align:right;white-space:nowrap}
td:first-child,th:first-child{text-align:left;min-width:80px}
td{background:#fff}
td.s1{background:#dff2df} td.s2{background:#fbdcdc} td.s3{background:#dce8f7} td.s4{background:#eeeeee}
td.s5{color:#c4c4c4}
td.s6{background:#fff1b8;font-weight:600}
tr.picked td{background:#ffe08a}
tr:hover td{background:#eef4ff;cursor:pointer}
</style></head><body>
<div id="bar"><b>%(title)s</b>
<label>%(sellabel)s <select id="res"></select></label>
<span>%(key)s</span>
<button id="pop" class="plotonly">Open table in its own window</button>
<span class="plotonly" style="color:#666">Click a day on the plot to find it in the table; click a row to mark it on the plot.</span></div>
<div id="chips" class="plotonly" style="display:none;margin:0 0 6px 0"></div>
%(plot)s
<div id="tablebox"><table id="tbl"></table></div>
<script>
var OWNER = %(owner)s, CATS = %(cats)s, TABLES = %(tables)s, ALL = %(all)s, FILES = %(files)s,
    STRIP = %(strip)s, CHANNEL = %(channel)s, TABLE_LABEL = %(tablelabel)s, GROUPS = %(groups)s;
// The same page shows the plot with the table under it, or, opened with
// "#table", the table alone to fill another window. The two windows talk
// through localStorage, which every local file shares in Chrome and Edge:
// pages opened from disk count as separate sites and cannot reach each other.
// Only the table window itself (opened under the name CHANNEL) hides the plot:
// the same address reached any other way, e.g. from history, shows everything
var TABLE_ONLY = location.hash.indexOf("#table") === 0 && window.name === CHANNEL;
var HAS_PLOTLY = typeof Plotly !== "undefined";
var gd = document.getElementById("plot"), sel = document.getElementById("res"),
    box = document.getElementById("tablebox"), tbl = document.getElementById("tbl"),
    current = Object.keys(TABLES)[0], me = String(Math.random());
// "#table=<name>" picks which table, when a page holds several
var wanted = decodeURIComponent(location.hash.split("=").slice(1).join("="));
if (TABLES[wanted]) current = wanted;
function tableUrl(name) { return FILES[name] + "#table=" + encodeURIComponent(name); }
function send(msg) {
  msg.from = me; msg.t = Date.now();
  try { localStorage.setItem(CHANNEL, JSON.stringify(msg)); } catch (e) {}
}
ALL.forEach(function (n) { var o = document.createElement("option"); o.text = n; sel.add(o); });
sel.value = current;
function fmt(v) { return (typeof v === "number") ? v.toLocaleString(undefined, {maximumFractionDigits: 2}) : (v === null ? "" : v); }
function drawTable() {
  var t = TABLES[current], cols = t.columns, html = "<tr>" + cols.map(function (c, j) {
    var p = t.priority && t.priority[j];
    return "<th>" + c + (p ? "<br><span style='color:#888;font-weight:400'>" + p + "</span>" : "") + "</th>";
  }).join("") + "</tr>";
  t.data.forEach(function (r, i) {
    var st = t.status[i];
    html += "<tr data-date='" + r[0] + "'>" +
      r.map(function (v, j) { return "<td" + (st[j] ? " class='s" + st[j] + "'" : "") + ">" + fmt(v) + "</td>"; }).join("") + "</tr>";
  });
  tbl.innerHTML = html;
  freezeColumns(t.freeze || 0, t.data.length && String(t.data[0][0]).length > 10 ? 124 : 96);
}
// Keep the first n columns in place while the rest scroll sideways. They get
// fixed widths, so where each sits is known rather than measured: a measured
// position goes stale when the browser lays the table out differently, and
// the scrolled columns then show through the gaps.
function freezeColumns(n, dateWidth) {
  var doc = tbl.ownerDocument, style = doc.getElementById("freeze");
  if (!style) { style = doc.createElement("style"); style.id = "freeze"; doc.head.appendChild(style); }
  var css = "", left = 0;
  for (var j = 0; j < n; j++) {
    var w = j === 0 ? dateWidth : 84;
    var cells = "#tbl td:nth-child(" + (j + 1) + "), #tbl th:nth-child(" + (j + 1) + ")";
    css += cells + "{position:sticky;left:" + left + "px;box-sizing:border-box;" +
           "width:" + w + "px;min-width:" + w + "px;max-width:" + w + "px;white-space:normal}";
    css += "#tbl td:nth-child(" + (j + 1) + "){z-index:1;white-space:nowrap;overflow:hidden}" +
           "#tbl th:nth-child(" + (j + 1) + "){z-index:3}";
    left += w;
  }
  if (n > 0) css += "#tbl td:nth-child(" + n + "),#tbl th:nth-child(" + n + "){box-shadow:2px 0 0 #999}";
  style.textContent = css;
}
function markPlot(date) {
  if (TABLE_ONLY || !HAS_PLOTLY) return;
  Plotly.relayout(gd, {shapes: date ? [{type: "line", xref: "x", yref: "paper", x0: date, x1: date, y0: 0, y1: 1,
                                       line: {color: "#ff9900", width: 2}}] : []});
}
function markRow(date) {
  Array.prototype.forEach.call(tbl.querySelectorAll("tr.picked"), function (r) { r.classList.remove("picked"); });
  var row = tbl.querySelector("tr[data-date='" + date + "']");
  if (row) { row.classList.add("picked"); row.scrollIntoView({block: "center"}); }
}
function stamp(x) { return String(x).replace("T", " ").slice(0, 16); }
function switchTo(name) {
  if (TABLES[name]) {
    current = name; sel.value = name;
    if (TABLE_ONLY) { document.title = TABLE_LABEL + ": " + current; } else { showPlot(); }
    drawTable();
    if (!TABLE_ONLY) send({type: "show", reservoir: current});
  } else {
    location.href = TABLE_ONLY ? tableUrl(name) : FILES[name];
  }
}
sel.onchange = function () { switchTo(sel.value); };
tbl.onclick = function (e) {
  var row = e.target.closest("tr[data-date]"); if (!row) return;
  var d = row.dataset.date; markRow(d); markPlot(d);
  send({type: "mark", reservoir: current, date: d});
};
window.addEventListener("storage", function (e) {
  if (e.key !== CHANNEL || !e.newValue) return;
  var msg = JSON.parse(e.newValue);
  if (msg.from === me) return;
  if (msg.type === "alive") { if (!TABLE_ONLY) { box.style.display = "none"; lastAlive = Date.now(); } return; }
  if (TABLE_ONLY && msg.reservoir !== current) {
    // The plot moved to another element: follow it
    if (TABLES[msg.reservoir]) { switchTo(msg.reservoir); if (msg.date) markRow(msg.date); return; }
    try { localStorage.setItem(CHANNEL + "Pending", msg.date || ""); } catch (err) {}
    location.href = tableUrl(msg.reservoir);
    return;
  }
  if (msg.type === "mark" && msg.reservoir === current) { markRow(msg.date); markPlot(msg.date); }
});
// The plot's traces and status rows for the current element. A page whose
// plot holds all its elements at once (the control points) keeps its own.
function showPlot() {
  if (!HAS_PLOTLY) return;
  if (GROUPS) {
    // A page with all its elements on one plot (the control points): show the
    // picked one and the status bars, hide the rest; the legend brings any back
    Plotly.restyle(gd, {visible: GROUPS.map(function (g) {
      return (g === current || g === "status") ? true : "legendonly"; })});
  }
  var key = OWNER.some(function (o) { return o[0] === current; }) ? current : null;
  if (key) Plotly.restyle(gd, {visible: OWNER.map(function (o) { return o[0] === key ? o[1] : false; })});
  var cats = CATS[key || (OWNER.length ? OWNER[0][0] : "")] || [];
  var lay = {};
  lay[STRIP + ".tickmode"] = "array"; lay[STRIP + ".tickvals"] = cats.map(function (c, i) { return i; });
  lay[STRIP + ".ticktext"] = cats; lay[STRIP + ".range"] = [-0.5, Math.max(cats.length, 1) - 0.5];
  Plotly.relayout(gd, lay);
}
// On a page with every element on one plot, a button per element turns all
// its lines on or off together; the legend still turns single lines on or off
function groupNames() {
  var seen = [];
  (GROUPS || []).forEach(function (g) { if (g && g !== "status" && seen.indexOf(g) < 0) seen.push(g); });
  return seen;
}
function paintChips() {
  if (!GROUPS || !HAS_PLOTLY) return;
  Array.prototype.forEach.call(document.querySelectorAll("#chips button"), function (btn) {
    var on = gd.data.some(function (t, i) { return GROUPS[i] === btn.dataset.group && t.visible === true; });
    btn.classList.toggle("on", on);
  });
}
function buildChips() {
  if (!GROUPS || !HAS_PLOTLY || TABLE_ONLY) return;
  var box = document.getElementById("chips");
  box.style.display = "";
  box.innerHTML = "<span style='color:#666;margin-right:6px'>Show:</span>";
  groupNames().forEach(function (g) {
    var btn = document.createElement("button"); btn.textContent = g; btn.dataset.group = g;
    btn.onclick = function () {
      var on = btn.classList.contains("on"), idx = [];
      GROUPS.forEach(function (x, i) { if (x === g) idx.push(i); });
      Plotly.restyle(gd, {visible: on ? "legendonly" : true}, idx);
    };
    box.appendChild(btn);
  });
  gd.on("plotly_restyle", paintChips);
  paintChips();
}
var lastAlive = 0;
if (TABLE_ONLY) {
  document.title = TABLE_LABEL + ": " + current;
  gd.parentNode.style.display = "none";    // Plotly's wrapper around the plot
  Array.prototype.forEach.call(document.querySelectorAll(".plotonly"), function (el) { el.style.display = "none"; });
  box.style.height = "calc(100vh - 60px)";
  drawTable();
  var pending = ""; try { pending = localStorage.getItem(CHANNEL + "Pending") || ""; localStorage.removeItem(CHANNEL + "Pending"); } catch (e) {}
  if (pending) markRow(pending);
  // Tell plot pages this window is open, so they can drop their own table
  setInterval(function () { send({type: "alive", reservoir: current}); }, 1000);
  send({type: "alive", reservoir: current});
} else {
  if (!HAS_PLOTLY) {
    var note = document.createElement("p");
    note.style.cssText = "color:#b00;font-weight:600";
    note.textContent = "The plot could not load: plotly.min.js must be in the same folder as this page.";
    box.parentNode.insertBefore(note, box);
  }
  showPlot();
  buildChips();
  drawTable();
  if (HAS_PLOTLY) gd.on("plotly_click", function (ev) {
    var d = stamp(ev.points[0].x); markPlot(d); markRow(d);
    send({type: "mark", reservoir: current, date: d});
  });
  document.getElementById("pop").onclick = function () {
    window.open(tableUrl(current), CHANNEL, "width=1400,height=900");
  };
  // A table window already open follows this page to its reservoir
  send({type: "show", reservoir: current});
  // Show this page's own table again once the table window closes
  setInterval(function () { if (Date.now() - lastAlive > 2500) box.style.display = ""; }, 1000);
}
</script></body></html>
"""


def reservoirFile(name):
    return "Reservoir - %s.html" % name


def writeReservoirPage(path, title, plots, tables, allNames=None, groups=None):
    """
    The reservoir plot and its release decision table on one linked page.
    allNames lists every reservoir for the page's list; those not on this page
    are reached by switching to their own page.
    """
    panels = ["Elevation (ft)", "Flow (cfs)", "Release decisions"]
    fig, owner = stackedFigure(plots, panels, rowHeights=[0.3, 0.42, 0.28])
    fig.update_layout(height=1000, margin={"t": 20})
    first = next(iter(plots), None)
    if first:
        cats = plots[first]["categories"]
        fig.update_yaxes(tickmode="array", tickvals=list(range(len(cats))), ticktext=cats,
                         range=[-0.5, max(len(cats), 1) - 0.5], showgrid=False, row=3, col=1)
    plotHtml = fig.to_html(full_html=False, include_plotlyjs="directory", div_id="plot")
    codes = {key: i + 1 for i, (key, _, _) in enumerate(STATUS_STYLE)}
    data = {}
    zoneAbbr = lambda z: "".join(w[0] for w in z.split()).upper()
    for name, (table, statuses, inZone) in tables.items():
        t = table.reset_index()
        t["Date"] = _stamps(pd.DatetimeIndex(t["Date"]))
        # Each rule's status that day shades its cell, as in the decisions panel
        status = pd.DataFrame(0, index=table.index, columns=t.columns)
        for label, kind, v, st, text in statuses:
            code = st.map(codes).fillna(0).astype(int)
            # A rule not in the stack of the zone the pool was in is greyed out
            if label in inZone:
                code = code.where(inZone[label].values | (code > 0), len(codes) + 1)
            status[label] = code.values
        t = t.astype(object).where(t.notna(), None)
        # Each rule's place in the stack of each zone, under its name
        zones = (groups or {}).get("stack", {}).get(name, [])
        places = []
        for c in t.columns:
            p = ["%s %d" % (zoneAbbr(z), stackPosition(zones, z, c)) for z, _ in reversed(zones)
                 if stackPosition(zones, z, c)]
            places.append(" · ".join(p) or None)
        data[name] = {"columns": list(t.columns), "data": t.values.tolist(),
                      "status": status.values.tolist(), "priority": places,
                      "freeze": 4}    # Date, Elevation, Inflow, Outflow stay put while the rules scroll
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(RESERVOIR_PAGE % {
            "title": title, "plot": plotHtml,
            "owner": json.dumps([[o, s] for o, s in owner]),
            "cats": json.dumps({n: p["categories"] for n, p in plots.items()}),
            "tables": json.dumps(data, default=float),
            "pagelabel": "Reservoirs", "sellabel": "Reservoir", "key": RESERVOIR_KEY,
            "strip": json.dumps("yaxis3"), "channel": json.dumps("releaseDecisions"),
            "groups": "null",
            "tablelabel": json.dumps("Release decisions"),
            "all": json.dumps(list(allNames or plots.keys())),
            "files": json.dumps({n: reservoirFile(n) for n in (allNames or plots.keys())})})


def writeReport(runDir, runInfo, configRoot, configFiles, results, plotFiles):
    parts = ["<html><head><meta charset='utf-8'><title>Model check: %s %s</title>"
             % (runInfo.get("simulation", ""), runInfo.get("alternative", "")),
             "<style>body{font-family:sans-serif;margin:24px}table{border-collapse:collapse;"
             "font-size:13px}td,th{border:1px solid #ccc;padding:3px 6px;text-align:right}"
             "th{background:#f0f0f0}td:first-child{text-align:left}</style></head><body>",
             "<h1>Model check: %s / %s</h1>" % (runInfo.get("simulation", ""), runInfo.get("alternative", "")),
             "<p>DSS: %s<br>Config files read from: %s</p><ul>" % (runInfo.get("dss_path", ""), configRoot)]
    for label, path in configFiles.items():
        parts.append("<li>%s: %s</li>" % (label, path))
    parts.append("</ul><h2>Plots</h2><ul>")
    for label, plotFile in plotFiles:
        parts.append("<li><a href='plots/%s'>%s</a></li>" % (plotFile, label))
    parts.append("</ul>")
    for check, (table, note) in results.items():
        parts.append("<h2>%s</h2><p>%s</p>" % (check, note))
        parts.append(table.to_html(index=False, na_rep="") if len(table) else "<p>Nothing to check.</p>")
    parts.append("</body></html>")
    with open(os.path.join(runDir, "report.html"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))


def main(runDir=None, startDate=None, endDate=None, headroom=None):
    """
    Check one output folder. run_model_check.py passes the folder and dates;
    otherwise RUN_DIR (or the newest folder), START_DATE and END_DATE.
    """
    runDir = runDir or findRunDir()
    with open(os.path.join(runDir, "run_info.json")) as fh:
        runInfo = json.load(fh)
    configRoot = findConfigRoot(runInfo)
    altConfig = readAltConfig(configRoot, runInfo.get("alternative", ""))
    groups = loadGroups(runDir)
    if "reservoirs" not in groups or "limits" not in groups:
        sys.exit("%s needs reservoirs.csv and limits.csv from extract_dss.py" % runDir)
    if "rules" not in groups:
        print("No rules.csv in this folder: re-run extract_dss.py to check whether "
              "each rule was followed, not only whether the target was met.")

    dates = groups["reservoirs"].index
    start = startDate or START_DATE
    end = endDate or END_DATE
    if not start and "diversions" in groups:
        start = groups["diversions"].dropna(how="all").index.min()
    if start:
        dates = dates[dates >= pd.Timestamp(start)]
    if end:
        dates = dates[dates < pd.Timestamp(end) + pd.Timedelta(days=1)]
    global STEP_DAYS
    if len(dates) > 1:
        STEP_DAYS = float(pd.Series(dates).diff().median() / pd.Timedelta(days=1))
    print("Time step: %g hours" % (STEP_DAYS * 24))
    print("Checking %s, %s to %s, configs from %s"
          % (runDir, dates.min().date(), dates.max().date(), configRoot))

    files = {
        "FIRO_SPACE": configPath(configRoot, altConfig, "firoSpaceConfigCSV",
                                 "scripts/externalRules/FIRO_SPACEConfig.csv"),
        "Minimum flow": configPath(configRoot, altConfig, "minFlowConfigCSV",
                                   "scripts/externalRules/MinFlowConfig.csv"),
        "Withdrawal": configPath(configRoot, altConfig, "withdrawalConfigCSV",
                                 "scripts/externalRules/WithdrawalConfig.csv"),
        "Diversions": configPath(configRoot, altConfig, "diversionConfigCSV",
                                 "scripts/externalRules/DiversionConfig_ALT.csv"),
        "Salem min flow": configPath(configRoot, altConfig, "minFlowTargetCSV_Salem",
                                     "scripts/externalSVs/MinFlowSalem_2008BiOp.csv"),
        "Albany min flow": configPath(configRoot, altConfig, "minFlowTargetCSV_Albany",
                                      "scripts/externalSVs/MinFlowAlbany_2008BiOp.csv"),
    }
    plotDir = os.path.join(runDir, "plots")
    if not os.path.isdir(plotDir):
        os.makedirs(plotDir)
    # The pages load plotly.min.js from beside them. to_html only links to it,
    # so write it here, fresh each run to match the plotly that made the pages
    from plotly.offline import get_plotlyjs
    with open(os.path.join(plotDir, "plotly.min.js"), "w", encoding="utf-8") as fh:
        fh.write(get_plotlyjs())
    # Per-check plots from earlier versions of this script
    for old in ("FIRO_SPACE.html", "MinFlow.html", "Diversions.html", "Reservoirs.html", "ControlPoints.html"):
        if os.path.isfile(os.path.join(plotDir, old)):
            os.remove(os.path.join(plotDir, old))

    checks = [
        ("FIRO_SPACE", ["FIRO_SPACE"], lambda: checkFiro(groups, files["FIRO_SPACE"], dates),
         "Achieving: pool within %.1f ft of the target. Off-target days are explained when "
         "the outflow sat on the max limit (could not draft) or the min limit (could not fill). "
         "Targeting: rule_followed_pct is how often the outflow obeyed the FIRO rule's own value; "
         "overridden days are where another rule won." % ELEV_TOL_FT),
        ("MinFlow", ["Minimum flow", "Withdrawal"], lambda: checkMinFlow(groups, files["Minimum flow"], files["Withdrawal"], dates),
         "Minimum flow + withdrawal from the config against the outflow where it is met. "
         "A shortfall is explained when the max limit was below the requirement. "
         "rule_attached says whether %s exists at that reservoir in this run." % MINFLOW_RULE_NAME),
        ("Diversions", ["Diversions"], lambda: checkDiversions(groups, files["Diversions"], dates),
         "Whether DiversionFromCSV wrote the config value to its rule (within %.1f cfs)." % RULE_TOL_CFS),
    ]
    results = {}
    extras = {}
    groups["stack"] = loadStack(runDir)
    stack = ruleStack(groups, dates)
    if len(stack):
        stack.to_csv(os.path.join(runDir, "RuleStack_summary.csv"), index=False)
        results["Rule stack"] = (
            stack, "Each reservoir's rules in each zone, top of the stack first, from the active "
            "operation set in modelReport.json (written by Alternative_Setup on every compute). "
            "pool_in_zone_pct: share of the run the pool spent in the zone, from the zone-top "
            "elevations. in_results: whether the rule's values are in the results; a rule marked "
            "no is in the operation set but saved nothing.")
    else:
        print("No modelReport.json in this folder, or no zones in it: re-run extract_dss.py "
              "to show the rule stack.")
    for name, needs, run, note in checks:
        missing = [files[k] for k in needs if not os.path.isfile(files[k])]
        if missing:
            print("%-11s skipped, config not found: %s" % (name, ", ".join(missing)))
            continue
        table, traces = run()
        for element, t in traces.items():
            extras.setdefault(element, []).extend(t)
        table.to_csv(os.path.join(runDir, "%s_summary.csv" % name), index=False)
        results[name] = (table, note)
        print("\n== %s ==" % name)
        with pd.option_context("display.width", 200, "display.max_columns", 30):
            print(table.to_string(index=False) if len(table) else "nothing to check")

    resPlots, control, conflicts, decisions, inControl = reservoirPlots(groups, dates, extras)
    # One page per reservoir keeps each file a size a browser opens quickly,
    # even for years of sub-daily results
    names = list(resPlots.keys())
    for name in names:
        writeReservoirPage(os.path.join(plotDir, reservoirFile(name)),
                           "%s / %s" % (runInfo.get("simulation", ""), runInfo.get("alternative", "")),
                           {name: resPlots[name]}, {name: decisions[name]}, names, groups)
    decisionDir = os.path.join(runDir, "release_decisions")
    if not os.path.isdir(decisionDir):
        os.makedirs(decisionDir)
    for name, (table, _, _) in decisions.items():
        table.to_csv(os.path.join(decisionDir, "%s.csv" % name))
    control.to_csv(os.path.join(runDir, "RuleControl_summary.csv"), index=False)
    conflicts.to_csv(os.path.join(runDir, "Conflicts_summary.csv"), index=False)
    if "rules" in groups:
        results["Conflicts"] = (
            conflicts.sort_values(["reservoir", "volume_af"], ascending=[True, False]) if len(conflicts) else conflicts,
            "Rules that wanted a different release and what stopped them. <b>capped</b>: the rule "
            "wanted more, and the outflow sat on the max limit set by <i>by</i> (outlet capacity when "
            "no rule's value equals the max limit). <b>held up</b>: the rule wanted less, and the "
            "outflow sat on the min limit set by <i>by</i>. volume_af is the total difference "
            "between what the rule wanted and the release. Day by day in release_decisions/ and "
            "the table under the reservoir plot.")
        results["RuleControl"] = (
            control[control["days_in_control"] > 0],
            "Days each rule's value equalled the outflow (within %.0f cfs or %.0f%%), i.e. the rule "
            "was in control. Several rules can share a day. Rules never in control are left out "
            "here; RuleControl_summary.csv has them all." % (FLOW_TOL_CFS, 100 * FLOW_TOL_FRAC))
    cpLimits = loadControlPointLimits()
    cpMins = mainstemMinTargets(files, dates)
    plotFiles = [("Reservoir: %s" % n, reservoirFile(n)) for n in names]
    status = controlPointStatus(groups, dates, cpLimits, cpMins, inControl) if cpLimits else None
    if status:
        cpPlot, cpTables, cpSummary = status
        if "Salem" in cpTables:
            cpTables = dict([("Salem", cpTables["Salem"])] + [(k, v) for k, v in cpTables.items() if k != "Salem"])
        writeControlPointPage(os.path.join(plotDir, controlPointFile()),
                              "%s / %s" % (runInfo.get("simulation", ""), runInfo.get("alternative", "")),
                              cpPlot, cpTables)
        plotFiles.insert(0, ("Control points: status, limits and releases", controlPointFile()))
        if HEADROOM if headroom is None else headroom:
            hDaily, hSummary = headroomCheck(groups, dates, cpLimits, inControl)
            hDaily.to_csv(os.path.join(runDir, "ControlPointHeadroom_daily.csv"), index=False)
            hSummary.to_csv(os.path.join(runDir, "ControlPointHeadroom_summary.csv"), index=False)
            print("\n== Control point headroom (CSV only) ==")
            with pd.option_context("display.width", 200, "display.max_columns", 30):
                print(hSummary.to_string(index=False) if len(hSummary) else "no reservoir held back by a control point")
        cpSummary.to_csv(os.path.join(runDir, "ControlPoints_summary.csv"), index=False)
        results["Control points"] = (
            cpSummary, "Flow at each control point against its maximum (the regulation goal, or the "
            "action flow where none is given, from control_point_limits.csv) and, at Salem and Albany, "
            "the lowest BiOp minimum for the day across water year types.")

    writeReport(runDir, runInfo, configRoot, files, results, plotFiles)
    print("\nReport: %s" % os.path.join(runDir, "report.html"))


if __name__ == "__main__":
    main()
