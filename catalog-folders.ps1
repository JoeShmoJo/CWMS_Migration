param(
    [string]$RepositoryRoot = $PSScriptRoot,
    [string[]]$Folders = @('CWMS_RTS', 'NWP_Willamette_Master_2026_10_05_DamagesPrevented'),
    [string]$OutputDirectory = ''
)

# Compatible with Windows PowerShell 5.1. Reads metadata, not file contents.
$ErrorActionPreference = 'Stop'
$RepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $RepositoryRoot 'catalog'
}
if (Test-Path -LiteralPath $OutputDirectory) {
    throw "Output directory already exists: $OutputDirectory. Choose a new -OutputDirectory to preserve previous catalogs."
}

# Validate every source before creating output.
$sources = foreach ($folder in $Folders) {
    $path = if ([IO.Path]::IsPathRooted($folder)) { $folder } else { Join-Path $RepositoryRoot $folder }
    $item = Get-Item -LiteralPath $path -Force
    if (-not $item.PSIsContainer) { throw "Not a folder: $path" }
    [pscustomobject]@{ Label = $folder; Path = $item.FullName.TrimEnd('\', '/') }
}
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$problems = New-Object 'System.Collections.Generic.List[object]'
$rows = New-Object 'System.Collections.Generic.List[object]'

foreach ($source in $sources) {
    $pending = New-Object 'System.Collections.Generic.Stack[string]'
    $pending.Push($source.Path)
    while ($pending.Count -gt 0) {
        $directory = $pending.Pop()
        try {
            $children = @(Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop)
        } catch {
            $problems.Add([pscustomobject]@{
                Source = $source.Label
                RelativePath = $directory.Substring($source.Path.Length).TrimStart('\', '/')
                Issue = 'Directory enumeration failed: ' + $_.Exception.Message
            })
            continue
        }
        foreach ($item in $children) {
            $relative = $item.FullName.Substring($source.Path.Length).TrimStart('\', '/')
            $isLink = ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
            $rows.Add([pscustomobject]@{
                Source = $source.Label
                RelativePath = $relative
                Kind = if ($item.PSIsContainer) { 'Directory' } else { 'File' }
                Extension = if ($item.PSIsContainer) { '' } else { $item.Extension.ToLowerInvariant() }
                SizeBytes = if ($item.PSIsContainer) { $null } else { $item.Length }
                ModifiedUtc = $item.LastWriteTimeUtc.ToString('o')
                ReparsePoint = $isLink
            })
            if ($isLink) {
                $problems.Add([pscustomobject]@{ Source = $source.Label; RelativePath = $relative; Issue = 'Link or junction recorded; not traversed' })
            } elseif ($item.PSIsContainer) {
                $pending.Push($item.FullName)
            }
        }
    }
}

$ordered = @($rows | Sort-Object Source, RelativePath)
$ordered | Export-Csv -LiteralPath (Join-Path $OutputDirectory 'inventory.csv') -NoTypeInformation -Encoding UTF8
$files = @($ordered | Where-Object Kind -eq 'File')
$files | Group-Object Source, Extension | ForEach-Object {
    [pscustomobject]@{
        Source = $_.Group[0].Source
        Extension = $_.Group[0].Extension
        FileCount = $_.Count
        TotalBytes = ($_.Group | Measure-Object SizeBytes -Sum).Sum
    }
} | Sort-Object Source, Extension | Export-Csv -LiteralPath (Join-Path $OutputDirectory 'file-types.csv') -NoTypeInformation -Encoding UTF8

# A shortlist for review, not a claim that all migration inputs are identified.
$extensions = @('.py', '.java', '.groovy', '.js', '.bat', '.cmd', '.ps1', '.sh', '.config', '.properties', '.xml', '.json', '.ini', '.conf', '.cfg', '.yaml', '.yml')
$files | Where-Object {
    $_.Extension -in $extensions -or $_.RelativePath -match '(?i)script|simulation|watershed|jython|readme'
} | Export-Csv -LiteralPath (Join-Path $OutputDirectory 'review-candidates.csv') -NoTypeInformation -Encoding UTF8

if ($problems.Count) {
    $problems | Export-Csv -LiteralPath (Join-Path $OutputDirectory 'scan-issues.csv') -NoTypeInformation -Encoding UTF8
}
@(
    "Catalog created UTC: $([DateTime]::UtcNow.ToString('o'))"
    'Sources: ' + (($sources | ForEach-Object Label) -join ', ')
    "Files: $($files.Count)"
    "Directories: $(@($ordered | Where-Object Kind -eq 'Directory').Count)"
    "File bytes: $(($files | Measure-Object SizeBytes -Sum).Sum)"
    "Scan issues or skipped links: $($problems.Count)"
    'File contents were not read. Links and junctions were not followed.'
) | Set-Content -LiteralPath (Join-Path $OutputDirectory 'summary.txt') -Encoding UTF8
Write-Host "Catalog saved to $OutputDirectory"
if ($problems.Count) {
    Write-Warning 'Catalog may be incomplete. Review scan-issues.csv before using it to select files.'
}
