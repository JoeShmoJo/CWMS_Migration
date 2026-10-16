# RTS workflow documentation

Use these current documents together:

- [Operator SOP](RTS_OPERATOR_SOP.md): the short procedure from initial extract
  through baseline, augmentation, a new baseline/scheme, and plotting.
- [Process and file reference](RTS_WORKFLOW_REFERENCE.md): inputs, outputs,
  locations, producing/consuming programs, configuration provenance and limitations.
- [Data I/O audit](RTS_DATA_IO.md): compact archives, legacy DSS compatibility,
  staging/backup behavior and the focused backend update.

These supersede earlier descriptions of the larger multi-button menu, routine
full-DSS result snapshots, broad baseline fingerprints, and Reset Baseline as a
main-window button.

## Current menu

Run installed `scripts\RTS_WORKFLOW_MENU.py` from the RTS watershed Script Editor.
The four main actions are:

| Action | Purpose |
| --- | --- |
| Initial Extract | Download/archive inputs and load the completed extract; compute manually afterward |
| Baseline Configuration | Edit/save reusable scripted-rule settings and apply a forecast-scoped set with augmentation disabled |
| Augmentation Configuration | Accept completed results if requested, configure/process/load releases against the saved baseline |
| Plot Results | Accept completed results if requested, choose one/two archived runs, plot or delete an augmented result |

Greyed-out metadata identify the selected forecast. Refresh after selection/date
changes. Compute remains a normal RTS/ResSim action; no menu task starts it.
“Yes” in the completion question means the operator confirms successful compute
and requests capture. “No” uses saved results without accepting current live
outputs. “Cancel” stops. Finish compute and close DSS views before file operations.

Saving configuration, applying/loading it, computing, and accepting outputs are
separate steps. Use the SOP for their order. New captures retain selected full
series in `series.npz` plus `run-archive.json`. These are primary data; do not
remove them as disposable caches. Older full-DSS archives and their rebuildable
`run-data-cache-C0` folders remain supported.

Baseline equality compares pool elevation/outflow timestamps, values, units and
types, not every model/configuration/input variable. It preserves the existing ID
when those outputs match. The reference documents the input-only-change caveat,
including water-year type. No operation-set selection/stack order is restored
from result archives.

## Related installation/development material

- [Forecast extraction](FORECAST_EXTRACTION.md): original plan/test launcher and
  downloader details; the operator SOP describes the menu's extract-and-load action.
- [Baseline configuration](RTS_BASELINE_CONFIGURATION.md): adapter/editor setup and
  historical performance diagnostics.
- [Augmentation backend](RTS_AUGMENTATION.md): calculator/background CLI material.

Installer scripts print backup locations. Updating kit files does not update
installed watershed scripts. See the reference for installation boundaries and
shared versus per-forecast files. This workflow does not require the experimental
application JAR patch.

Optional developer Swing smoke check (not an operator step):

```sh
java -Djava.awt.headless=true -jar /path/to/jython-standalone-2.7.3.jar tests/check_swing_configuration.py
```
