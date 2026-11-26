# MySQL 运行、关系实体迁移与恢复

当前业务库 `temu_workbench`，默认 `127.0.0.1:3306`，结构版本 `20261126-relational-v2`。MySQL 8 / InnoDB / utf8mb4_bin，通过 PyMySQL 连接。关系图、表职责及面试讲法见 [数据库设计](DATABASE.md)。

## 新环境

先安装并启动 MySQL 8.0+、Python 3.11+：

```bash
python -m pip install -r requirements.txt
python scripts/configure-mysql.py
python scripts/seed-demo.py
python -m app.backend.api.server
```

配置脚本隐藏读取 root 密码，创建项目库与库内应用账号。随机应用密码只保存到被忽略的 `data/mysql.local.json`，root 密码不落盘。账号权限限制在项目 schema，包含建表、迁移及查询视图所需权限；不是已经拆分迁移账号和纯运行账号的生产权限方案。

新空库首次启动会创建关系表和参数字典。环境变量优先于本机 JSON；`.env.example` 是变量说明，不会自动加载 `.env`。MySQL 连接失败不会静默切回 SQLite。

也可使用已有授权账号设置 `WORKBENCH_MYSQL_HOST/PORT/USER/PASSWORD/DATABASE`。数据库需先创建；本地开发账号在该 schema 需要 SELECT、INSERT、UPDATE、DELETE、CREATE、INDEX、ALTER、CREATE VIEW、SHOW VIEW。旧表改名归档另需 MySQL RENAME 所要求的权限，建议通过一次性管理员迁移完成。

## 已有 MySQL v1 升级

旧版只有 `records/revisions/submissions/snapshots/adapter_status` 五表。新应用发现旧库会给出升级提示，绝不会自动覆盖或悄悄建立另一份工作数据。

1. 关闭工作台，暂停写入。脚本检查配置的应用端口已关闭。
2. 执行下列命令，通过隐藏输入提供管理员密码，只在进程内使用。

```bash
python scripts/upgrade-database-v2.py --app-stopped --admin
```

3. 启动工作台，检查健康接口、商品和财务结果；Navicat 刷新表与视图。

升级分阶段：

```text
停写 → 旧五表一致性读取与备份
     → 创建关系结构（DDL）
     → 一个事务内拆分导入、重建DTO、全量摘要核对（DML）
     → 登记数据库版本
     → 参考来源入库、已有网页文件与哈希核验
     → v2全部实体备份
     → 一个RENAME语句将旧五表改名legacy_v1_*归档
```

MySQL DDL 会隐式提交，不能声称整段操作都在同一事务里。结构创建可能留下空的新表，但原五表在导入成功前保持原样。导入失败会回滚新业务数据；应用只有看到已提交的版本标记才读新实体。已完成导入但归档未完成时，重新运行可继续归档。旧表不会被新应用继续双写。

升级脚本只添加缺失的参考登记，不覆盖已有业务观察或已经入库的登记。旧商品来源的快照路径回填到 `source_snapshots`，逐个检查文件与 SHA256；不存在/不匹配会如实记录。只有日期的旧记录保留日期精度，午夜 UTC 只是数据库排序约定，不冒充精确抓取时间。

## 从 SQLite 迁移

停止应用，配置空的 MySQL 目标库：

```bash
python scripts/migrate-sqlite-to-mysql.py --app-stopped
```

脚本先备份 SQLite，通过旧五表 DTO 交换格式转换到关系实体，比较全部 ID、时间和 payload 摘要；非空且不同的目标库拒绝覆盖。旧 SQLite 保留。`export_state()` 用于这一兼容对账，不是 v2 全量数据库备份接口。

## 完整备份与恢复

设置与集成中的“备份数据库”生成 `*.mysql.json`，格式 `temu-workbench-relational/v2`。覆盖全部 **21 张业务/字典表**：包括统一来源、SKU、尺寸、属性、组成、成本、参数、反馈、审计和提报，不只导出当前列表。

备份包含结构版本、DDL摘要、完整行、主键定义对应的全量摘要。导出在一致的事务快照中完成。恢复先验证版本、表集合、列集合、主键和摘要，再按外键顺序在一个事务内删除与插入；不关闭外键检查。字典与当前模型不一致、外键失败或中途错误均回滚，保留原有数据。

旧 `temu-workbench-backup/v1` 备份仍可转换恢复。应用恢复成功后补齐已知参考登记。旧格式不包含停用 SKU、完整参数字典等新实体，恢复旧格式即恢复其当时能表达的数据；使用 v2 备份保存新的完整结构数据。

**数据库备份不包括** MySQL 用户/服务配置、其他 schema、磁盘网页原文件。`.cache` 中需要的 HTML 文件应另行备份，换机器需核对路径。`file_exists/hash_verified` 表示登记或核验时的状态，不是持续文件监控。

## 回退

旧五表以 `legacy_v1_*` 保留，迁移前 JSON 备份位于 `data/backups/before-relational-v2-*.mysql.json`。归档不会包含切换后的新修改。先备份当前 v2 数据，再在独立数据库和匹配的旧代码上恢复旧备份验证，确认哪份数据作为后续来源；不要在运行中的工作库直接交换表名。

SQLite 显式回退使用 `WORKBENCH_DB_DRIVER=sqlite`，它只能看到那份 SQLite 中的记录，不会自动获得之后的 MySQL 修改。

## 本机实迁结果

2026-11-26：12 个商品、12 SKU、60 条基础成本、31 条统一来源、5 份已核验网页索引；8 条审计、8 份提报保留。旧 DTO 全量 SHA256 一致，全部12商品的财务结果与迁移前一致。完整报告与备份位于本机被忽略的 `reports/database-v2`、`data/backups`，不公开工作数据。

## 测试

基础80项不需要MySQL。真实集成23项必须明确启用，测试库名以 `_test` 或 `_ci` 结尾且不同于工作库；测试会重置测试库的关系数据，禁止指向业务库。

```powershell
python scripts/configure-mysql.py --with-test-database
$env:WORKBENCH_TEST_MYSQL='1'
$env:WORKBENCH_TEST_MYSQL_DATABASE='temu_workbench_test'
python -m unittest discover -s app/tests -v
```

CI 使用 MySQL 8.0.42 容器，覆盖长ID、外键、关系列读取、跨子表失败回滚、停用SKU、参考登记、全实体备份恢复、模型字典漂移和完整利润工作流。不在失败后自动重放SQL，也不在显式事务中偷偷重连。

## 官方依据

- [InnoDB 一致性读](https://dev.mysql.com/doc/refman/8.0/en/innodb-consistent-read.html)
- [MySQL DDL 隐式提交](https://dev.mysql.com/doc/refman/8.0/en/implicit-commit.html)
- [MySQL 外键](https://dev.mysql.com/doc/refman/8.0/en/create-table-foreign-keys.html)
- [MySQL RENAME TABLE 权限](https://dev.mysql.com/doc/refman/8.0/en/rename-table.html)
- [PyMySQL 连接参数](https://pymysql.readthedocs.io/en/latest/modules/connections.html)

Docker 和独立本机实例仍可通过现有 `compose.mysql.yml`、`scripts/start-mysql-local.py` 使用；确认端口、schema 和本机配置后再启动，避免误连旧工作库。
