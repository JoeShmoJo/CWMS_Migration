# Coupled diversion and withdrawal switch (standalone sandbox)

This experiment copies the current watershed and patches only the copied
`DiversionFromCSV` and `MinFlowPlusWithdrawal` modules. Use the working V2
ResSim installation. It does not modify an installation, start a compute,
or change the original watershed. Known absolute text references to the source
watershed are rebased to the copy; external dependencies remain external.

`prepare_diversion_switch.py --watershed SOURCE --destination NEW_DIRECTORY`

The copy contains `scripts/diversion-demands.json`:

```json
{
  "diversion_demands_enabled": true
}
```

- `true`: existing diversion, return, and added withdrawal behavior.
- `false`: every DiversionFromCSV rule specifies zero flow, including negative
  returns. No diversion schedule CSV is loaded. Combined Min Trib keeps its
  minimum-flow schedule and downstream target calculations but skips the
  withdrawal schedule and its contribution to releases.

This controls these two scripted rule families, not unrelated diversion rules,
fixed model demands, or physical outlets. Rule objects and stacks stay in place.
Minimum-flow CSVs remain required. Invalid or missing switch files stop
initialization rather than silently choosing an operating mode.

Edit only between completed computes. The setting is read during initialization,
then stored on each rule; there is no per-timestep file access or shared mutable
configuration cache. Every initialization replaces the previous demand state.
Close and reopen ResSim before the first sandbox test so imported modules belong
to the copied watershed. Use a fresh application session when moving back to the
working watershed too. Do not use the timing-instrumented watershed as input.

First run with ON and compare the copied outputs against the working ON run.
Then save the ON DSS separately, change to OFF, and rerun the same members/window.
OFF intentionally changes flows: inspect diversion/return zeros and retained
minimum targets; record compute time. Finally turn ON again to check restoration.
Retain separate output files so old DSS results cannot masquerade as fresh runs.
Native Windows ResSim validation and timing remain user-run checks.

This first version is a standalone sandbox setting. Integrating it into the RTS
baseline editor and archiving its value with baseline configurations is follow-up
work; do not install it into RTS as a substitute for that integration.

Validation: tests exercise negative returns, positive demands, ON/OFF/ON reuse,
minimum-only operation, blank minimum days, downstream target handling, strict
booleans, and source/DSS preservation by the installer. No speedup is claimed
before a native compute measurement.
