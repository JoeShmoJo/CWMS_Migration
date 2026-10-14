# Temporary compiler closes a live interpreter's files

Prepared from ResSim 4.1.2 / RTS 3.6.0 investigation. No vendor files were modified.

## Observed in Windows

The native ensemble launcher starts concurrent workers. Both adapted rules and,
following a verified original-rule installation and process restart, original
rules encounter an unfinished compute. The original-rule thread dump on
2026-10-14 (PID 38404) shows one worker in:

    ScriptOpRule.compileScript
    hec.rss.model.z.a
    PythonInterpreter.close / cleanup
    PySystemState.callExitFunc
    threading._MainThread.__exitfunc
    Thread.join

The other five workers are idle in ThreadPoolExecutor.getTask; the launcher waits
in ExecutorCompletionService.take. Earlier adapted-rule runs also reported closed
files in FIRO_SPACE, MinFlowPlusWithdrawal, and cLoadModules. Idle workers alone do
not establish whether their members succeeded or failed.

## Bytecode evidence

In the supplied ResSimApp-4.1.2.jar, ScriptOpRule.getInitializedInterpreter creates
PythonInterpreter() without an explicit PySystemState. Its compiler delegates to
hec.rss.model.z.a(String, String), which creates another PythonInterpreter() and
closes it after compilation, including exception paths. Jython's default
constructor uses Py.getSystemState(). Thus these interpreters can share state;
closing the temporary compiler runs cleanup on that state.

## Minimal reproduction

CompilerCleanupProbe.java needs Java 11+ and an existing Jython standalone JAR;
it does not need ResSim, native DLLs, a watershed, or network access. It creates
one temporary text file and removes it on successful completion. No JARs are
bundled or changed.

Compile (replace JYTHON_JAR with the local JAR path):

    javac -cp JYTHON_JAR CompilerCleanupProbe.java

On Windows, run:

    java -cp "JYTHON_JAR;." CompilerCleanupProbe
    java -cp "JYTHON_JAR;." CompilerCleanupProbe isolated

On Linux use ':' instead of ';' in the classpath.

The default case must print shared state true and live rule file closed true.
This reproduces premature resource cleanup. The isolated case must print false
for both and verify the file remains readable. Both cases use assertions that
fail if the expected distinction disappears. PASS in the first case means the
bug was reproduced, not that application behavior is correct.

## Limits and proposed vendor investigation

The file probe reproduces resource cleanup independently of threading.
IdleCleanup.java additionally reproduces the blocking stack pattern without HEC
classes: preload threading on the host, retain a registered pool worker, then
close a compiler using the shared state on another worker. It waits five seconds
for completion, prints STALLED and worker stacks, and exits with code 2 when the
stall is reproduced. It explicitly terminates its own test JVM. Compile/run it
with the same classpath recipe as CompilerCleanupProbe.
The saved thread-result-jython-2.7.3.txt captures a reproduced stall on Java 21.
This is a minimal analogue, not an execution of the proprietary ResSim compiler. Per-worker state
isolation previously failed to prevent the ResSim stall and is not a validated
fix. Compiler-specific state isolation in this probe is a different boundary.

Ask HEC to investigate whether compilation can avoid closing the active rule
runtime: for example an explicitly isolated compiler state with prior thread
state restored on all paths, or a compilation API without interpreter teardown.
Any change needs testing for imports, compiler settings, threading exit hooks,
file ownership, and serial/parallel output equivalence. We have not modified
vendor bytecode, disabled cleanup, or established a supported application-level
fix. Keep normal work on sequential compute for now.

## Local validation

CompilerCleanupProbe shared and isolated cases both passed their expected
assertions on Jython 2.7.2 and 2.7.3 using Java 21. The shared case closed the
live file; the isolated case preserved and successfully read it.

IdleCleanup also reproduced the stalled Thread.join / idle executor pattern on
Jython 2.7.2, exiting with the expected diagnostic code 2. Its saved stack is in
thread-result-jython-2.7.2.txt. The `isolated` argument tests compiler-specific
state isolation while keeping the worker pool and live runtime unchanged.
The isolated compiler variant completed on Jython 2.7.2 with exit code 0. This
validates a potential fix boundary in the analogue only; it is not a ResSim fix.
