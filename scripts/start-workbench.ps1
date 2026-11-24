# 启动 Temu 全托管选品与买手提报工作台（本地，仅监听 127.0.0.1）
# 用法：在 E:\TemuBuyerWorkbench 目录下运行
#   powershell -ExecutionPolicy Bypass -File scripts\start-workbench.ps1
# 退出：在本窗口按 Ctrl+C。业务数据：MySQL temu_workbench；本机凭据：data\mysql.local.json
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $taskRoot

$env:PYTHONPATH = $taskRoot
$env:PYTHONPYCACHEPREFIX = Join-Path $taskRoot '.cache\python'
$env:PIP_CACHE_DIR = Join-Path $taskRoot '.cache\pip'
$env:WORKBENCH_DATA_DIR = Join-Path $taskRoot 'data'

$hostPort = if ($env:WORKBENCH_PORT) { $env:WORKBENCH_PORT } else { '8765' }
Write-Host "工作目录: $taskRoot"
Write-Host "启动本地工作台: http://127.0.0.1:$hostPort  (Ctrl+C 退出)"
python -X utf8 -m app.backend.api.server
