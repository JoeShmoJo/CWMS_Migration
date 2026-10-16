# RTS / ResSim parallel compute investigation

Inspected user-supplied `javap -p -c -constants` output from installed RTS 3.6.0 and ResSim 4.1.2 on 2026-10-09. No installed binaries or runtime settings changed.

Confirmed in `ResSimPluginServer.buildComputeInfo`: when RTS ensemble compute is active and the alternative is an ensemble alternative, `ComputeInfo.computeType` is assigned literal 3. `additionalOptions` receives one formatted six-digit ensemble member ID from `ComputeOptions.getEnsembleMemberNumber()`.

Confirmed in `MultithreadedComputeLauncher.compute`: it initially obtains `ResSimExecutorServiceDelegate.getPoolCount()`, but when `RssRun.getComputeType() == 3`, it prints `Native Ensemble Compute` and assigns worker count 1 before creating its run array. A larger executor pool does not override this branch.

Confirmed: `ResSimPluginServer.compute(ModelAlternative, ComputeProgressListener)` is public synchronized. This serializes calls to that method on the same server instance. It does not prove every alternative execution route is serialized; other instances/processes would need separate assessment.

Observed logs match these findings: one member and one thread per request, with other RTS compute requests waiting for ResSim. The launcher name alone is not evidence of parallel ensemble execution.

Not established: a supported standalone batch/headless API that can execute multiple forecast members together, a supported RTS setting selecting that API, or safe import of its outputs back into RTS. Inspect launcher factories, ensemble plugin classes and compute interfaces next. Do not patch vendor bytecode or alter computeType to bypass the branch: native mode affects member selection, paths and compute setup, not just thread count.

Candidate approach if supported: work on an isolated copy of the forecast, let the standalone ensemble engine handle several members, validate member IDs, timestamps and output F parts, then merge results into RTS only after compute finishes. Separate worker processes are another candidate, each with private model/DSS/log files; running them all against the live forecast DSS is not an acceptable experiment. Compatibility of our adapted rule globals with actual concurrent native compute still requires testing.

## Standalone ensemble plugin inspection

Confirmed in a second user-supplied javap dump: `EnsembleAltPluginData.setUseMultithreadedCompute(boolean)` controls whether `getComputeLauncher()` returns an `EnsembleComputeLauncher`. That launcher inherits the type-3 single-worker restriction. For a non-type-3 run it obtains a collection-member list from the alternative, caps workers at `min(poolCount, memberCount)`, and assigns contiguous member-index ranges to cloned runs with `setEnsembleIndexes(start,end)`. For type 3 it instead builds a one-member list from the provided ID.

This identifies a real native batch path, not a hypothetical parallel loop. It still does not establish a supported script/headless entry point or correct RTS input/output mapping in that mode. Next inspect public workspace / ComputeInfo interfaces and executor configuration before designing an isolated proof of concept. Our next experiment must preserve the standalone master and the live RTS forecast.

## Workspace and executor inspection

Confirmed executor setting: `hec.rss.compute.d` reads Java system property `ResSim.ComputeThreadCount` via `Integer.getInteger`, defaulting to `Runtime.availableProcessors()`, and constructs a fixed thread pool. The property is read when that executor is created, so any worker-process proof of concept should supply it at JVM startup. This property does not bypass the type-3 restriction.

Public workspace entry points include `RssRmiWorkspaceImpl.computeAlternative(ComputeInfo)`, `load()`, `getRssRun(String,boolean)`, and constructors accepting an integer or a String/Identifier. `ComputeInfo` exposes the time window, forecastpath, modelAltname, output DSS filename, computeType, additionalOptions, and related fields. These declarations establish API availability, not complete headless initialization requirements.

The executor factory stores one static cached delegate; the delegate's `shutDown()` shuts down its ExecutorService. The inspected factory does not test whether it is terminated before returning it again. This is consistent with the cancellation-followed-by-RejectedExecutionException observed in testing; restart the worker JVM between canceled trials.

Proposed first trial: isolated forecast copy, two real historical members, two workers via `-DResSim.ComputeThreadCount=2`, native batch ensemble mode, no automatic merge. Compare those two members' pool elevations/outflows to manual RTS outputs before expanding or merging. Verify initialization of the HEC native libraries, forecast input mapping, scripted configuration resolution, member F parts, and compute cancellation cleanup. Need workspace loading/compute implementation to construct this trial correctly; declarations alone are insufficient.
