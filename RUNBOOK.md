# 运行与操作说明

## 环境与启动

Python 3.11或更新版本、MySQL 8.0或更新版本。安装requirements中的PyMySQL驱动；无需前端构建或AI账号。

在克隆后的仓库根目录执行：

```bash
python -m pip install -r requirements.txt
python scripts/configure-mysql.py
python scripts/seed-demo.py
python -m app.backend.api.server
```

先启动已有MySQL服务。配置脚本隐藏输入root密码，创建项目库与受限应用账号，仅把应用凭据保存在本机`data/mysql.local.json`。随后加载5个离线案例，启动服务。访问 http://127.0.0.1:8765 ，Ctrl+C停止应用。MySQL服务需保持运行，环境变量优先于本机配置。

Windows前台启动也可执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-workbench.ps1
```

业务数据位于MySQL的`temu_workbench`库，完整JSON备份位于`data/backups/*.mysql.json`，页面快照在`.cache/workbench/`。本机配置、备份、旧SQLite文件与缓存均不提交Git。设置抽屉显示当前数据库，备份列表只提供当前引擎格式，恢复验证失败保留现有数据。

当前MySQL为关系实体v2：商品`products`、SKU`product_skus`、成本`sku_costs`、网址`sources.url`。在Navicat打开`v_product_evidence`视图可以直接关联商品和出处。规则登记也已入库；网页原文件除`.cache/workbench`外还可保留在原有`.cache/profit-evidence`和`.cache/case-evidence`路径，统一由`source_snapshots`索引。完整备份覆盖21张业务/字典表，网页文件本体需另行备份。[数据库说明](docs/DATABASE.md)

## 五个案例是什么

它们研究德国市场收纳用品。商品公开规格和观察日期有出处；采购报价、公司开支、退回及扣款概率、公司门槛和买手反馈是案例假设。运行后六件套当前核价21元、基准预算净收益4.48元、保守2.13元，完整口径见 [利润模型](docs/PROFIT_MODEL.md)。

不运行seed-demo时，服务首次启动只建立最小初始样例。若先启动过服务，现有经营政策不会被seed-demo覆盖；要复现仓库中的40%贡献率案例政策，应在设置中核对现有政策，而不是随意删除工作数据库。

## 日常使用

1. **新建**：候选研究→新建候选；填写名称、标题、材质、货源，保存后填写SKU、尺寸、包装、价格及成本。
2. **查看**：候选列表→查看详情；定位到商品概览，再点“查看商品资料与利润”。
3. **看费用**：商品提报→瀑布图；悬停名称、金额或柱子，手机直接点击。弹出明细含公式、金额、来源；点击可固定，Esc或×关闭。
4. **调预算**：编辑SKU→完整成本参数；调整退回、扣款、人工、分摊数量、资金和税费，再保存SKU。当前利润图随之重算。
5. **改门槛**：设置与集成的40%是原五项贡献政策；每SKU完整参数的15%是净收益目标，两者不是同一个百分比。
6. **跟核价**：反馈跟进→关联SKU，登记原话、日期、证据和建议供货价；核价生效范围及草稿状态有明确标识。
7. **导出**：生成内部提报资料→下载HTML／JSON。HTML可单独打开查看图表明细；该资料不是Temu官方导入模板。
8. **导入交换**：设置与集成→内部CSV／JSON；坏行、重复及缺失会报告，不直接改写真实平台。

## 配置与连接

通过进程环境变量配置，`.env.example`是变量说明，应用不会自动读取`.env`文件。常用变量：

| 变量 | 默认／作用 |
|---|---|
| `WORKBENCH_PORT` | 8765 |
| `WORKBENCH_HOST` | 127.0.0.1，仅本机 |
| `WORKBENCH_DATA_DIR` | 仓库下的data目录；自定义时用绝对路径 |
| `WORKBENCH_DB_DRIVER` | 默认mysql；sqlite仅用于显式回退或测试 |
| `WORKBENCH_MYSQL_HOST` / `WORKBENCH_MYSQL_PORT` | 127.0.0.1 / 3306 |
| `WORKBENCH_MYSQL_DATABASE` | temu_workbench |
| `WORKBENCH_MYSQL_USER` / `WORKBENCH_MYSQL_PASSWORD` | 受限应用账号及密码；不要使用root长期运行应用 |
| `WORKBENCH_ROOT` | 自动识别仓库；通常无需指定 |

DSH／DeepSeek／平台接口目前仍为预留，配置变量并不等于真实采集、读取或写入已经实现。没有这些账号也可完成本地案例。不要把API Key、Cookie或真实账户账单写进提交。

## 演示与部署边界

这是没有登录和角色权限的本地MVP，不要直接用于承载真实商家敏感数据的公网生产部署。仓库不含穿透工具及配置；需要远程演示时，演示者自行管理临时连接、本机在线和展示数据。临时网址掉线不表示MySQL记录丢失。MySQL数据目录由数据库服务管理，不等于项目下的data目录。

## 校验

在根目录运行应用测试，在starter目录运行领域参考测试：

```bash
python -m unittest discover -s app/tests -v
cd starter
python -m unittest discover -s tests -v
cd ..
python scripts/validate_bundle.py
```

可选的JSON Schema库存在时，验证脚本会额外执行Schema检查；不存在时会明确报告未执行，应用本身无需安装它。

## 从SQLite迁移

先停止工作台，确认MySQL目标库为空，再运行 `python scripts/migrate-sqlite-to-mysql.py --app-stopped`。脚本先备份旧SQLite，再迁移全部五表并比较摘要；失败回滚、拒绝覆盖非空MySQL库。完整步骤和独立MySQL实例／Docker选项见[MySQL说明](docs/MYSQL.md)。
