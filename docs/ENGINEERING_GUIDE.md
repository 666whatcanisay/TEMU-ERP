# 工程阅读指南

## 追踪一条操作

六件套当前核价 21 元：页面请求商品详情，应用选择对应 SKU 的有效核价，领域层计算完整成本与情景，前端把同一结果渲染成摘要、图表和浮层。评审单从持久化数据准备资料，不从浏览器显示文本反推金额。

```text
app.js / workflow.js
        ↓ HTTP
api/server.py
        ↓ 用例
application/services.py
        ├─ domain/pricing.py：五项贡献与经营门槛
        ├─ domain/profit_model.py：完整成本、情景与底价
        ├─ domain/evidence.py：来源与可比性
        └─ adapters/storage_mysql.py：业务记录与历史
        ↓ 结构化结果
profit-view.js：摘要、图表、明细与评审模板
profit-popover.js：鼠标、键盘、点击和定位
```

## 金额：区分两种口径

[pricing.py](../app/backend/domain/pricing.py) 保留原五项贡献；[profit_model.py](../app/backend/domain/profit_model.py) 计算完整费用。`scenario` 生成带 key、分组、公式、金额和来源的费用行，`evaluate_full` 输出情景和底价。前端不维护第二套利润算法。

明细四位小数，主结果到分。金额、币种、单位与确认状态由领域校验。六件套 `21 − 16.5184 = 4.4816` 可在 [利润测试](../app/tests/test_full_profit.py) 复核；[模型说明](PROFIT_MODEL.md) 展开费用责任与假设。

## 核价：记录与生效分开

[services.py](../app/backend/application/services.py) 的 `add_feedback` 保存原话、凭证、日期和 SKU，缺依据降为草稿。`_latest_buyer_income` 选择适用核价，`sku_view` 保留原始报价。多 SKU 时不能把商品级模糊核价覆盖所有变体。

见 [用例测试](../app/tests/test_services.py) 和 [工作流测试](../app/tests/test_business_workflow.py)：不匹配 SKU、草稿、原价未变及缺字段路径。

## 保存：业务操作的事务边界

`save_candidate` 先校验，再在事务中读旧记录、写历史、保存商品。异常一起回滚。承诺是单次保存不留下半成功历史，不等同多人协同或历史防篡改。

[存储测试](../app/tests/test_storage.py) 的 `test_failed_candidate_save_rolls_back_revision_and_record` 在历史写入后强制中断最终保存：验证商品和历史不变，再恢复保存检查历史。[MySQL 测试](../app/tests/test_mysql_storage.py) 继承该契约，在 InnoDB 上实际运行。

## 数据库：共享语义，隔离引擎差异

[storage_relational.py](../app/backend/adapters/storage_relational.py) 维护记录与修订语义，[storage_mysql.py](../app/backend/adapters/storage_mysql.py) 处理参数化 SQL、连接、事务和备份。JSON 载荷保留未知字段和字符串 ID，索引列用于查找。此取舍迁移成本低，但尚未将所有属性规范化为独立关系表。

[storage_state.py](../app/backend/adapters/storage_state.py) 定义五表备份及摘要。SQLite 保留迁移、显式回退和基础测试路径。详见 [MySQL](MYSQL.md)。

## 依据：出处能支持什么

[来源登记](../research/sources.json) 保留出处。[字段映射](../contracts/temu_field_map.json) 是候选，不是已取得的真实后台模板。商品页支持尺寸、件数和观察价格，不支持公司采购价或风险概率。

[规则提取](../app/backend/adapters/extraction_rules.py) 的候选与人工确认分开。模型和 RPA 由 [端口契约](../app/backend/domain/ports.py) 隔离，未实现适配器不会假成功。

## 后续如何改

| 需求 | 主要位置 | 应验证 |
|---|---|---|
| 新费用 | 领域、参数契约与明细渲染 | 情景、合计、底价、导出一致 |
| 换采集渠道 | 独立适配器与来源状态 | 快照、候选提取、人工确认 |
| 调费用浮层 | `profit-popover.js` 与样式 | 悬停/点击/键盘、关闭、场景切换 |
| 接类目模板 | 模板适配器、版本与映射 | 不猜枚举、平台 ID 和必填项 |
| 多人协同 | 用例版本控制、权限与部署 | 过期草稿冲突、隔离与权限 |

当前仅单人本地场景。MySQL 不自动带来账号权限、并发编辑保护或生产部署能力。
