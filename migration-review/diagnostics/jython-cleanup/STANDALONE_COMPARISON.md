# Working ResSim 3.5 script snapshot comparison

Source: standalone-script-review-d65726c2-82e2-4235-8f35-6b73e4724c3b.zip
from remote forecast-extraction-context, inspected 2026-10-14. Compare Python
text with normalized line endings against standalone-review/scripts (the
maintained pre-adapter snapshot), not against an unverified live Windows tree.

- Alternative_Setup.py and ControllerExternalSV.py are identical.
- Four of five externalSV Python files are identical. baseExternalSV.py differs
  in compatibility imports for relocated Java classes (LocalTSRecordImpl and
  removal of unused TSDataSet import).
- The older externalRules folder lacks FIRO_SPACE.py, MinFlowPlusWithdrawal.py,
  and DiversionFromCSV.py. Eight common substantive rule modules changed.
  Thus the old watershed is not an equivalent workload, even apart from version.
- Old NWDJyLib imports logging in multiple utilities. Logging can import
  threading; absence of explicit 'import threading' in a rule is insufficient to
  rule out Jython threading exit hooks. Do not remove logging on this evidence.
- The current repository snapshot does not contain NWDJyLib, so its current
  cFile/cLoadModules contents cannot be compared from this ZIP alone.

Conclusions: no evidence that ControllerExternalSV or Alternative_Setup changes
introduced the issue; no equivalent 3.5/4.1 test is established. A blanket swap
of older scripts would remove rules and change model behavior. Prefer comparing
3.5 compiler lifecycle to 4.1.2, or testing compiler-only isolation in a separate
installation copy. Local Jython reproductions establish a plausible cleanup
mechanism, not a validated patch to ResSim.
