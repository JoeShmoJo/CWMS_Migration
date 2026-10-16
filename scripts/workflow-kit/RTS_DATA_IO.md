# RTS data I/O and compact completed-run archives

## Changes

New accepted baselines and augmented results are primary compressed-array archives,
not full copies of forecast.dss. The archive contains `series.npz` and
`run-archive.json`, plus existing baseline/result provenance and configuration
metadata. The manifest preserves logical DSS pathnames, timestamps, units, data
type, timezone and array checksum. Its hash is the compact archive identity.

Capture scans the catalog once and reads each selected physical date block once.
Overlapping blocks are merged with conflict checking. Missing samples stay missing;
no interpolation or time extension is introduced. Required-record failures abort
capture. Optional rule/state records that cannot be read are explicitly recorded
as unavailable, rather than invented.

Scope: computed ensemble records for the accepted run code (all cataloged members
of that run), limited to pool elevation/outflow and configured plot control-point
flows; storage/inflow for augmentation reservoirs; Combined Min Trib requirements;
and water-year type. Powerhouse, tailwater, diversion/return, unrelated routing
reach, other run-code, and DSS rule-curve records are excluded. Rule curves for
plots continue to come from the annual CSV.

## Process audit

| Step | DSS work retained | Work avoided |
| --- | --- | --- |
| Initial extract | Seed a separate staged DSS to preserve existing/unmanaged inputs; write required downloaded/shared inputs; verify before promotion | Loading the extract now keeps rollback by renaming the old live DSS, avoiding a second backup copy |
| ResSim compute | Normal native DSS input/output | No change to scripted rules or postprocessing |
| Accept baseline | One catalog-only inspection, then one selected-block capture from live DSS | No full DSS snapshot; no second DSS value pass for fingerprinting/cache warming |
| Accept augmented result | One selected-block capture | No full DSS snapshot or whole-file content hash; unchanged compact results reuse their prior archive |
| Compare baseline versions | Pool elevation/outflow arrays | No DSS reads for compact versions |
| Prepare augmentation | Baseline arrays; write only prepared minimum-release records to augmentation.dss | No baseline DSS reads for compact versions |
| Load scheme | One full staging copy, write only manifest-listed augmentation records, verify, retain original via rename | No separate full backup copy |
| Disable augmentation | Marker change; compact baseline mode retains live DSS inputs and requires unaugmented recompute | No archived-output reload for compact baselines |
| Plot archived runs | Verified arrays and rule-curve CSV | No DSS reads for compact archives, including baseline inspection |
| Plot live forecast through legacy CLI | Selected live output reads; CSV rule curves by default | Broad output reads and absent-rule-curve searches remain excluded |

Live scheme loading still stages a whole DSS because overwriting the live file
in place could leave partial releases after a failed write. The original is
renamed into its unique recovery backup immediately before promoting the staged
file. A caught promotion failure restores it. An interruption between renames may
require restoring that backup manually. Existing backups are not automatically
deleted. Initial extraction's seed copy is retained for input compatibility; this
change does not assume every existing input can be regenerated from downloaders.

## Compatibility and integrity

- Existing full-DSS archives, scheme hashes, baseline versions, and plots remain
  supported and unchanged. Their disposable caches can still rebuild from DSS.
- Compact archives are primary data, not disposable caches. Corrupt primary arrays
  fail verification; the workflow never silently substitutes current live results.
- Unchanged elevation/outflow fingerprints keep the existing baseline identity.
  No existing archives are converted or deleted. Consequently, an unchanged legacy
  baseline may remain DSS-backed even after a new compact capture is compared.
- Old augmented results keep their original baseline pairing and Previous baseline
  labels when a changed baseline is accepted.
- A compact baseline has no archived simulation-input DSS to load. Baseline mode
  disables augmentation and retains live inputs, then requires a new unaugmented
  compute. Legacy full-DSS baseline loading retains its earlier behavior.
- Source size, modification time and change/creation time are checked around
  capture. These detect ordinary concurrent writes, not changes deliberately
  made while preserving all timestamps. Finish compute and close DSS views before
  accepting; archive data hashes verify the retained contents afterward.
- Freshness still depends on operator confirmation. Old DSS records can survive
  failed computes. No log or catalog check certifies every member's success.

## Install and try in the existing test forecast

Finish compute and close the workflow menu; no new watershed copy is needed.
The focused installer backs up only the affected Python workflow files. It does
not touch the Java patch, operating-rule scripts, configurations, DSS files,
existing archives, or the PostProcess_CSV cleanup script.

PowerShell one line:

```powershell
Set-Location "C:\Projects\A_REPOSITORIES\CWMS_Migration"; git pull --ff-only; if ($LASTEXITCODE -ne 0) { throw "Git pull failed" }; & ".\migration-review\Install-RunArchives.ps1" -WatershedRoot "C:\CWMS\watershed\ResSimMaster"
```

Reopen the workflow menu and accept a completed unaugmented run, then prepare/load
augmentation and compute normally. Accept the augmented result and plot it with
the baseline. Look for `Compact archive: ... No DSS snapshot copied.` The log
reports selected series, successful DSS block reads, and compressed-array bytes.
An unchanged old baseline can remain legacy-backed; new augmented results will
still be compact. Existing archives need not be removed to test this.

Verify the new result folder has `series.npz` and `run-archive.json`, rather than
`forecast.dss`. Plot it again: the compact path should not print DSS zread output.
Native Windows timing and file-lock behavior require user testing.

The installer's printed backup directory contains `files.json`, including which
files existed beforehand. To restore, close the menu, copy back those originals,
and remove only files marked newly installed. Existing pre-change backends cannot
read compact archives, so reinstall the new backend when viewing newly archived
runs. Do not delete primary compact arrays to clear a cache.

## Validation

120 Python tests passed, including legacy archive compatibility, selective capture,
block merging, changed-source rejection, checksum failures, unchanged/changed
baseline identity, retained live inputs in compact baseline mode, duplicate result
reuse, and rollback on failed candidate promotion. Augmentation preparation runs
twice with exactly equal generated tables; the second run forbids baseline DSS
reads. Saved-run plots are generated with live DSS removed and DSS opens forbidden.
Windows pydsstools I/O is represented by test doubles in cloud tests; native RTS
verification is still required. NumPy/Pandas remain the storage dependencies;
no new Windows package is introduced.
