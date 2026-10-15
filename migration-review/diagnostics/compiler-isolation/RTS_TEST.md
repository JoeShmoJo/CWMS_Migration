# RTS 3.6.0 / ResSim 4.1.2 test

This is an experimental compiler-only patch. Reuse the existing RTS test forecast;
no new watershed or installation copy is needed. The original JAR is automatically
archived and verified before replacement. No forecast file, scripted rule, JRE,
launcher, thread limit, or RTS configuration is changed.

1. Finish computes and close CWMS/RTS and every ResSim application.
2. Run the installer below. It accepts only the inspected original 4.1.2 JAR.
3. Restart RTS from the same installation, open the existing test forecast, and
   launch its ResSim editor. Use ResSim's native ensemble multithread compute as
   in the previous test. Installing this patch does not change CWMS ensemble
   orchestration or enable parallel compute by itself.
4. Start with a few members known to have inputs for the full simulation window
   (for example 1983-1986 if covered). Confirm the launcher identifies multithreaded
   ensemble compute. The V2 active marker must name the RTS 4.1.2 JAR. It appears
   when a scripted rule is compiled; startup alone may not emit it.
5. Require completion for every member, check error/cleanup logs and fresh output
   coverage, and compare reservoir outflows and Salem against an equivalent serial
   run. Preserve each result separately. Then test the larger ensemble. Partial
   outputs or 100% progress alone do not prove success.

Install (PowerShell one line):

```powershell
Set-Location "C:\Projects\A_REPOSITORIES\CWMS_Migration"; git pull --ff-only; if ($LASTEXITCODE -ne 0) { throw "Git pull failed" }; & "$env:LOCALAPPDATA\miniconda3\envs\hydro39\python.exe" ".\migration-review\diagnostics\compiler-isolation\install_rts_compiler.py" --installation "C:\Mobile_Programs\rts-install-package-3.6.0\HEC-RTS-3.6.0"
```

The installer prints its `BACKUP` directory. Backups are below
`HEC-ResSim\4.1\compiler-isolation-backups`, outside JAR loading directories.
The receipt records both hashes and the original JAR is retained. For this
compiler-only change, that archive is the required rollback backup; it is not a
backup of forecast data or other independent model edits.

After closing RTS and ResSim, restore the most recent archive (PowerShell one line):

```powershell
Set-Location "C:\Projects\A_REPOSITORIES\CWMS_Migration"; $install = "C:\Mobile_Programs\rts-install-package-3.6.0\HEC-RTS-3.6.0"; $backup = Get-ChildItem -LiteralPath (Join-Path $install "HEC-ResSim\4.1\compiler-isolation-backups") -Directory | Sort-Object Name -Descending | Select-Object -First 1; if ($null -eq $backup) { throw "No compiler backup found" }; & "$env:LOCALAPPDATA\miniconda3\envs\hydro39\python.exe" ".\migration-review\diagnostics\compiler-isolation\install_rts_compiler.py" --installation $install --restore $backup.FullName
```

If a Java process is reported, close its owning application normally and retry.
The tool never kills processes. If version validation fails, keep the original
installation and provide the error; do not substitute a standalone application JAR.

## Worker count for the first trial

The installer deliberately leaves thread settings alone. Before computing, inspect
ResSim's launcher message for the actual worker count. The inspected 4.1.2 executor
reads the JVM property `ResSim.ComputeThreadCount` when constructing its pool.
In the **ResSim** Script Editor, before the first multithread compute in the new
session, a session-only limit can be set without editing RTS launcher files:

```python
from java.lang import System
System.setProperty("ResSim.ComputeThreadCount", "4")
print("Requested worker limit: " + System.getProperty("ResSim.ComputeThreadCount"))
```

This must run in the ResSim JVM, not the CWMS/RTS script console. It cannot resize
an already-created pool. Check the compute launch message to confirm the actual
count; restart ResSim if the pool already exists. This runtime setting does not
persist when ResSim exits. Four workers provide a small first trial; eight can be
tried after validation.

For HEC, share `HEC_COMPILER_ISOLATION_REPORT.md`, the helper Java source, and the
minimal reproduction sources in `../jython-cleanup/`. No patched vendor JAR needs
to be sent. The report distinguishes completed standalone checks from pending
native RTS validation.
