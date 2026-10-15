# Review of successful-flow V2 run, 2026-10-15

Source: user-uploaded console log, SHA-256
bd483bfee6b3a5e91e0ac732395f48214efc12d317200cc7e5b94dc94169240d.
No model, configuration, installation or cache changes were made for this review.

## Workload and timing evidence

The log has the V2 active marker, eight workers partitioning 43 members, and
1,376 `DiversionFromCSV: loaded` messages: 32 per member. These are initialization
messages, not individually instrumented physical file reads or parse timers.
The maintained script snapshot's loadDailyConfig reads and parses its CSV on
entry, but the precise live loader source/caches are not established by a log.

Eight native worker summaries report:

| Phase | Minimum | Median | Maximum |
| --- | ---: | ---: | ---: |
| Native init | 0.736 s | 0.764 s | 0.776 s |
| Regulated compute | 48.434 s | 48.927 s | 52.694 s |
| Completion/finalization | 66.349 s | 67.748 s | 72.820 s |
| Worker total | 123 s | 124 s | 133 s |

These worker times overlap; their sum is not elapsed run time. They summarize
worker partitions, not 43 independent timings. Configuration reads and scripted
initialization are not necessarily all accounted for by the native init phase.
Likewise, rule footer timings (eight copies of each rule instance) cannot be
assumed to measure every config load across all members.

ResSim 4.1.0 RssRun.finalizeCompute bytecode measures its completion phase around
saveOutput, system.finalizeCompute, prepRegulatedFlowCompute and embedded
alternative cleanup. Thus it is not a pure DSS disk-write timer. It is a larger
reported phase than regulated compute and deserves investigation independently
of configuration caching. High output/console volume and contention are possible
contributors, not established causes.

The log also contains `Reloaded module ...` messages from Import Modules; do not
assume the earlier no-reload rule edits remain active in the current model.
Preserve the actual working files before any instrumentation.

## Output errors still present

- Six `ERROR Unable to write modelReport file` messages name the same
  modelReport_Con_Season.json path. Concurrent access is plausible, not proven.
- Two error reports for PostProcess_CSV cleanup show writer.writerow at line 109
  failing with `ValueError: I/O operation on closed file`. Duplicated traceback
  printing means this is not a reliable count of unique failed members.

The user previously compared 602 reservoir/Salem flow series for 1982-2024 in
trial CON_SEASON0 and reported exact equality, with no missing data or coverage
differences. These CSV/report errors do not negate that scoped DSS comparison;
they do mean the full export/report workflow has not been validated error-free.

## Recommendation

Do not add a cache yet or change the known working V2 installation. First inspect
the current PostProcess_CSV cleanup code and its file ownership/naming. Capture
a preserved test-model copy before adding timing-only wrappers. Any further
profiling should separate raw reads, parsing/table construction, and export/
finalization, record per-file/member/thread counts and inclusive times, and avoid
per-call console logging. Shared parsed-data caching requires immutable data,
thread-safe initialization and explicit compute-boundary invalidation. It must
be validated against serial flows without changing the original config sources.

The existing log establishes repeated initialization and points to finalization
cost; it cannot quantify the speedup available from caching. No timing wrappers,
cache, or deployment were installed as part of this review.
