# 本地校验：lint -> publish -> guard -> status
# 用法：powershell -ExecutionPolicy Bypass -File 90_Meta\scripts\verify.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $root
chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

Write-Host "== 1/4 结构与链接检查 ==" -ForegroundColor Cyan
python 90_Meta\scripts\kb.py lint
if ($LASTEXITCODE -ne 0) { throw "lint 未通过" }

Write-Host "== 2/4 生成发布面 ==" -ForegroundColor Cyan
python 90_Meta\scripts\kb.py publish --out .publish

Write-Host "== 3/4 泄漏守卫 ==" -ForegroundColor Cyan
python 90_Meta\scripts\kb.py guard --dir .publish
if ($LASTEXITCODE -ne 0) { throw "guard 未通过" }

Write-Host "== 4/4 看板 ==" -ForegroundColor Cyan
python 90_Meta\scripts\kb.py status
Write-Host "全部通过。" -ForegroundColor Green
