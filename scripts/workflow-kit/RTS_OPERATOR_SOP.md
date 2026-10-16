# RTS baseline and augmentation: operator SOP

Current workflow, 16 October 2026. Details: [process and file reference](RTS_WORKFLOW_REFERENCE.md).
Use the original ResSim application and a supported compute mode; serial is
suitable. This workflow does not require the experimental JAR patch.

**Extract once → configure baseline → compute unaugmented → accept → process/load
augmentation → compute augmented → accept → plot.**

## 1. Open the forecast and extract

1. Open the intended forecast and select its forecast alternative in RTS.
2. Run watershed script `scripts\RTS_WORKFLOW_MENU.py` in the RTS Script Editor.
3. Verify forecast, alternative, DSS path, lookback, start, end and timezone.
   Use **Refresh forecast metadata** after changing the selected forecast/run.
4. Verify dates fit current RFC availability and CWMS lookback coverage. To process
   augmentation, the saved baseline must cover April 1, travel-time lead-in and
   the selected season end. A short October test is not a full-season baseline.
5. If using fixed-abundant water-year mode, verify the model uses
   **ALL_ABUNDANT (4)**, not the zero dummy.
6. Click **Initial Extract**, confirm, and wait for successful input loading.
   Reopen/refresh the same forecast as instructed. This does not compute ResSim.

Extract once for this forecast. After a baseline exists, use a new forecast for
new dates/downloads. Do not re-extract just to change operating configuration.

## 2. Configure and compute the baseline

1. Click **Baseline Configuration**. In the browser editor, open saved settings or
   edit the imported settings. Enter a useful name and description.
2. **Save Configuration** saves a reusable library version; it does not activate it.
3. Finish all computes and close DSS views, then **Apply for Baseline Compute**.
   Apply snapshots this forecast's settings and disables augmentation. Use
   **Close Editor** when finished.
4. Reopen the forecast if necessary. Confirm **Next compute: no augmentation**.
5. Compute the intended alternative/ensemble with the normal RTS/ResSim controls.
   The workflow menu does not start compute. Check successful member completion.
6. Click **Augmentation Configuration** and answer **Yes** to accept/archive the
   completed baseline. Confirm an ID such as `baseline-0001` is shown.

An unaugmented compute with the unchanged imported settings can also establish
the first baseline. Explicit Apply makes the selected configuration clearer.

## 3. Create and activate an augmentation scheme

1. In **Augmentation Configuration**, name the configuration and set reservoir
   participation, storage floors, maximum releases, travel times and calculation
   settings. Current requirements: identical Salem/Albany participation; Lookout
   Point participates and Hills Creek is combined with it.
2. **Save Configuration** retains reusable JSON; **Open Configuration** loads a
   saved file. Reusing settings in another forecast recalculates its releases.
3. Select an offered conservation season. If none is offered, save settings if
   useful but do not process: the baseline lacks the necessary season coverage.
4. Click **Process and Load Releases**. At its completion prompt, choose Yes only
   if a new successful compute needs archiving; otherwise choose No.
5. Wait for **Releases processed and loaded** and check the next-compute label.

This is the scheme “commit”: prepared releases are saved and activated against
one baseline. It is not a Git commit and does not run the simulation.

## 4. Compute, archive and plot the pair

1. Reopen the forecast as instructed and compute with the loaded augmentation.
   **Do not run Initial Extract again.**
2. Check successful completion. Click **Plot Results**, then **Yes** to archive it.
3. Ctrl-click the matching unaugmented baseline and augmented result, checking
   that both have the same baseline ID. Click **Plot Selected**.
4. Review elevations/outflows, mainstem flows and available target overlays.
   The browser opens the plot index; **Open Last Plots** reopens this session's plots.

Select one run for single-run plots or two for comparison. Cross-baseline pairs
are allowed but include baseline differences, as their labels indicate.

## 5. Create a new baseline and another scheme

1. Accept any completed augmented result you want to retain before changing
   baseline settings; a later compute can overwrite live outputs.
2. Open **Baseline Configuration**, load/edit/name/save settings, then **Apply for
   Baseline Compute**. Augmentation is disabled automatically. No separate
   Reset Baseline button is required in the current menu.
3. Compute unaugmented and accept the completed results as in step 2.
4. Changed pool elevations/outflows create a new baseline ID; older augmented
   results retain their pairs and become **Previous baseline**. Identical compared
   outputs retain the existing ID and print **Baseline results unchanged**.
5. Open/reuse augmentation settings, **Process and Load Releases**, compute,
   accept, and plot again. Releases must be prepared against the current baseline.

## Prompts, retention and errors

| Choice/action | Meaning |
| --- | --- |
| Completion prompt: Yes | Compute finished successfully; archive its current results |
| No | Use previously saved results only |
| Cancel | Stop |
| Delete Selected Augmented Result | After confirmation, remove that result and plots involving it; retain baselines, scheme inputs, configurations and history |

The completion prompt does not approve baseline quality or independently verify
compute success. Old DSS records can survive a failed compute.

Finish compute and close DSSVue/DSS views before file operations. If a lock requires
closing the forecast, keep the menu open and use **Use this displayed forecast
after closing it in RTS** with verified metadata; reopen the same forecast before
compute. Do not run menu tasks and native compute concurrently.

New accepted results log **Compact archive: ... No DSS snapshot copied.** Existing
DSS archives remain usable. Do not delete compact `series.npz` as a cache: it is
primary saved data. Keep the task's `workflow-logs` log for failures.

**Known caveat:** changing water-year inputs alone may retain an older archived
input if pool elevations/outflows match. Fixed-abundant rejects values other than
4. Do not assume reacceptance refreshed that input; resolve it before processing.
A fresh forecast is the clean workaround for changed extracted/mapped inputs.
See the reference for details and other troubleshooting.
