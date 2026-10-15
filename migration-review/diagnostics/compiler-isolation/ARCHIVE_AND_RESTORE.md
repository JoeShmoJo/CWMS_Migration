# Preserve the modified JARs and restore vendor originals

The user requested restoration after reviewing HEC's terms prohibiting modification
and reverse engineering. This tool only preserves existing modified binaries and
restores verified originals; it does not inspect bytecode or build a patch.

Close RTS/CWMS and all ResSim applications first. This command searches marked
standalone test installations under C:\Mobile_Programs, including copied V1/V2
and timing-test installations, and the specified RTS installation. No watershed
copy is made. It archives only modified application JARs and installation receipts.

PowerShell one line:

```powershell
Set-Location "C:\Projects\A_REPOSITORIES\CWMS_Migration"; git pull --ff-only; if ($LASTEXITCODE -ne 0) { throw "Git pull failed" }; & "$env:LOCALAPPDATA\miniconda3\envs\hydro39\python.exe" ".\migration-review\diagnostics\compiler-isolation\archive_and_restore.py" --standalone-search-root "C:\Mobile_Programs" --rts-installation "C:\Mobile_Programs\rts-install-package-3.6.0\HEC-RTS-3.6.0" --archive-root "C:\Projects\ResSimCompilerArchive"
```

The ZIP is outside the Git repository and application classpaths. It includes an
archive manifest with installation locations and before/after SHA-256 values.
Every archived JAR is read back and checked against the installed modified file's
recorded hash. All archive verification completes before any restoration begins.
The tool never uploads or distributes the ZIP.

Standalone originals come from the existing `.jar.original` files. RTS originals
come from the checksum-matched installation backup receipt. Both original versions
are checksum-pinned. Unknown changes or corrupt/missing backups stop preparation.
If no marked standalone installations are found, neither application is restored;
confirm the search location rather than proceeding with an incomplete inventory.
Copies outside the supplied search root are not scanned.

Original JARs replace modified JARs through verified staging files. A sibling
`.restoration.json` file records each successful restoration and final status.
`COMPLETE` means all planned application JARs matched their vendor-original hashes.
A later failure is recorded as incomplete; earlier successful restorations are
retained and all modified JARs are already in the verified ZIP. A retry skips JARs
already restored. Existing original backups remain intact.

No model data, operating scripts, configurations, thread settings, JREs or unrelated
profiling helper files are changed. Test directories may still have V2 in their
names even though their application JAR is original again. Standard unmodified
standalone installations without a test marker are not touched. After restoring,
the compiler workaround is no longer active; its parallel scripted-compute benefit
is no longer expected. Preserve the ZIP privately pending applicable guidance.

Validation: five local tests cover both versions, ZIP content/identity, repeated
restoration, unknown JARs, corrupt originals, failed ZIP verification, failed
replacement, and refusal when applications are running. These use temporary
fixtures and mocked process checks; native Windows execution remains the user's
next step.
