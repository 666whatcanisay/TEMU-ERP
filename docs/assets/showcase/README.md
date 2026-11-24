# 首页素材说明

2026-11-24，通过 Codex 内嵌浏览器拍摄本项目实际页面，未使用桌面或用户现有浏览器窗口截图。

回环服务使用独立 MySQL `temu_workbench_test` 和 [五商品案例](../../../fixtures/demo-catalog.json)，不读取工作库或卖家账号。实际内容宽约 632 像素；`product.jpg` 为完整页面，其余为视区。视口覆盖未改变实际尺寸，不称为 390px 手机或 1365px 桌面截图。

| 文件 | 内容 |
|---|---|
| [research.jpg](research.jpg) | 基准/保守与亏损 |
| [product.jpg](product.jpg) | 商品入口、金额、两类图表与 SKU |
| [cost-detail.jpg](cost-detail.jpg) | 退款风险公式、合计与来源 |
| [feedback.jpg](feedback.jpg) | 多次 SKU 核价和凭证 |
| [review.jpg](review.jpg) | 内部评审与待办 |

公开页面支持商品规格和观察价；采购、概率、数量、税费准备、门槛和买手反馈是可调整案例输入。“已核对”是案例内状态，不是真实买手回执。[来源登记](../../../research/sources.json) · [利润假设](../../PROFIT_MODEL.md)

原有 `docs/assets/research.png`、`product.png`、`cost-detail.png` 保留供历史参考。

`cover.svg`、`workflow.svg`、`architecture.svg` 由 [build-showcase-assets.py](../../../scripts/build-showcase-assets.py) 生成，实线为实现、虚线为预留，人工平台操作单列。重建命令：

```bash
python scripts/build-showcase-assets.py
```
