# ResSim 4.1 Jython compiler lifecycle: evidence and experimental workaround

Prepared 2026-10-15 for review by HEC. This is an independently developed,
unsupported diagnostic workaround, not a vendor fix. No claim is made that every
Jython concurrency problem, scripted rule, or output writer is now thread safe.

## Problem observed

Native multithreaded ensemble computations failed or remained unfinished in both
standalone ResSim 4.1.0 and ResSim launched from HEC-RTS 3.6.0 (bundled ResSim
4.1.2). Sequential computations completed. In some attempts the first members
produced outputs, but the entire ensemble did not finish. Existing DSS output
could obscure failed members, so presence of records alone was not accepted as
success.

Windows traces included closed files during scripted-rule configuration loading
and failures involving `PySystemState.unregisterCloser`. A 2026-10-14 RTS thread
dump (PID 38404) showed a worker in this path:

```
ScriptOpRule.compileScript
hec.rss.model.z.a(String, String)
PythonInterpreter.close / cleanup
PySystemState.callExitFunc
threading._MainThread.__exitfunc
Thread.join
```

Other workers were idle in `ThreadPoolExecutor.getTask`; the launcher waited in
`ExecutorCompletionService.take`. That pattern suggests cleanup of shared Jython
state, rather than insufficient CPU parallelism. It does not by itself prove the
status of the other members. Standalone tests also encountered compiler cleanup
problems; removing selected rules or bulk module reloads was not a sufficient fix.

## Inspected compiler lifecycle

The supplied application JARs contain the compile-only method:

```
hec.rss.model.z.a(String source, String filename) -> org.python.core.PyCode
```

For nonempty source, it initializes scripting, constructs a no-argument
`PythonInterpreter`, calls `compile(source)` or `compile(source, filename)`, and
closes the temporary interpreter on both normal and exceptional paths. The
compiled code is returned for later execution in a model interpreter.

Jython's default interpreter constructor obtains `Py.getSystemState()`. A
compiler constructed on a thread with a live model state can therefore share
that state. Closing it can clean up resources owned by live scripts and invoke
threading exit handlers. This is the suspected failure boundary, supported by
the inspected bytecode and independent reproductions, rather than a claim that
all observed failures have one cause.

Minimal non-HEC reproductions are in `../jython-cleanup/`:

- `CompilerCleanupProbe.java`: closing a default temporary compiler closes a
  live interpreter's open file; an explicitly isolated compiler preserves it.
- `IdleCleanup.java`: reproduces a cleanup/thread-join stall with idle executor
  workers. Compiler-specific isolation avoids that stall in the reproduction.

Both were exercised with Java 21 and Jython 2.7.2 and 2.7.3. See the adjacent
README and saved thread-result files for reproduction commands and limits.

## Exact experimental Java change

No JRE, Java executable, Jython distribution, compute launcher, model algorithm,
rule stack, DSS library, or Python configuration loader is replaced by this
patch. Only `ResSimApp-<version>.jar` is modified.

Inside that JAR:

1. Modify `hec/rss/model/z.class` only in the compile method above: change the
   `new PythonInterpreter()` allocation and matching no-argument constructor
   owner to `cwms.diagnostics.IsolatedCompilerInterpreter`.
2. Add `cwms/diagnostics/IsolatedCompilerInterpreter.class` and its anonymous
   ThreadLocal initializer class `$1.class` from the bundled helper JAR.
3. Leave every other original JAR entry byte-for-byte unchanged.

For inspected 4.1.2, `javap -p -c` shows these only instruction changes:

```
16: new           org/python/util/PythonInterpreter
20: invokespecial org/python/util/PythonInterpreter.<init>:()V
```

become:

```
16: new           cwms/diagnostics/IsolatedCompilerInterpreter
20: invokespecial cwms/diagnostics/IsolatedCompilerInterpreter.<init>:()V
```

Three constant-pool entries are appended (UTF8, Class, Methodref). Code length,
branch offsets, exception ranges, and stack maps are unchanged. Existing compile
calls and close calls remain; dynamic dispatch selects the helper's `close()`.
The normal model-interpreter factory elsewhere in `z` is unchanged.

The V2 helper's complete source is `IsolatedCompilerInterpreter.java`:

- One private `PySystemState` is retained in a Java `ThreadLocal` per compiling
  worker. Different worker threads do not share this compiler state.
- Each compilation receives a fresh interpreter wrapper, globals and compiler
  flags. A future import in one script does not change later scripts' flags.
- Construction captures the caller state before activating the compiler state.
- `close()` restores the caller state exactly once. It deliberately does not
  run cleanup on the retained compiler state or on the live model state.
- Nested compilation restores the enclosing compiler state, then the model state.
- Model code executes in its original runtime, not in this compile-only cache.

This lifetime policy is deliberate and limited to the inspected compile-only
call path. Compiler state remains tied to worker lifetime and can remain for the
JVM session when workers are retained. Long-session memory behavior, shutdown,
and unusual import/compiler-extension behavior need vendor review. V2 does not
add general-purpose support for executing scripts in cached interpreters.

