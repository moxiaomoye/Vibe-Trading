# AI Investment Researcher 一年路线图 V2

版本：V2.0  
规划周期：12个月  
排序原则：Research Quality ROI，而不是功能数量

## 1. 路线图原则

每个阶段只有在前一阶段的研究闭环通过验收后才进入下一阶段。开发顺序遵循：

```text
定义正确问题
→ 建立可追溯事实
→ 建立长期Thesis记忆
→ 发现错误定价
→ 形成行动观察等级
→ 历史验证
→ 扩大资产与市场
```

技术设施只在当前研究能力确有需要时建设。

## 2. Sprint路线

### Sprint V2.0：产品重构设计

时间：当前Sprint

交付：

- `PROJECT_CONSTITUTION.md`
- `DOMAIN_MODEL_V2.md`
- `ARCHITECTURE_V2.md`
- `ROADMAP_V2.md`
- Capability Matrix评价框架

验收：

- 北极星、边界和禁止事项无冲突；
- V1每个核心模块有明确去留；
- 领域模型支持Thesis树、版本、证据、错误定价、资产表达和复核；
- Daily Report与Opportunity Alert语义分离；
- 不修改代码。

### Sprint V2.1：能力研究与产品能力地图

时间：第1—2个月

研究对象：

- 投资研究平台：Bloomberg、Morningstar、Koyfin、FinChat、AlphaSense、Seeking Alpha、TIKR等；
- 开源项目：Qlib、VectorBT、Backtrader、Hikyuu、FinRL、PyPortfolioOpt、AKShare、Tushare、RQAlpha、Empyrical及至少20个相关项目；
- 必要的论文和公开技术文档。

交付：

- 完整Capability Matrix；
- 能力差距地图；
- `Adopt / Adapt / Build / Defer / Reject`决策；
- 产品研究工作流；
- 不复制代码和UI。

验收：每项借鉴能力必须说明它如何提高Research Quality，以及为什么适合或不适合本项目。

### Sprint V2.2：Thesis Engine设计

时间：第2—3个月

交付设计：

- Thesis Tree；
- ThesisVersion与变更原因；
- Evidence Ledger与Counter Evidence；
- Catalyst；
- Kill Criteria；
- Review机制；
- Confidence内部值与外部Band；
- Thesis更新报告模板；
- 历史时点和append-only原则。

验收场景：AI CapEx上游证据变化能够影响下游GPU、光模块、PCB和服务器Thesis，但每个节点保留独立判断。

### Sprint V2.3：Mispricing与Research Decision设计

时间：第3—4个月

交付设计：

- Mispricing Opportunity；
- Market-Implied View与Research View；
- Price Move Attribution；
- Temporary / Structural / Uncertain；
- Asset Expression；
- Research Candidate；
- Action Level；
- Daily Research Report；
- Opportunity Alert；
- 历史验证和False Positive分类。

验收场景：系统能够区分“低PE但行业衰退”“高PE但长期盈利增长尚未计价”“ETF赎回造成暂时性压力”和“基本面永久破坏”。

### Sprint V2.4：第一版代码迁移方案

时间：第4—5个月

本阶段仍先提出迁移方案，经审查后才修改代码。

交付：

- V1→V2迁移顺序；
- 新旧数据库双读/回滚方案；
- API兼容策略；
- 模块拆分和依赖规则；
- 测试金字塔；
- 数据迁移和历史保留策略；
- 首个最小垂直切片定义。

首个垂直切片建议：

```text
一个MarketState
→ 一棵AI基础设施Thesis Tree
→ 一项Mispricing Opportunity
→ 股票/ETF两种Asset Expression
→ 一份Research Candidate报告
→ 一份Daily Report
```

### Sprint V2.5：Thesis Engine MVP

时间：第5—7个月

开发范围：

- Thesis、Version、Evidence和Review持久化；
- 一棵人工确认的AI基础设施Thesis Tree；
- 结构化AI更新；
- 证据正反分类与来源追踪；
- Thesis变化历史页面；
- 单元测试、时点测试和审计日志。

不开发Mispricing自动判定和Action Candidate，先验证长期研究记忆是否可靠。

### Sprint V2.6：Opportunity Discovery MVP

时间：第7—9个月

开发范围：

- A股科技MarketState；
- Price Move Attribution；
- Mispricing Opportunity；
- Asset Expression；
- Research Candidate；
- AI Action Assessment；
- 研究报告取代总分排名。

验收重点：False Positive、证据缺口和反方质量，不以短期收益验收。

### Sprint V2.7：Daily Intelligence与Alert

时间：第9—10个月

开发范围：

- A股交易日日历；
- 18:30 Daily Research Report；
- 无机会结论；
- Opportunity Alert固定门槛；
- 飞书和邮箱独立投递状态；
- 幂等、重试、失败恢复；
- 报告与历史版本浏览。

### Sprint V2.8：历史验证与校准

时间：第10—12个月

开发范围：

- point-in-time数据包；
- 历史Discovery重放；
- Confidence校准；
- Temporary/Structural归因复盘；
- False Positive、合理失败、运气盈利和典型错误分类；
- Research Quality仪表盘；
- Missed Opportunity回顾。

达到验收后，再决定是否扩大A股行业或进入港股/美股。

## 3. ROI优先级

