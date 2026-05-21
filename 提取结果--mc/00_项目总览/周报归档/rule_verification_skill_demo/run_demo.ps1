param(
  [string]$InputRules = "",
  [string]$OutputDir = "",
  [string]$Agent1Filled = "",
  [string]$Agent2Filled = ""
)

$ErrorActionPreference = "Stop"

$DemoDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $DemoDir "..\..\..\..")).Path
$SkillDir = Join-Path $ProjectRoot "skill documents\petrochemical-rule-verification"

if ([string]::IsNullOrWhiteSpace($InputRules)) {
  $InputRules = Join-Path $SkillDir "examples\rule_content_filled_example.xlsx"
}
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
  $OutputDir = Join-Path $DemoDir "live_output"
}
if ([string]::IsNullOrWhiteSpace($Agent1Filled)) {
  $Agent1Filled = Join-Path $DemoDir "prepared_fills\agent1_filled_demo.xlsx"
}
if ([string]::IsNullOrWhiteSpace($Agent2Filled)) {
  $Agent2Filled = Join-Path $DemoDir "prepared_fills\agent2_filled_demo.xlsx"
}

function Invoke-PythonStep {
  param([string[]]$PyArgs)
  & python @PyArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Python step failed: python $($PyArgs -join ' ')"
  }
}

foreach ($path in @($InputRules, $Agent1Filled, $Agent2Filled)) {
  if (-not (Test-Path -LiteralPath $path)) {
    throw "File not found: $path"
  }
}

if (Test-Path -LiteralPath $OutputDir) {
  $resolvedOutput = (Resolve-Path -LiteralPath $OutputDir).Path
  $resolvedDemo = (Resolve-Path -LiteralPath $DemoDir).Path
  if (-not $resolvedOutput.StartsWith($resolvedDemo)) {
    throw "Refusing to remove output outside demo directory: $resolvedOutput"
  }
  Remove-Item -LiteralPath $resolvedOutput -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$MaskWorkbook = Join-Path $OutputDir "01_rule_content_mask.xlsx"
$Agent1Blind = Join-Path $OutputDir "02_agent1_blind_input.xlsx"
$Agent2Blind = Join-Path $OutputDir "03_agent2_blind_input.xlsx"
$Agent1Demo = Join-Path $OutputDir "04_agent1_filled_demo.xlsx"
$Agent2Demo = Join-Path $OutputDir "05_agent2_filled_demo.xlsx"
$FilledWorkbook = Join-Path $OutputDir "06_rule_content_filled.xlsx"
$VerifiedWorkbook = Join-Path $OutputDir "07_rule_content_verified.xlsx"
$Report = Join-Path $OutputDir "08_verification_report.md"

Invoke-PythonStep @(
  (Join-Path $SkillDir "scripts\build_mask_workbook.py"),
  "--input", $InputRules,
  "--output", $MaskWorkbook
)

Invoke-PythonStep @(
  (Join-Path $SkillDir "scripts\export_blind_inputs.py"),
  "--input", $MaskWorkbook,
  "--outdir", $OutputDir
)

Move-Item -LiteralPath (Join-Path $OutputDir "agent1_blind_input.xlsx") -Destination $Agent1Blind -Force
Move-Item -LiteralPath (Join-Path $OutputDir "agent2_blind_input.xlsx") -Destination $Agent2Blind -Force
Copy-Item -LiteralPath $Agent1Filled -Destination $Agent1Demo -Force
Copy-Item -LiteralPath $Agent2Filled -Destination $Agent2Demo -Force

Invoke-PythonStep @(
  (Join-Path $SkillDir "scripts\merge_agent_fills.py"),
  "--base", $MaskWorkbook,
  "--agent1", $Agent1Demo,
  "--agent2", $Agent2Demo,
  "--output", $FilledWorkbook
)

Invoke-PythonStep @(
  (Join-Path $SkillDir "scripts\judge_verification.py"),
  "--input", $FilledWorkbook,
  "--output", $VerifiedWorkbook,
  "--report", $Report
)

Write-Host ""
Write-Host "Demo output:"
Get-ChildItem -LiteralPath $OutputDir | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize

Write-Host ""
Write-Host "Verification report:"
Get-Content -LiteralPath $Report -Encoding UTF8