V1 used a fresh private state for every compilation; it avoided the original
cleanup boundary in testing but had excessive initialization cost. V2 retains
private module/runtime state while keeping compiler wrappers and flags fresh.

## Binary identity and reversible installation

Only these inspected originals are accepted by the relevant installers:

| Application | Original SHA-256 |
| --- | --- |
| Standalone ResSimApp-4.1.0.jar | `6b18183e72d236940bf780655c816eca4ccc6939766b4e676446431db8359c3d` |
| RTS ResSimApp-4.1.2.jar | `5f2841092448f6afa547a7f3f0a83c0f5d06c3c6523dee579f41218be459ed28` |
| V2 isolated-compiler-helper.jar | `1e6821997caa8a64b53f389ae3db0d6b715e3e4fec03573e6d09c43409605b8d` |

Unknown application versions, signed JARs, already-patched applications, and
unexpected helper contents are refused. Do not transplant 4.1.0's patched JAR
into RTS: 4.1.2 is independently patched from its own original.

`prepare_compiler_test.py` retains the earlier standalone copy-only workflow.
`install_rts_compiler.py` provides the separately requested in-place RTS test:
it builds the candidate first, archives the exact original outside the `jar`
search directory, verifies hashes, writes a receipt, then atomically replaces
only the application JAR. It checks for running RTS/ResSim processes on Windows;
the user must close both before install or restore. The receipt records original,
patched, and helper hashes. Restore refuses to overwrite an unrecognized newer
application and preserves the archive. Models and launcher configuration are
not modified. No compute starts during installation.

Startup/use marker (emitted on first use of the compiler helper, not necessarily
at application launch):

```
EXPERIMENTAL COMPILER ISOLATION V2 ACTIVE (cached per worker): <actual JAR URL>
```

## Validation completed and its scope

### Local Java / installer checks

- Java 21, Jython 2.7.2, actual helper loaded from the patched 4.1.2 JAR:
  50 concurrent compile cycles with distinct caller states and another 50 with
  a shared caller state passed. Checked worker-private cache identity, nested
  restoration, live-file preservation, executable compiled code, syntax-error
  propagation and recovery, fresh future flags, and caller restoration.
- Those checks exercise the bundled helper, not a native ResSim simulation.
- Disassembly of original and patched 4.1.2 showed only the two changed compiler
  instructions described above. JAR entry comparison found only `z.class`
  modified and the two helper classes added.
- Three standalone installer tests and four RTS installer/restore tests passed.
  Tests cover untouched sources, archive integrity, repeated restore, unknown
  binaries, process-check refusal, failed atomic replacement, unchanged sentinel
  model/config files, and refusal of tampered backups or unknown current JARs.

### User-reported native Windows standalone results

With the V2 patch, eight workers, all intended operating rules present, and a
one-month 1982-2024 ensemble (43 members), user reported approximately 131-133
seconds. The same watershed/alternative under original standalone 4.1 serial
reported 286 seconds: approximately 2.2x faster for that workload. These timings
are not an eightfold speedup and should not be generalized to other models.
The earlier V1 result was 526 seconds for a similar ensemble.

A read-only DSS comparison of preserved parallel and serial runs passed at
absolute tolerance 0.0 for 602/602 series: 13 reservoir pool outflows plus
Willamette_at Salem FLOW, over all 43 members, exact trial suffix CON_SEASON0.
Compared timestamps were 2026-10-15 00:00 through 2026-11-15 00:00. No differences,
absent series, missing/undefined samples, or coverage differences were reported.
This establishes the reported comparison scope; it does not establish equivalence
of every model variable, output freshness by itself, or endpoints absent in both
files. The comparison tool is `../../ExternalPython/compare_simulation_flows.py`.

Concurrent report JSON/CSV postprocessing errors were observed separately during
investigation. This compiler patch does not serialize those writers or repair
shared output-file ownership. A completed flow comparison is not a claim that
all ancillary reports are correct.

### Still to validate

Native Windows RTS/ResSim 4.1.2 compute with this patch has NOT yet been tested.
Use the existing test forecast and first compare a small set of known-covered
members against serial results, then the larger ensemble. Confirm every member,
full time coverage, return status, output equivalence, and the marker's actual
JAR path. Long-session/repeated-compute memory and resource use remain unverified.
Do not infer that CWMS orchestration automatically switches to the native ResSim
multithreaded ensemble launcher: those are separate execution paths.

## Requested HEC review

Please review ownership of the temporary compiler's PySystemState and whether
compilation can avoid tearing down the active rule runtime. A supported change
could isolate compilation state with caller restoration, or use a compile API
that does not perform interpreter teardown. In particular, please assess compiler
flags, nested use, imported modules, Jython threading exit hooks, live-file
ownership, retained-state lifecycle, and serial/parallel numerical equivalence.

The helper source, minimal reproductions, installer/restore code, tests and this
note are available for review. Vendor bytecode and patched JARs do not need to be
redistributed with the report; HEC can inspect the corresponding original build.
