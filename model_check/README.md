# model_check

Checks a ResSim run against the config files its scripted rules read. Runs on
desktop Python 3 in the `hydro39` conda environment (pydsstools, pandas,
plotly), not inside ResSim.

## Steps

Set the path to the simulation's DSS file, the alternative and the steps to run in
`model_check_config.txt`, then:

```powershell
conda activate hydro39
python model_check\run_model_check.py
```

Or open `run_model_check.py` in Jupyter or VS Code and run it. The steps:

| Step | Does | Run it when |
|---|---|---|
| `run_catalog` | lists every record in `simulation.dss` | looking for records to add to the extract |
| `run_extract` | pulls the alternative's results into CSVs | after every model run |
| `run_check` | compares with the configs; writes the report and plots | always. With extract off, it checks the newest extract of that simulation and alternative, e.g. after changing a config file |

Each script also still runs on its own (`DSS_PATH` / `RUN_DIR` at the top).

## Control point limits

`control_point_limits.csv` holds the flood flows at each control point (action
or bankfull, flood and major flood) and the regulation goal, from Table 2,
"Flood regulation goals at Willamette projects", with each station matched to
its junction in the model. ResSim does not save control point limits in the
results, so the control point checks read them from here. Update it when the
rating tables or regulation goals change.

**Control points page** (`plots/Control points.html`):

- **Plot.** Every control point in `control_point_limits.csv`: its flow,
  cumulative local flow, and every distinct limit (regulation goal,
  action, flood and major flood stage, each its own dash style; limits with the
  same flow share a line), since the reservoirs regulate to different ones at
  different times. Salem is shown to start with. Picking a point in the list
  shows it and hides the others; the Show buttons above the plot turn a whole
  point on or off, and the legend single lines.
- **Salem and Albany minimums.** The BiOp targets from the tables the
  alternative points to (`minFlowTargetCSV_Salem` and `_Albany` in alt_config),
  one dotted line per distinct row of the table, since the water year type
  that chooses between them is not in the results. When flow augmentation is
  on, the model's own target (`Min_Flow_Target_<place>`) is also in the
  results.
- **Status bars.** One per control point, grouped by basin, upstream first:
  green in range, red above the maximum (the regulation goal, or the action
  flow where none is given), blue below the minimum (the lowest BiOp target
  that day).
- **Table.** For the point picked in the list, each day's flow, cumulative
  local flow, minimum and each limit, then each upstream
  reservoir's release with the rules in control there, highlighted when a rule
  is releasing for that point (its name contains the place, or
  MainstemFlowAug at Salem and Albany). It links to the plot and opens in its
  own window like the reservoir table.
- **Other junctions.** Those with a real (not all-zero) local flow but no row
  in the CSV, such as Oregon City, are listed under "No limits", with flows and
  a table but no status bar.

The `basin` and `reservoirs` columns of the CSV set the grouping and the
upstream reservoirs; edit them there.

**Headroom** (optional: `run_headroom: true` in `model_check_config.txt`). On
steps a reservoir is held back by a control point's built-in MAX rule (one in
control whose name contains the point's place name) while above its rule curve,
the room left under the point's maximum when that release arrives
(`HEADROOM_LAG_STEPS` later), counted when over `HEADROOM_MIN_CFS`. Writes
`ControlPointHeadroom_daily.csv` (every held-back step: release, rules, flow now
and on arrival, room, above rule curve, change in cumulative local flow) and
`ControlPointHeadroom_summary.csv` (days held back and with room per reservoir,
and the room's volume per control point, counted once since the reservoirs
share it). Nothing is added to the report or the plots. Room that tracks a
falling cumulative local flow suggests the rule assumes the local flow persists
over the travel time; room when two reservoirs are held back together suggests
each leaves space for the other.

## Files it reads

These are read but never written by these scripts. Everything else comes from
the extract.

| File | Where | Read by | For |
|---|---|---|---|
| `model_check_config.txt` | this folder | `run_model_check.py` | DSS path, alternative, steps, dates |
| `simulation.dss` | the path in `simulation_dss` | `catalog_dss.py`, `extract_dss.py` | the run's results |
| `modelReport_<alternative>.json` | the watershed's `rss` folder, then the simulation folder | `extract_dss.py` | the rule stack; optional |
| `control_point_limits.csv` | this folder | `check_model.py` | control point flood flows and regulation goals |
| `alt_config/_default.txt`, `alt_config/<alternative>.txt` | `scripts/` | `check_model.py` | which config files the alternative uses |
| `FIRO_SPACEConfig.csv` | `scripts/externalRules/` (key `firoSpaceConfigCSV`) | `check_model.py` | FIRO_SPACE targets |
| `MinFlowConfig.csv`, `WithdrawalConfig.csv` | `scripts/externalRules/` (keys `minFlowConfigCSV`, `withdrawalConfigCSV`) | `check_model.py` | minimum flows and withdrawals |
| `DiversionConfig_ALT.csv` | `scripts/externalRules/` (key `diversionConfigCSV`) | `check_model.py` | diversion amounts |
| `MinFlowSalem_2008BiOp.csv`, `MinFlowAlbany_2008BiOp.csv` | `scripts/externalSVs/` (keys `minFlowTargetCSV_Salem`, `_Albany`) | `check_model.py` | Salem and Albany BiOp minimums |

The `scripts/` files come from the watershed if it is on this machine,
otherwise from this repository's `data/` folder, and the alt_config key, when
set, overrides the default name shown.

## What you get

`extract_dss.py` writes `output/<simulation>_<alternative>_<date>/`:

