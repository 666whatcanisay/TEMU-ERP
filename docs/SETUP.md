# 从零启动

## 环境与目录

需要 Python 3.11+、MySQL 8.0+、Git。CI 实际使用 Python 3.12 和 MySQL 8.0.42，操作系统覆盖 Windows 与 Ubuntu。静态前端不需要 npm 或 AI 账号。命令在仓库根目录执行。

```bash
git clone https://github.com/666whatcanisay/TEMU-ERP.git
cd TEMU-ERP
python -m pip install -r requirements.txt
python scripts/configure-mysql.py
python scripts/seed-demo.py
python -m app.backend.api.server
```

配置前启动 MySQL。脚本在终端隐藏读取管理员密码，创建 `temu_workbench` 和库内应用账号，仅保存随机应用凭据到被忽略的 `data/mysql.local.json`；已有可用配置会保留。管理员密码不写进文件或命令行。

打开 [本地工作台](http://127.0.0.1:8765/)。导航为候选研究、商品提报、反馈跟进。默认仅监听回环，Ctrl+C 停止应用；MySQL 是独立服务。

## 第一次看什么

1. `seed-demo.py` 导入五个离线案例，不访问外网、不覆盖已有记录或政策。
2. 候选研究中选择六件套 `DE-DRAWER-006`，查看资料与利润。
3. 当前案例核价 21 元、基准净收益 4.48 元、保守 2.13 元；点击退款风险查看公式和来源。
4. 生成内部评审资料，核对待办并下载 HTML；可独立打开，不向 Temu 写入。

若先启动服务才导入案例，最小初始政策会被保留，经营门槛结果可能不同；在设置中核对来源与口径，不要为复现截图删除工作数据。

## 数据与配置

| 内容 | 位置或规则 |
|---|---|
| 业务数据 | MySQL `temu_workbench`，实际目录由数据库服务管理 |
| 本机凭据 | `data/mysql.local.json`，不提交 Git |
| 完整备份 | `data/backups/*.mysql.json` |
| 页面缓存 | `.cache/workbench/` |
| 日志报告 | `reports/` |
| 环境配置 | 进程变量优先于本机 JSON，不自动加载 `.env` |

变量见 [操作手册](../RUNBOOK.md) 与 [.env.example](../.env.example)。MySQL 失败时报错，不自动退回 SQLite。

## 常见问题

| 现象 | 检查方式 |
|---|---|
| 找不到 pymysql | 用启动应用的同一个 Python 安装 requirements |
| MySQL 连接失败 | 检查服务、端口、凭据及旧环境变量，不删除工作库 |
| 8765 被占用 | 确认是否已有工作台，或通过 `WORKBENCH_PORT` 换端口 |
| 新建后不知道哪里填写 | 商品提报顶部“填写商品信息”“填写规格与成本” |
| 40% 与 15% 不一致 | 前者是五项贡献政策，后者是完整净收益目标，费用范围不同 |
| 手机打不开 localhost | 手机 localhost 指向手机自身；默认服务只提供本机入口 |
| DSH 等未配置 | 当前为独立预留接口，手动和文件流程不依赖它们 |

## 验证

基础测试不需要 MySQL 服务：

```bash
python -m unittest discover -s app/tests -v
python scripts/validate_bundle.py
python scripts/validate_docs.py
cd starter
python -m unittest discover -s tests -v
```

基础 76 项、starter 24 项；未启用时另有 12 项真实 MySQL 测试显示 skipped。集成测试会清空独立测试库，必须按 [MySQL 说明](MYSQL.md) 配置，禁止指向工作库。CI MySQL 作业实际运行它们。

旧数据迁移：停止应用，配置空目标库，执行 `python scripts/migrate-sqlite-to-mysql.py --app-stopped`。脚本备份旧库，完整迁移五表并摘要对账，恢复/回滚详见 [MySQL](MYSQL.md)。
