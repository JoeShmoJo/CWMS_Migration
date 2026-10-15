# Experimental standalone 4.1.0 compiler isolation — V2

Unsupported diagnostic patch for a separate installation copy. Not a validated
ResSim fix or an authorization to use its results operationally.

Update 2026-10-15: the standalone V2 test completed with all intended rules,
and the user reported exact agreement for 602/602 reservoir outflow/Salem series
against serial. The separately requested RTS 4.1.2 trial now has a reversible
JAR-only installer: see [RTS_TEST.md](RTS_TEST.md). Do not copy the standalone
application JAR into RTS. The current vendor-facing evidence and limitations are
in [HEC_COMPILER_ISOLATION_REPORT.md](HEC_COMPILER_ISOLATION_REPORT.md).

## Change

ResSim's hec.rss.model.z.a(String, String) constructs a default interpreter,
compiles, and closes it. Default interpreters can share state with live model
scripts. Windows traces and local reproductions show premature file cleanup and
threading exit-handler waits. The patch changes only that compiler allocation.

V1 created and cleaned up a separate runtime on every compilation. It completed
15 Windows workers but suffered substantial initialization cost with more
workers. V2 retains one private PySystemState per Java worker thread and creates
a fresh lightweight interpreter wrapper for each compilation. Fresh globals and
compiler flags prevent future-import settings leaking between scripts. close()
restores the caller state without cleaning up the cached compiler environment.
Nested use restores the enclosing state correctly. Model code still executes in
its original interpreter, never in this compiler cache.

Cached module state remains until worker/JVM lifetime ends; it is bounded by the
number of worker threads, not members or rule invocations. It deliberately avoids
per-compilation cleanup. This is for the inspected native compile-only call path,
not arbitrary Python execution or a general interpreter replacement. Additional
shared module state and model script concurrency hazards may still exist.

Active console marker:

    EXPERIMENTAL COMPILER ISOLATION V2 ACTIVE (cached per worker): <JAR location>

## Preparation

Use Python 3.9+ to run prepare_compiler_test.py with --installation ORIGINAL,
--destination NEW_DIRECTORY and optionally --threads 8. Source must be the
untouched standalone 4.1.0 installation, not V1 or an RTS installation. Destination
must be new and outside the source tree. Space for a full installation is needed.

The installer copies the entire installation and modifies only the copied
application JAR and, if requested, copied launcher thread limit. The original
application and launcher remain unchanged. With --threads it locates exactly
one root .config whose mainclass is hec.rss.client.RSS, removes existing worker
property lines in that file and appends the requested property after includes.
It retains the copied original JAR as .jar.original and writes
compiler-isolation-test.json with version 2 and the requested thread limit.
No compute starts and no model file changes. Discard incomplete destinations if
preparation raises an error; do not launch them.

Application JAR SHA-256 is pinned to:
6b18183e72d236940bf780655c816eca4ccc6939766b4e676446431db8359c3d
Other versions and signed JARs are rejected. The bytecode edit changes only NEW
and its constructor owner in the exact compiler method. Code length, branches,
exception ranges and stack maps stay unchanged. Only hec/rss/model/z.class
changes; the helper and its ThreadLocal implementation class are added. All
other application entries are byte-for-byte unchanged.

## Windows comparison

1. Close standalone ResSim and RTS/ResSim. Prepare a new V2 copy from the original
   installation; keep V1 for comparison. Launch V2 directly from its new folder.
2. Open only the diagnostic model. Preserve the same script edits, removed rules,
   input data, window and members for a controlled comparison.
3. Confirm the V2 active console marker names the new JAR and the compute launcher
   uses eight workers. Stop if the intended patch is not active.
4. First test 2000-2003, requiring every member completion and no errors. Then
   test the same 1982-2024 one-month window at eight workers. V1 user-reported
   reference is 526 seconds. Compare total elapsed time, not CPU utilization.
5. Preserve complete logs and verify fresh full-window outputs. Old DSS record
   presence and a few completion messages do not establish full success.

A successful reduced model still lacks intended operating rules. Restoring
all rules and comparing identical serial/parallel outputs are separate
validations (subsequently completed for the standalone scope noted above).
To roll back standalone, close V2 and launch the untouched original executable.
Use only the version-specific installer and restore procedure for the RTS trial.

## Verified locally, 2026-10-14

- Installer tests pass: unknown binary refused, existing destination refused,
  source application/config unchanged, correct copied thread limit, exact JAR
  entry scope (including nested helper class).
- Java 21 / Jython 2.7.2: 50 concurrent cycles with distinct model states and
  another 50 with shared caller state passed. Checks cover private per-worker
  cache identity, nested compilation, executable compiled code, live config
  files, syntax errors/recovery, fresh future flags, and caller restoration.
- V2 adapter benchmark: 120 simple compilations over four workers in 0.998 sec.
  V1 reference was 12.369 sec. Neither predicts native full-run speedup.
- Subsequent native Windows standalone V2 compute: user-reported 131-133 seconds
  at eight workers versus 286 seconds serial; exact 602/602 flow-series match.
  Native RTS 3.6.0 / ResSim 4.1.2 validation also completed: six members
  (2000-2005), six threads, 34 seconds, and all 84 compared flow series matched
  serial exactly. Long-session/shutdown memory behavior remains unverified.
  Original Windows evidence and local cleanup reproductions are in ../jython-cleanup.

## Rebuild/check

Compile IsolatedCompilerInterpreter.java against a local Jython 2.7.2 JAR using
Java 8 bytecode target (-source 8 -target 8). Bundle both
cwms/diagnostics/IsolatedCompilerInterpreter.class and its $1.class in
isolated-compiler-helper.jar. No Java compiler is needed on Windows to install.

Compile CompilerIsolationCheck.java with Jython and the helper on the classpath;
run it once with no argument, then with shared. Compile/run CompilerCostCheck
with the same dependencies for timing. Its bundled-adapter mode tests the
currently bundled helper, and reuse-prototype is a separate exploratory variant.

    python migration-review/diagnostics/compiler-isolation/test_prepare_compiler_test.py