| 优先级 | 能力 | Research ROI | 原因 |
|---|---|---:|---|
| 1 | Evidence时点、来源和版本 | 极高 | 没有可信Evidence，所有AI结论都不可审计 |
| 2 | Thesis Engine | 极高 | 形成长期研究记忆和因果主轴 |
| 3 | Price Move Attribution | 极高 | 回答“为什么别人卖”并减少伪错杀 |
| 4 | Mispricing Opportunity | 极高 | 将系统从便宜筛选器升级为错误定价研究员 |
| 5 | Research Report与反方审查 | 高 | 降低总分和流畅叙事造成的False Positive |
| 6 | Daily Intelligence | 高 | 每天产生研究价值且不制造推荐 |
| 7 | Historical Validation | 高 | 检验过程质量和Confidence校准 |
| 8 | Action Level与Alert | 中高 | 将研究连接到真实行动观察，但必须建立在前述能力之上 |
| 9 | ETF/行业表达 | 中高 | 降低单股风险并找到更纯粹表达 |
| 10 | 多市场 | 中 | 有价值但会放大数据与制度复杂度 |
| 11 | 插件平台/多Agent | 低 | 首年不直接提高核心研究质量 |

## 4. Capability Matrix评价框架

V2.1对每个平台或项目统一评价以下能力：

| 能力域 | 核心问题 | 与本项目关系 |
|---|---|---|
| Market Intelligence | 是否能解释市场状态与变化 | 必需 |
| Point-in-Time Data | 是否避免未来数据污染 | 必需 |
| Thesis Management | 是否支持长期逻辑、版本和失效条件 | 核心差异化 |
| Evidence System | 是否支持来源、正反证据和时间 | 核心差异化 |
| Mispricing Discovery | 是否识别预期与价值偏离 | 核心差异化 |
| Price Move Attribution | 是否解释为什么市场卖出 | 核心差异化 |
| Asset Expression | 是否比较股票、ETF、行业和指数 | 必需 |
| Research Prioritization | 是否压缩研究范围 | 必需 |
| Explainability | 结论是否可追溯和可反驳 | 必需 |
| Historical Validation | 是否能在历史时点重放研究 | 必需 |
| Portfolio Construction | 是否支持组合优化 | 后期可选 |
| Execution | 是否自动交易 | 核心拒绝 |
| Data Connectors | 是否提供可靠批量数据接口 | 可借鉴 |
| Experiment Tracking | 是否保存配置、数据和结果版本 | 可借鉴 |
| Notification | 是否支持可靠交付 | 配套能力 |
| Extensibility | 是否通过稳定接口扩展 | 后期能力 |

每个对象最终给出：

- `Adopt`：能力与项目高度一致，可直接采用思想或依赖；
- `Adapt`：值得借鉴，但需要围绕Thesis/Mispricing重构；
- `Build`：市场方案缺失，是本项目核心差异化；
- `Defer`：未来有价值，当前ROI不足；
- `Reject`：与项目使命冲突。

## 5. 初步能力假设（待V2.1证据验证）

| 项目类型 | 预期可借鉴能力 | 当前态度 |
|---|---|---|
| Qlib | 数据集、实验、模型与回测工作流 | Adapt |
| VectorBT | 向量化研究和大规模参数验证 | Adapt |
| Backtrader / RQAlpha / Hikyuu | 事件驱动回测和市场规则建模 | Adapt |
| AKShare / Tushare | A股数据适配与字段覆盖 | Adapt，不形成单一供应商锁定 |
| Empyrical / QuantStats类 | 绩效与风险指标 | Adopt/Adapt |
| PyPortfolioOpt | 资产表达和未来组合研究 | Defer |
| FinRL类 | 强化学习交易 | Reject为核心能力，研究其评估方法即可 |
| Bloomberg / Morningstar | 数据组织、研究工作流、资产比较 | Adapt |
| AlphaSense | Evidence检索、引用和企业信息发现 | Adapt |
| Koyfin / TIKR / FinChat | 可读研究界面、财务比较和AI解释 | Adapt |

该表不是正式调研结论。V2.1必须逐项使用官方资料验证，并扩展至至少30个GitHub项目。

## 6. 明确不开发清单

未来一年默认不开发：

- 自动交易、自动下单和券商执行连接；
- 分钟级、日内和隔夜涨跌预测；
- 每日股票推荐；
- 仓位建议；
- 强化学习交易Agent；
- 为演示效果增加多个Agent人格；
- 没有Evidence需求前的大规模RAG平台；
- 没有真实扩展需求前的插件市场；
- 微服务、Kubernetes和复杂分布式架构；
- 中美港同时覆盖；
- 无法回测和解释的黑箱总分；
- 只因GitHub热门而引入框架。

## 7. 年度成功门槛

一年后系统应满足：

1. 每个A股交易日稳定生成有证据的Daily Research Report。
2. 没有机会时明确输出继续等待。
3. 至少维护一棵真实、版本化的AI基础设施Thesis Tree。
4. Research Candidate均能解释市场为什么卖出。
5. 所有Action Candidate拥有正反证据、Kill Criteria和Next Review。
6. Opportunity Alert满足固定门槛且数量保持稀缺。
7. 任一历史候选可按当时Evidence重放。
8. Research Quality指标可以持续计算。
9. 用户看到的是研究报告和变化，而不是总分排行榜。
10. 项目仍然可以单机可靠运行，没有因过早平台化失去开发效率。

## 8. 阶段退出与扩张规则

只有满足以下条件才扩展到新的行业或市场：

- 当前资产覆盖的Evidence完整率稳定；
- Thesis更新和历史版本可靠；
- Action Candidate False Positive已有可解释基线；
- 历史验证不存在明显前视偏差；
- 日报和Alert投递稳定；
- 新市场带来的研究价值高于数据、规则和运维成本。

否则继续改进A股科技研究闭环，而不是扩大股票数量。

