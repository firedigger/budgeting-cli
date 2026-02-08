[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = 'Stop'

# Allow running from source without installing the package.
$repoRoot = $PSScriptRoot
$srcPath = Join-Path $repoRoot 'src'
if (Test-Path $srcPath) {
    if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
        $env:PYTHONPATH = $srcPath
    } else {
        $env:PYTHONPATH = "$srcPath;$($env:PYTHONPATH)"
    }
}

function Get-Py311 {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $py) { return $py.Path }
    return $null
}

$pyPath = Get-Py311
if ($null -ne $pyPath) {
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        # Probe for Python 3.11 without surfacing launcher errors.
        & $pyPath -3.11 -c "import sys" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            & $pyPath -3.11 -m budgeting_cli.main @Args
            exit $LASTEXITCODE
        }

        # Fall back to default launcher runtime.
        & $pyPath -c "import sys" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            & $pyPath -m budgeting_cli.main @Args
            exit $LASTEXITCODE
        }
    } finally {
        $ErrorActionPreference = $oldEap
    }
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -ne $python) {
    & $python.Path -m budgeting_cli.main @Args
    exit $LASTEXITCODE
}

Write-Error "Could not find Python. Install Python 3.11 (recommended) or ensure 'python' is on PATH."
exit 1
