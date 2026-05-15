param(
    [Parameter(Mandatory = $true)]
    [string]$Tag
)

$ErrorActionPreference = "Stop"

$version = $Tag.TrimStart("v")
$notesFile = Join-Path $PSScriptRoot ".." ".github" "release-notes" "$Tag.md"
$notesFile = [System.IO.Path]::GetFullPath($notesFile)

if (Test-Path -LiteralPath $notesFile) {
    $notes = Get-Content -LiteralPath $notesFile -Raw
    $summary = (Get-Content -LiteralPath $notesFile -TotalCount 1).Trim()
    $title = "$version — $summary"
    return [PSCustomObject]@{
        Title = $title
        Notes = $notes.Trim()
    }
}

$changelogPath = Join-Path $PSScriptRoot ".." "CHANGELOG.md"
$changelogPath = [System.IO.Path]::GetFullPath($changelogPath)
if (-not (Test-Path -LiteralPath $changelogPath)) {
    throw "No release notes file at $notesFile and CHANGELOG.md not found"
}

$lines = Get-Content -LiteralPath $changelogPath
$header = "## [$version]"
$start = [array]::IndexOf($lines, $header)
if ($start -lt 0) {
    throw "Changelog section not found: $header"
}

$end = $lines.Count
for ($i = $start + 1; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^## \[') {
        $end = $i
        break
    }
}

$section = ($lines[$start..($end - 1)] -join "`n").Trim()
$title = "$version"
return [PSCustomObject]@{
    Title = $title
    Notes = $section
}
