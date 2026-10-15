# Configuration timing only — sandbox diagnostic

No cache, altered input tables or operating calculations. prepare_config_timing.py
copies the CURRENT V2 installation and CURRENT watershed into two new directories.
It adds a Java timing collector to the installation COPY and appends wrappers to
selected Python modules in the watershed COPY. Original V2 and model remain
unchanged. Both new destination directories must not already exist. The source
V2 JAR checksum must match its compiler-isolation-test.json marker.

Known text model/script absolute references under the source watershed are rebased
to the copied watershed; DSS and binary files are not edited. Unknown external
absolute references cannot be inferred safely. Before computing, open the copied
.wksp and confirm the simulation/output DSS is under the copied watershed. Never
run the original model in the diagnostic installation. One model, one compute per
fresh JVM keeps the counters interpretable. Preparation copies entire directory
trees and needs room for both copies. Do not launch incomplete copies if it fails.

## Scope

The installer instruments cFile.fileOpenReadClose and its encoding variant, plus
top-level functions whose names start with load/read and contain config, in
externalRules and externalSVs. It lists every instrumented function in
config-read-timing-diagnostic.json. Class methods, direct open() calls such as
Alternative_Setup's _default.txt reader, native JSON readers, and unrelated export
paths are outside scope. Config-loader timings include parsing/table allocation;
exclusive timings subtract nested instrumented reads/loaders, not all work done
by other functions. Timings include scheduling/lock waits, not just CPU time.

Java static counters aggregate across Python states and worker threads. Wrappers
return the original result object unchanged and propagate original exceptions.
There is no file/report output per call. Timing/statistics have some overhead;
do not interpret diagnostic compute time as an optimization benchmark.

## Windows use

Close ResSim/RTS. Run prepare_config_timing.py with --installation V2_SOURCE,
--watershed MODEL_SOURCE, --destination-installation NEW_INSTALLATION, and
--destination-watershed NEW_WATERSHED. Launch the new installation directly and
open the copied watershed. Keep the same members, month, rules and eight threads.

The console must show CONFIG READ TIMING ACTIVE (no caching) and a report path
under the NEW model. If absent, the intended scripts were not exercised.
After ONE compute finishes, close the copied ResSim application normally. Its
Java shutdown hook writes summary.txt and timings.csv into a new capture folder
under NEW_WATERSHED/config-read-timing-reports. Ordinary close is required; force
killing the process may lose reports. Report in-flight count must be zero.
Alternatively, after compute, run these two lines in ResSim's script editor:

    from cwms.diagnostics import ConfigReadTimings
    print(ConfigReadTimings.writeReport())

The report path is printed. Closing later creates another snapshot of the same
counters, not another compute. A snapshot during compute is labeled with active
calls and must not be treated as complete. Reports are cumulative since startup,
including any instrumented setup before compute. Do not run a second compute in
the same JVM. Summed worker seconds are not elapsed time or predicted savings.

Output includes call/failure counts and inclusive, exclusive and maximum time
per loader and filename. Share summary.txt and timings.csv for analysis. Existing
CSV/model-report errors are neither repaired nor hidden by this diagnostic.
No profiling hooks or new cache are installed in the working V2 application.

Rollback: close the copied app and return to the original V2/model. Keep or delete
the two diagnostic directories later. Do not copy instrumented scripts back.

## Verification

Two Python preparation tests check copied-model instrumentation, existing-copy
refusal, original file integrity, text mapping rebasing, no DSS byte changes and
selection of only top-level config loaders. Jython 2.7.2/Java 21 check_runtime.py
tests four concurrent workers, nested read/parse totals, return identity, exception
propagation/failure counts, idempotent wrapping and CSV report output. These are
local tests, not native ResSim verification. Actual Windows model execution and
full configuration-reader coverage remain unverified.

Java source and bundled helper JAR are included. Compile ConfigReadTimings.java
with -source 8 -target 8 and package its class plus all nested classes. Run
check_runtime.py under Jython with the helper JAR on Java's classpath, then run:

    python migration-review/diagnostics/config-timing/test_prepare_config_timing.py
