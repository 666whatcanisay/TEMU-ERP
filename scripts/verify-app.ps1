# 运行应用后端单元测试（领域计算、持久化、导入导出、服务流程）
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$env:PYTHONPATH = $taskRoot
$env:PYTHONPYCACHEPREFIX = Join-Path $taskRoot '.cache\python'
python -X utf8 -m unittest discover -s (Join-Path $taskRoot 'app\tests') -v
if ($LASTEXITCODE -ne 0) { throw 'App tests failed.' }