| File | Contents |
|---|---|
| `reservoirs.csv` | inflow, outflow, elevation and rule curve per reservoir |
| `limits.csv` | min and max limit ResSim applied at each reservoir, plus the mainstem targets |
| `junctions.csv` | local, cumulative local and total flow where a local flow is defined |
| `diversions.csv` | what each diversion moved, and what DiversionFromCSV asked for |
| `rules.csv` | the value every reservoir rule returned each day |
| `modelReport.json` | the active operation set: each zone's rules in stack order (copied from the simulation folder) |
| `*_series.csv` | the DSS pathname and units behind every column |
| `run_info.json` | simulation, alternative and watershed, used by `check_model.py` |

`check_model.py` adds to the newest of those folders:

| File | Contents |
|---|---|
| `report.html` | every summary table, with links to the plots |
| `<check>_summary.csv` | one row per reservoir, diversion or rule |
| `release_decisions/<reservoir>.csv` | per day: elevation, inflow, outflow, min and max limit, and the value every rule asked for |
| `plots/Reservoir - <name>.html` | one page per reservoir, three panels: elevation (with rule curve and FIRO target); flow (outflow, inflow, limits, every rule's value); release decisions (a bar per rule, coloured by its status, breaking only where the status changes). The release decision table sits underneath, one column per rule, cells shaded by status |

In the plots, pick an element from the dropdown and click legend entries to
hide or show them. On the reservoir plot's flow panel only the outflow and the
min and max limits start shown; turn on rules from the legend. Hover the
outflow to see which rules were **in control** that day (their value equalled
the outflow). The decision table under the plot has every rule's value every
day whatever is shown, each cell shaded by the rule's status. Date, Elevation,
Inflow and Outflow stay in place while the zone, limits and rules scroll
sideways. Click a day on
the plot to jump to it in the table; click a row to mark that day on the plot.

**Open table in its own window** puts the table in a window of its own, to
fill a second screen. Clicks still link both ways, the window follows the plot
when you pick another reservoir, and closing it puts the table back under the
plot. The two windows talk through the browser's local storage, which works in
Chrome and Edge for pages opened from disk; Firefox keeps each local file
separate, so there the windows will not link.

**Sub-daily runs** work: dates carry the time of day, and counts and volumes
use the run's time step (counts are still reported in days). Each reservoir
page holds the whole run, so it grows with it: about 5 MB a year of 3-hour
results at a reservoir with around 15 rules. Set `START_DATE` and `END_DATE` at the
top of `check_model.py` to look at part of a long run.

## How a release decision is read

Each rule's value that day is compared with the outflow. None of this needs
the rule priority order.

| Rule's value | Outflow | Status |
|---|---|---|
| equal | | **in control** |
| above | at the max limit | **capped** by the rule whose value equals the max limit, or by *outlet capacity* if no rule's does |
| below | at the min limit | **held up** by the rule whose value equals the min limit |
| above or below | between the limits | **set by another rule** (scripted and guide rules only) |

A built-in min rule below the outflow, or a max rule above it, is satisfied
and not shown. The guide releases are ResSim's `<zone>-ZBOp Rule` series: what
the guide curve asks for when nothing else acts. At low flows several rules
often share a value, so "set by" can name more than one.

It reads the config files the alternative uses (`scripts/alt_config/<alternative>.txt`
over `_default.txt`), from the watershed if it is on this machine, otherwise
from this repository's `data/` folder. The report lists the files it used.

## The checks

**FIRO_SPACE.** Two separate questions:

- *Achieving:* is the pool within `ELEV_TOL_FT` of the target, and how far
  above or below it does it get?
- *Targeting:* did the outflow obey the FIRO rule's own value that day?
  `rule_overridden_days` counts days another rule won. Needs `rules.csv`.

**MinFlow.** Minimum flow plus withdrawal from the config, against the outflow
where it is met (Foster for Green Peter). A shortfall is explained when the max
limit was below the requirement. `rule_attached` says whether
MinFlowPlusWithdrawal runs at that reservoir in this alternative, and
`other_rule` compares any other min-flow rule to the same numbers.

**Diversions.** Whether DiversionFromCSV wrote the config value to its rule.

**Rule stack.** Each reservoir's rules in each zone, top of the stack first,
from `modelReport_<alternative>.json`, which `Alternative_Setup` writes on
every compute (the active operation set, zone by zone). The extract looks for it
in the watershed's `rss` folder, then the simulation folder
(`MODEL_REPORT_DIRS` in `extract_dss.py`), and copies it in as
`modelReport.json`; without it the check runs as before, just with no stack. It
also pulls each zone's top
elevation (`<reservoir>-<zone> Elev-ZONE`) so the check knows which zone, and
so which stack, applied each day. The reservoir page orders rules by the stack
of the zone the pool spent longest in, puts a `Zone` column in the table, shows
each rule's place in each zone under its name (`RC 3 · TOD 5`), and greys out a
rule on days its zone's stack does not include it. `in_results` flags a rule
in the operation set that saved no values. With the model report, the rules shown
on the reservoir pages are the stack's: a rule deleted from the stack is left
out even if an earlier run left its values in the DSS, and a rule in the stack
that never returned a value still gets its (empty) row, line and table column.

**Conflicts.** For every rule, how many days it was capped or held up, by
what, and the total volume between what it wanted and what was released.

**RuleControl.** For every rule at every reservoir, the days its value equalled
the outflow. Several rules can tie on a day (a min and a max both at 50 cfs,
say), and each is counted. `(no rule equal to outflow)` counts days no rule
matched. Needs `rules.csv`.

Tolerances, rule names and the start date are set at the top of
`check_model.py`.
