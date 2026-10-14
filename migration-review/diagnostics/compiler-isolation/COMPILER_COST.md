# Compiler initialization cost experiment, 2026-10-14

Java 21 / Jython standalone 2.7.2, four worker threads, 30 trivial script
compilations per worker. Each strategy runs in a separate fresh JVM; timing
excludes initial host-interpreter construction and includes worker initialization.
CompilerCostCheck.java is the executable benchmark source. Results from one run:

- Current isolated compiler: 120 compilations in 12.369 seconds.
- Private compiler reused by each worker: 120 compilations in 1.649 seconds.

This is approximately 7.5x faster for this small compilation workload. It does
not measure native ResSim simulation or predict full-run speedup. There were no
model inputs, rule initializers or DSS writes. The reuse test checks caller
state restoration, but is a prototype: it does not close cached interpreters,
implement reentrant acquisition, or establish safe application shutdown and
cache reset. The existing installed patch remains unchanged.

The all-member Windows dump (PID 23980) showed 32 ensemble workers loading site,
Python modules and Java classes, with other workers waiting on JAR/class-loader
locks. None was in PythonInterpreter.cleanup or Thread.join. That supports
initialization cost as a bottleneck in that snapshot; it does not establish that
all elapsed compute time is attributable to compilation.

An optimized patch should retain private compiler state per executor worker,
restore caller state on success and failure, and keep execution of model scripts
in their original interpreters. It must test syntax-error recovery, concurrent
compilation, reentrancy, compiler options, process lifecycle, bounded retained
state and serial/parallel output equivalence before operational use.

## V2 result

The implemented V2 helper reuses only private PySystemState per worker; it still
creates a new wrapper and compiler flags per script. The same benchmark using the
bundled V2 adapter completed 120 compilations in 0.998 seconds. Later benchmark
output labels this mode bundled-adapter rather than fresh. This remains a local
microbenchmark. User-reported V1 reference for 1982-2024 one-month simulation at
eight threads is 526 seconds; V2 native timing is not yet available.
