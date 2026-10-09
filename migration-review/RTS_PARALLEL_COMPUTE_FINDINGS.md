# RTS / ResSim parallel compute investigation

Inspected user-supplied `javap -p -c -constants` output from installed RTS 3.6.0 and ResSim 4.1.2 on 2026-10-09. No installed binaries or runtime settings changed.

Confirmed in `ResSimPluginServer.buildComputeInfo`: when RTS ensemble compute is active and the alternative is an ensemble alternative, `ComputeInfo.computeType` is assigned literal 3. `additionalOptions` receives one formatted six-digit ensemble member ID from `ComputeOptions.getEnsembleMemberNumber()`.

Confirmed in `MultithreadedComputeLauncher.compute`: it initially obtains `ResSimExecutorServiceDelegate.getPoolCount()`, but when `RssRun.getComputeType() == 3`, it prints `Native Ensemble Compute` and assigns worker count 1 before creating its run array. A larger executor pool does not override this branch.

Confirmed: `ResSimPluginServer.compute(ModelAlternative, ComputeProgressListener)` is public synchronized. This serializes calls to that method on the same server instance. It does not prove every alternative execution route is serialized; other instances/processes would need separate assessment.

Observed logs match these findings: one member and one thread per request, with other RTS compute requests waiting for ResSim. The launcher name alone is not evidence of parallel ensemble execution.

Not established: a supported standalone batch/headless API that can execute multiple forecast members together, a supported RTS setting selecting that API, or safe import of its outputs back into RTS. Inspect launcher factories, ensemble plugin classes and compute interfaces next. Do not patch vendor bytecode or alter computeType to bypass the branch: native mode affects member selection, paths and compute setup, not just thread count.

Candidate approach if supported: work on an isolated copy of the forecast, let the standalone ensemble engine handle several members, validate member IDs, timestamps and output F parts, then merge results into RTS only after compute finishes. Separate worker processes are another candidate, each with private model/DSS/log files; running them all against the live forecast DSS is not an acceptable experiment. Compatibility of our adapted rule globals with actual concurrent native compute still requires testing.
