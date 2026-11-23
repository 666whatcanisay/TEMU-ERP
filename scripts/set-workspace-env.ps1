# Dot-source this file for the current shell only. No machine/global settings change.
$taskRoot = Split-Path -Parent $PSScriptRoot
$env:PIP_CACHE_DIR = Join-Path $taskRoot '.cache/pip'
$env:UV_CACHE_DIR = Join-Path $taskRoot '.cache/uv'
$env:npm_config_cache = Join-Path $taskRoot '.cache/npm'
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $taskRoot '.cache/ms-playwright'
$env:PYTHONPYCACHEPREFIX = Join-Path $taskRoot '.cache/python'
