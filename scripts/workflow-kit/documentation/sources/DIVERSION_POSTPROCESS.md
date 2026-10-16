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

Baseline configurations now contain inactive null entries for unused IRRM and
Deep Drawdown reservoirs, covering all 13 supported locations. Existing values are
preserved. Off or incomplete entries are neutral, and the browser identifies
their effective state. Null placeholders are kept out
of legacy numeric CSV readers. Native rule attachment still requires ResSim.
