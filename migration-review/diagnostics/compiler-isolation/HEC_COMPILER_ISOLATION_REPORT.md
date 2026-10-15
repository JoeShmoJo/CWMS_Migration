# ResSim 4.1 native ensemble compute: experimental compiler fix

Prepared for HEC, 2026-10-15. This is an unsupported experimental workaround.

Tested successfully in standalone ResSim 4.1.0 and RTS 3.6.0's ResSim 4.1.2;
parallel/serial flow comparisons matched exactly in both tests (scope below).

## Observed behavior

In our testing, native multithreaded ensemble compute worked without the scripted
rules that read configuration files and perform related initialization. With
those scripts present, serial compute worked, but parallel compute could fail or
hang. This was observed in standalone ResSim 4.1.0 and RTS 3.6.0's ResSim 4.1.2.
Configuration-file reading is an observed distinction, not an established sole
trigger; the scripts also import modules, initialize logging, and use Jython state.

Failures included prematurely closed configuration files. A Windows thread dump
showed a worker stalled in:

```
ScriptOpRule.compileScript -> hec.rss.model.z.a(String, String)
PythonInterpreter.close / cleanup -> PySystemState.callExitFunc
threading._MainThread.__exitfunc -> Thread.join
```

## Suspected cause and exact change

The inspected `hec.rss.model.z.a(String, String)` creates a temporary default
`PythonInterpreter`, compiles a script, then closes the interpreter. Jython's
default interpreter uses the current `PySystemState`, which can also belong to
live model scripts. Closing the compiler can therefore clean up live files and
invoke threading exit handlers. Independent Java/Jython reproductions confirmed
both premature file cleanup and an analogous cleanup/thread-join stall.

Our V2 patch changes only that temporary compiler allocation to a subclass,
`cwms.diagnostics.IsolatedCompilerInterpreter`. The subclass:

- Retains one private compiler `PySystemState` per Java worker thread.
- Creates fresh interpreter globals and compiler flags for each compilation.
- Restores the caller's state on close, without cleaning up the retained compiler
  state or the live model state. Nested calls restore their enclosing state.

Model scripts still execute in their original interpreters. In the application
JAR, only `hec/rss/model/z.class` changes; the helper and its ThreadLocal initializer
class are added. The edit replaces the `new` instruction's class and matching
constructor owner in the compile method. Code length, branches, exception ranges,
and stack maps are unchanged. No JRE, Jython library, compute algorithm, scripted
rule, or DSS library is replaced. The original JAR is archived for restoration.

V1 created a new isolated runtime per compilation and had excessive initialization
cost. V2 reuses private runtime state per worker while keeping compiler flags fresh.

## Validation

- Local Java 21 / Jython 2.7.2 checks passed 100 concurrent compiler cycles covering
  live-file preservation, worker isolation, nested calls, executable compiled code,
  syntax-error recovery, compiler-flag isolation, and caller-state restoration.
- Standalone 4.1.0, all intended rules present: user-reported 131-133 seconds with
  eight workers versus 286 seconds serial for a one-month, 43-member ensemble.
  All 602 compared series matched exactly: 13 reservoir outflows plus Salem flow
  across members 1982-2024.
- RTS-launched ResSim 4.1.2: six members (2000-2005) completed on six threads in
  34 seconds. The console confirmed the patched RTS JAR was active. All 84
  reservoir outflow/Salem series matched serial exactly over the compared window,
  2026-10-14 00:00 through 2026-11-01 00:00, with no missing-data or coverage failures.

These comparisons cover the selected flows and windows, not every model output.
Long-session resource use and general repeated-compute reliability still need
validation. The cached compiler-state lifetime and a supported alternative to
closing a compiler that shares model state warrant HEC review.

## Review materials and build identity

Helper source: `IsolatedCompilerInterpreter.java` in this directory. Minimal
reproductions: `../jython-cleanup/CompilerCleanupProbe.java` and `IdleCleanup.java`.
The patcher, version checks, tests, and reversible RTS installer are alongside
this report. Operational test/restore instructions are in `RTS_TEST.md`.

Inspected original application JAR SHA-256:

- ResSimApp-4.1.0.jar: `6b18183e72d236940bf780655c816eca4ccc6939766b4e676446431db8359c3d`
- ResSimApp-4.1.2.jar: `5f2841092448f6afa547a7f3f0a83c0f5d06c3c6523dee579f41218be459ed28`

Please review temporary-compiler state ownership and lifecycle, including live-file
ownership, threading exit hooks, compiler flags, and retained-state cleanup.
