# 本地预览站点（会先 publish，再启动 Quartz）
# 用法：powershell -ExecutionPolicy Bypass -File 90_Meta\scripts\preview.ps1 [-Port 8080]
param([int]$Port = 8080)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $root
chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$nodeVersion = (node --version) -replace '^v', ''
if ([int]($nodeVersion.Split('.')[0]) -lt 20) {
    throw "Quartz 4.4 需要 Node 20+，当前为 $nodeVersion。请升级 Node 后重试。"
}

Write-Host "== 生成发布面（含草稿，仅本地） ==" -ForegroundColor Cyan
python 90_Meta\scripts\kb.py publish --out .publish --include-drafts

if (-not (Test-Path ".quartz")) {
    Write-Host "== 首次运行：克隆 Quartz 框架 ==" -ForegroundColor Cyan
    git clone --depth 1 --branch v4.4.0 https://github.com/jackyzha0/quartz.git .quartz
}

Copy-Item "site\quartz.config.ts" ".quartz\quartz.config.ts" -Force
Copy-Item "site\quartz.layout.ts" ".quartz\quartz.layout.ts" -Force

Push-Location .quartz
try {
    if (-not (Test-Path "node_modules")) {
        Write-Host "== 安装依赖（只需一次，约 1-3 分钟） ==" -ForegroundColor Cyan
        npm ci
    }
    Write-Host "== 启动预览：http://localhost:$Port ==" -ForegroundColor Green
    node .\quartz\bootstrap-cli.mjs build --serve -d "$root\.publish" -o "$root\public" --port $Port
} finally {
    Pop-Location
}
