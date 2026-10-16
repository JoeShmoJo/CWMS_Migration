# Optional diversion and return postprocessing

This is an opt-in experiment, separate from the established standalone and RTS
menus and archives. It reads completed DSS results, follows the supplied network
export, applies generic-year diversion/return schedules and optional reservoir-
elevation withdrawal reductions, and writes separate adjusted flow CSVs/audits.
No source DSS records or native rule bindings are changed by the postprocessor.

Open [the complete procedure](optional-diversion-postprocess/README.md), including
network barriers, signs, double-subtraction prevention, timestamp conventions,
configuration fields, PowerShell command and all input/output locations.
The initial method is same-timestamp bookkeeping, stops at reservoirs and does
not reproduce Muskingum routing or reservoir feedback. Example conditions are
disabled until configured. The tool does not automatically feed adjusted results
into augmentation or existing plots.

The baseline editor also supports adding inactive IRRM and Deep Drawdown entries
for any of the 13 reservoirs. A real target elevation and native rule binding
are still needed. Existing operating settings are not automatically expanded or
activated; new Deep Drawdown seasonal fields must be reviewed.
