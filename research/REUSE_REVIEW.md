# 同类产品与复用结论

核对时间：2026-11-22 至 2026-11-23。以下是有限候选的源码/官方产品资料调查，不是完整市场普查。未验证真实店铺业务能力。

## 推荐决定

保留轻量本地工作台，用许可明确的小组件支撑采集和字段研究。当前未找到已经核实许可证、可直接承担“全托管选品证据＋公司收益门槛＋买手反馈”完整闭环的现成开源应用。因此不以未知授权的大型 ERP 作为今晚底座。

### 1. 店小秘 · 商业 SaaS，对标流程和字段

- 产品：https://www.dianxiaomi.com/
- 全托管文档：https://help.dianxiaomi.com/article/productManagement/2346
- 价格与版本：https://www.dianxiaomi.com/user/vipDetail.htm
- 官方文档列有全托管刊登、站外参考、SKU、申报价格、包装资料和备货等能力；版本页有免费和付费层级。
- 借鉴：采集箱到商品记录、字段模板、SKU 与申报价、失败原因、后续供货衔接。
- 不复制：商业源码、界面素材和平台未核实的限制。以真实业务数据和许可使用条件决定是否直接利用公司已有账号。
- 形态主要是网页服务，不需要为研究它强行安装一个客户端。本轮未购买、未登录、未连接店铺。

### 2. 妙手 ERP · 商业 SaaS，对标套装与采集整理

- 全托管教程：https://erp.91miaoshou.com/help_center/article_2299.html
- 价格：https://erp.91miaoshou.com/price.html
- 观察：公开文档覆盖采集、编辑、SKU 分类和套装资料，价格页列有 Temu 全托管版本权益。
- 借鉴：同款多件/混合套装、来源记录、批量编辑和字段完整性。
- 限制：这是厂商产品实现及权益说明，不能直接认定为全部卖家当前平台规则。

### 3. hiscaler/temu-go · 已下载，字段结构参考优先

- 仓库：https://github.com/hiscaler/temu-go
- 固定提交：1217476f829528bb43f156b28e9a0d175823a368
- 本地：vendor/temu-go
- 许可证：根 LICENSE 已读取，BSD-3-Clause。保留原许可；未运行 SDK 的 API 示例或测试。
- 技术：Go SDK，含全托管与半托管字段，不是完整选品应用。
- 已核对：goods.go 的商品/SKC/SKU 请求层、全托供货价字段与单位说明；goods.category.attribute.go 的类目属性获取结构；entity 中规格与平台 ID 结构。
- 复用方式：优先作为字段映射依据候选；不为了使用 SDK 给 Python/TS MVP 添加 Go 运行服务。今后若确有调用需求，可单独选择实现。
- 关键限制：第三方 SDK 的注释和本地验证规则不是平台当前权威要求；其中字段或注释也可能滞后/不一致，必须与当前店铺和接口文档核对。

### 4. apify/crawlee-python · 已下载，可选采集组件

- 仓库：https://github.com/apify/crawlee-python
- 固定提交：7bd32e7d9cfe219f3aebc13cf631b45fdb14e653
- 本地：vendor/crawlee-python
- 许可证：根 LICENSE 已读取，Apache-2.0。未安装依赖、浏览器或运行网络任务。
- 价值：为公开资料采集提供 HTTP/浏览器爬取、错误处理与队列能力。
- 是否立即采用：单页读取先评估普通 HTTP + HTML 解析是否足够；出现确定的动态页面需求再引入浏览器采集。不为未来可能的规模先上完整队列平台。

### 5. howtimeschange/temu-assistant · 已下载客户端，独立研究参考

- 仓库：https://github.com/howtimeschange/temu-assistant
- 作者 Release：https://github.com/howtimeschange/temu-assistant/releases/tag/v1.0.6
- 作者描述是 Temu 运营数据导出桌面工具，含商品、销售、售后、评价等导出。它不等同于本项目的选品与买手提报闭环，适用后台和模式还要确认。
- 客户端：vendor/installers/Temu.Assistant.Setup.1.0.6.exe，115,880,620 bytes。
- SHA-256：c9c1c6d59cccb7f897006d8f0d0dae2415c183041877ab8757c27c9b9999bd22，与 GitHub Release 返回的 digest 一致。
- 状态：未安装、未运行；本机签名查询为 NotSigned。哈希核对只证明与该 Release 文件一致，不代表完成安全或业务能力审计。
- 许可：README 声明 MIT；GitHub 元数据无根许可证识别，递归目录中未见项目根 LICENSE，仅有捆绑依赖许可。实际复制/分发源码之前核实授权条件。
- 借鉴：导出任务的状态、浏览器登录隔离、渠道适配器思路。今晚不直接整仓二开，不引入其中已捆绑的整套运行时。

### 6. vanky2viva/temu-omni · 只作概念参考

- 仓库：https://github.com/vanky2viva/temu-omni
- 页面描述为自用后台管理端，目录含后端、前端和部署。
- GitHub 元数据无明确许可证；递归树未找到项目 LICENSE/COPYING 文件。
- 决定：不复制代码进应用、不作为底座。没有必要仅为“已经有人做”而承担许可和维护负担。

## 为什么这个 MVP 仍有必要

现成 ERP 已有采集和刊登能力。公司真正需要验证的新增价值是：证据可回看、同规格比较、供货单位和成本一致、经营门槛可确认、核价反馈与后续决定能复盘。先与公司已有 ERP 并存，导入导出稳定后再接适配器。

后续可扩展的方向只保留：

1. 真实全托管类目模板同步与字段检查；
2. 提报、补样和重新报价原因分析；
3. 供应商履约与实际结算反馈到下一次选品。

这些方向均需相应真实数据和验收，不在今晚无条件扩张范围。
