# Experimental standalone 4.1.0 compiler isolation

This is an unsupported diagnostic patch for a separate installation copy. It is
not a validated ResSim fix and must not be used for operational results.

## Why

The inspected 4.1.0 compiler helper hec.rss.model.z.a(String, String) constructs a
default PythonInterpreter, compiles code, and closes the interpreter on both
success and exception paths. A default interpreter can share PySystemState with
live rule interpreters. Closing it can close their files or run threading exit
handlers while ensemble workers remain alive. Windows traces show both patterns.

The patch substitutes only that compiler allocation with
cwms.diagnostics.IsolatedCompilerInterpreter. This subclass constructs a private
PySystemState and restores the caller state in finally after close. Model rule
interpreters and compilation calls remain otherwise unchanged. The class prints
EXPERIMENTAL COMPILER ISOLATION ACTIVE and its source JAR location when loaded.

## Scope and guards

prepare_compiler_test.py takes --installation and --destination. It copies the
entire installation into a new, nonexisting directory outside the source tree,
then modifies only the copied jar/ResSimApp-4.1.0.jar. It retains an original JAR
backup in the copy and writes compiler-isolation-test.json after preparation.
It does not launch Java, compute, or modify model files or the original install.
Do not launch an incomplete destination if preparation raises an error.

The application JAR is pinned to SHA-256:
6b18183e72d236940bf780655c816eca4ccc6939766b4e676446431db8359c3d
Other versions and signed JARs are rejected. The class patch adds three constant
pool entries and changes only NEW and its constructor call in the exact compiler
method. Code size, branches, exception ranges, and stack maps stay unchanged.
Only hec/rss/model/z.class changes; one new helper class is added. No other
application JAR entries change. The bundled helper was compiled against Jython
2.7.2 with Java 8 class format and tested on Java 21.

## Windows test

1. Close all standalone ResSim and RTS/ResSim processes.
2. Run prepare_compiler_test.py using Python 3.9+; supply the original standalone
   installation and a new destination outside it. This requires space for a full
   installation copy. It does not alter RTS.
3. Launch the ResSim executable from the copied directory directly, not from a
   shortcut or CWMS. Open only a disposable test watershed/simulation.
4. Confirm the active marker in the ResSim console names the copied application
   JAR. If it does not, stop: the intended compiler patch has not been exercised.
5. Keep current diagnostic scripts, members, inputs and time window fixed. Test
   the same 2000-2003 members sequentially, then restart the copied application
   and test those members in parallel. Preserve complete logs for both.
6. Require all member completions and fresh full-window outputs, including CSV
   cleanup. Existing DSS record presence or a few completion messages do not
   establish overall success. Compare pool elevations/outflows to sequential
   outputs before restoring additional rule families or expanding member count.

Do not restore removed rule families in this first experiment: that changes
multiple variables. A successful diagnostic compute still has invalid operating
results when operating rules/diversions are absent. Validation with all intended
scripts and identical serial/parallel outputs is a separate necessary step.

Rollback: close the test application and use the untouched original executable.
Do not copy the patched JAR into the original installation or RTS. Keep test model
changes and outputs separate from normal work.

## Local verification, 2026-10-14

- Three Python tests passed: unknown binary rejected, existing destination
  rejected, source unchanged, and exact JAR entry scope preserved.
- javap comparison shows only the compiler NEW and constructor owner change.
- CompilerIsolationCheck passed 50 concurrent cycles on Java 21 / Jython 2.7.2:
  live files remained readable, compiled PyCode executed in the caller, syntax
  exceptions propagated, and caller state was restored. The final bundled
  helper including its active marker was tested.
- Minimal cleanup reproductions are in ../jython-cleanup.
- Actual native ResSim compute cannot be executed in the Linux cloud environment.
  Windows application startup, native compute and model output equivalence remain
  unverified. Shared module globals, forced reloads and other concurrency hazards
  may require additional fixes even if compiler teardown is addressed.

## Rebuild and checks

From the repository root, with an existing Jython 2.7.2 standalone JAR:

    javac -source 8 -target 8 -cp JYTHON_JAR -d BUILD_DIR migration-review/diagnostics/compiler-isolation/IsolatedCompilerInterpreter.java

Package only cwms/diagnostics/IsolatedCompilerInterpreter.class into
isolated-compiler-helper.jar. To compile the Java check, include that helper JAR
and JYTHON_JAR; run CompilerIsolationCheck with both and the check class directory
on the classpath. On Windows classpath entries use semicolons.

    python migration-review/diagnostics/compiler-isolation/test_prepare_compiler_test.py

No Java compiler is required on the Windows test machine to run the installer;
it uses the bundled helper class. Do not bundle unrelated dependencies.
