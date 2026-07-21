# AI Investment Researcher Capability Matrix V2

核查日期：2026-07-21  
范围：30个代表性开源量化/研究项目，8个主流投资研究平台  
结论类型：能力提炼，不复制代码，不按Stars直接选型

## 1. Executive Conclusion

没有一个现成项目能够直接成为本项目的“投资大脑”。成熟开源项目主要集中在五类能力：

1. 数据接入与标准化；
2. 因子、模型和实验工作流；
3. 事件驱动或向量化回测；
4. 组合风险与绩效分析；
5. 自动交易执行。

商业研究平台更擅长数据聚合、搜索、筛选、可视化、文档检索和研究交付，但公开能力中同样缺少完整的：

- 可版本化Thesis Tree；
- Supporting/Counter Evidence对称账本；
- “为什么市场卖出”的Temporary/Structural归因；
- Mispricing Opportunity生命周期；
- Research Candidate到Action Candidate的可审计转换；
- 过程质量与结果收益分离的历史复盘。

因此V2的正确策略是：

> 数据、实验、回测、指标和Provider抽象优先借鉴成熟项目；Thesis、Evidence、Mispricing、Price Move Attribution和Decision Quality体系坚持自研。

## 2. 选择方法

“前30个”不解释为GitHub Stars机械排名，因为纯Stars会混入大量只适用于加密货币、自动下单或技术指标的项目。候选集综合考虑：

- 社区影响与维护活跃度；
- 中国市场适配；
- 数据、研究、回测、风险和AI能力代表性；
- 对V2北极星的潜在贡献；
- 不同架构范式的覆盖。

能力状态：

- `Strong`：直接且成熟；
- `Partial`：部分覆盖或需要明显改造；
- `Weak`：只有间接帮助；
- `None`：没有；
- `Unknown`：公开证据不足。

决策：`Adopt / Adapt / Build / Defer / Reject`。

## 3. 30个开源项目能力矩阵

| # | 项目 | 核心能力 | 最值得借鉴 | 与本项目的边界 | 决策 |
|---:|---|---|---|---|---|
| 1 | [Microsoft Qlib](https://github.com/microsoft/qlib) | AI量化研究全流程、数据集、模型、回测、PIT数据库 | 数据集/Handler、实验工作流、point-in-time意识、离线/在线分离 | 核心仍以预测、组合和执行为目标，没有Thesis/Mispricing研究域 | **Adapt** |
| 2 | [VectorBT](https://github.com/polakowo/vectorbt) | 基于NumPy/Pandas和Numba的向量化回测 | 同一数据上大规模参数/场景并行、交互分析速度 | 适合验证规则，不适合作为研究事实或Thesis系统 | **Adapt** |
| 3 | [Backtrader](https://github.com/mementum/backtrader) | Python事件驱动回测 | Feed/Strategy/Broker/Analyzer清晰分层和可插拔分析器 | 偏交易策略与订单模拟，维护节奏相对传统 | **Defer** |
| 4 | [Hikyuu](https://github.com/fasiondog/hikyuu) | C++/Python高性能量化研究、策略部件复用 | 组合式策略部件、A股本地化、高性能计算 | 组件思想有价值，但交易系统范围远超V2首期 | **Adapt** |
| 5 | [FinRL](https://github.com/AI4Finance-Foundation/FinRL) | 金融强化学习与train-test-trade流程 | 明确训练/验证/交易分区、市场摩擦和基准比较 | RL交易目标与宪法冲突；只借鉴实验隔离，不引入交易Agent | **Reject Core / Adapt Validation** |
| 6 | [PyPortfolioOpt](https://github.com/PyPortfolio/PyPortfolioOpt) | 均值方差、Black-Litterman、HRP等组合优化 | 清晰的预期收益—风险模型接口 | V2首期不输出仓位，未来仅用于比较Asset Expression和组合研究 | **Defer** |
| 7 | [AKShare](https://github.com/akfamily/akshare) | 大量中国及全球财经数据接口 | A股市场宽度、行情、公告和宏观数据快速接入 | 上游页面变化和字段稳定性需独立质量层；不能成为唯一事实源 | **Adapt** |
| 8 | [Tushare](https://github.com/waditu/tushare) | 结构化A股行情、财务和基础数据 | 相对统一的A股数据接口和资产主数据来源 | 积分、许可和可得字段需要单独管理；不能与领域模型绑定 | **Adapt** |
| 9 | [RQAlpha](https://github.com/ricequant/rqalpha) | 可扩展、可替换的多证券回测框架 | 中国市场交易规则、事件驱动扩展点和Mod架构 | 可为历史验证提供市场规则参考，不作为研究主流程 | **Adapt** |
| 10 | [Empyrical Reloaded](https://github.com/stefan-jansen/empyrical-reloaded) | 常用收益和风险指标 | 小而稳定的指标原语、与回测引擎解耦 | 只评价价格结果，不能评价研究过程质量 | **Adopt** |
| 11 | [Zipline Reloaded](https://github.com/stefan-jansen/zipline-reloaded) | Python事件驱动回测、Pipeline | 数据Bundle、日历、Pipeline和可重复回测 | 运行和数据约束较重；仅借鉴PIT/日历/Bundle设计 | **Adapt** |
| 12 | [QuantConnect LEAN](https://github.com/QuantConnect/Lean) | 多资产确定性事件引擎、研究到实盘 | 统一证券模型、数据标准化、确定性重放和企业行动处理 | 系统庞大且偏执行；不整体引入 | **Adapt Architecture** |
| 13 | [vn.py](https://github.com/vnpy/vnpy) | 事件引擎、交易Gateway和量化应用生态 | Event Engine与Adapter隔离、国内市场接口经验 | 自动交易不是V2核心，Gateway只作为未来边界参考 | **Reject Core / Defer** |
| 14 | [Backtesting.py](https://github.com/kernc/backtesting.py) | 简洁策略回测与优化 | 极低学习成本、清晰结果对象和可视化反馈 | 适合小型验证，不适合PIT基本面研究平台 | **Adapt UX** |
| 15 | [bt](https://github.com/pmorissette/bt) | 组合回测、Algo树组合 | 将策略拆为可组合算法节点 | 可借鉴Research Pipeline组合，但不复用交易语义 | **Adapt** |
| 16 | [QSTrader](https://github.com/mhallsmoore/qstrader) | 事件驱动组合回测 | Portfolio、Execution、Risk分离 | 项目重点是交易模拟，V2短期收益有限 | **Defer** |
| 17 | [Alphalens Reloaded](https://github.com/stefan-jansen/alphalens-reloaded) | 因子预测能力分析 | IC、分层收益、换手、行业中性和tear sheet | 可验证内部筛选特征，不能证明Thesis或Mispricing | **Adopt / Adapt** |
| 18 | [QuantStats](https://github.com/ranaroussi/quantstats) | 组合绩效统计和HTML报告 | 快速生成可读绩效报告 | 指标与现有能力可能重复，只复用缺口部分 | **Adopt Selectively** |
| 19 | [OpenBB](https://github.com/OpenBB-finance/OpenBB) | 面向分析师、量化和AI Agent的开放数据平台 | Provider抽象、标准化输出、扩展接口和数据命令层 | 不引入其整个平台；优先借鉴Provider Contract和数据血缘 | **Adapt Strongly** |
| 20 | [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | Rust原生、确定性事件驱动交易引擎 | 可重放事件、严格状态机、研究/仿真一致性 | 对日频研究过重；未来需要高吞吐事件回放时再评估 | **Defer** |
| 21 | [Lumibot](https://github.com/Lumiwealth/lumibot) | 可回测AI Agent策略、研究/多空辩论和券商连接 | 研究者—Bull—Bear角色分离、Agent结果可检查 | 最终仍以交易为中心；只借鉴Evidence Pack与反方审查模式 | **Adapt Research Pattern / Reject Execution** |
| 22 | [Technical Analysis Library](https://github.com/bukosabino/ta) | Pandas/NumPy技术指标特征 | 标准化指标接口和独立测试 | 项目已有大量因子；技术指标不能成为Mispricing结论 | **Defer** |
| 23 | [Microsoft RD-Agent](https://github.com/microsoft/RD-Agent) | 自动化数据/模型R&D迭代 | 实验—反馈—知识积累闭环和可追踪自动研究 | 容易把目标带回因子挖掘；仅在研究质量评价成熟后借鉴 | **Adapt Later** |
| 24 | [TensorTrade](https://github.com/tensortrade-org/tensortrade) | 模块化强化学习交易环境 | Action/Reward/Observer等环境组件拆分 | Reward优化交易与本项目目标冲突 | **Reject Core** |
| 25 | [Freqtrade](https://github.com/freqtrade/freqtrade) | 加密货币Bot、回测、优化、Dry-run和保护机制 | 配置验证、Dry-run、任务监控、运行保护 | 自动交易和超参优化不进入产品主线 | **Reject Core / Adapt Ops** |
| 26 | [Jesse](https://github.com/jesse-ai/jesse) | 加密交易策略研究、回测和调试 | 策略调试体验、可视化运行日志 | 市场与使命不匹配 | **Reject Core** |
| 27 | [Riskfolio-Lib](https://github.com/dcajasn/Riskfolio-Lib) | 多种风险度量和组合优化 | 丰富风险模型、约束和风险归因 | 首期不做仓位与组合建议；可用于未来Asset Expression风险比较 | **Defer** |
| 28 | [skfolio](https://github.com/skfolio/skfolio) | scikit-learn风格组合优化与模型选择 | 交叉验证、Pipeline、Estimator协议和避免过拟合的统一接口 | 组合构建后置，但验证接口值得借鉴 | **Adapt Validation / Defer Portfolio** |
| 29 | [FinanceToolkit](https://github.com/JerBouma/FinanceToolkit) | 透明财务分析、比率和估值工具 | 指标公式透明、批量财务计算、可复核数据转换 | 数据许可证和供应商需要另行解决；适合作为财务派生层参考 | **Adapt** |
| 30 | [Pyfolio Reloaded](https://github.com/stefan-jansen/pyfolio-reloaded) | 组合风险与绩效tear sheet | 收益、回撤、风险暴露和压力期分析 | 价格结果分析成熟，但不等于Decision Quality | **Adopt Selectively** |

## 4. 横向能力热力图

| 项目族 | PIT数据 | 批量研究 | 因子验证 | 回测重放 | 风险分析 | Evidence/引用 | Thesis版本 | Mispricing归因 |
|---|---|---|---|---|---|---|---|---|
| Qlib | Strong | Strong | Strong | Strong | Partial | None | None | None |
| VectorBT | Weak | Strong | Partial | Strong | Partial | None | None | None |
| Zipline/RQAlpha/LEAN | Strong | Partial | Partial | Strong | Partial | None | None | None |
| AKShare/Tushare/OpenBB | Partial | Strong | None | None | None | Partial | None | None |
| Alphalens | Partial | Strong | Strong | Weak | Partial | None | None | None |
| Empyrical/QuantStats/Pyfolio | Weak | Partial | None | None | Strong | None | None | None |
| PyPortfolioOpt/Riskfolio/skfolio | Weak | Strong | None | Partial | Strong | None | None | None |
| FinRL/TensorTrade/RD-Agent | Partial | Strong | Partial | Strong | Partial | Weak | None | None |
| Trading engines | Partial | Partial | Weak | Strong | Strong | None | None | None |
| 本项目V2目标 | Strong | Strong | Partial | Strong | Partial | **Strong** | **Strong** | **Strong** |

最明显的市场空白位于最后三列，这些正是本项目应当形成长期资产的部分。

## 5. 投资研究平台能力矩阵

| 平台 | 官方公开的核心能力 | 最值得借鉴 | 不应复制 | 决策 |
|---|---|---|---|---|
| [Bloomberg Terminal](https://professional.bloomberg.com/products/bloomberg-terminal/) | 多资产数据、新闻、研究、分析、协作和组合工具 | 从市场全景逐层下钻到行业/公司，数据与工作流高度统一 | 交易执行、全功能终端和昂贵数据体系 | **Adapt information hierarchy** |
| [Morningstar Direct](https://www.morningstar.com/business/products/direct) | 数据、独立研究、评级、同类比较、组合分析和报告 | 统一方法论、peer comparison、研究监控和可信报告模板 | 单一评级替代研究过程 | **Adapt research consistency** |
| [Koyfin](https://www.koyfin.com/features/) | 市场Dashboard、筛选、图表、Watchlist、Alert、公司与ETF分析 | 快速市场态势、可配置工作区、Watchlist变化和ETF穿透 | 将大量筛选条件当作Mispricing Engine | **Adapt UX and monitoring** |
| [FinChat](https://finchat.io/) | 全球财务、公司KPI、IR内容、估值、AI Copilot和通知 | 第一方IR资料与公司特有KPI组成Evidence Pack，AI减少资料整理 | “聊天答案”代替版本化Thesis | **Adapt evidence workflow** |
| [AlphaSense](https://www.alpha-sense.com/platform/generative-search/) | 跨文档搜索、Deep Research、Monitoring、内部/外部内容和逐段引用 | 精确引用、跨文档综合、重复研究问题批量化和持续监控 | 依赖高成本内容库，或让生成式搜索成为最终判断 | **Adapt strongly for Evidence Engine** |
| [Seeking Alpha](https://help.seekingalpha.com/premium/seeking-alpha-premium-feature-list) | 作者观点、卖方观点、Quant Rating、因子分级、提醒和Transcript | 同一资产并列多个观点，可用于Counter Evidence与分歧发现 | Strong Buy/Buy/Sell标签、总分驱动和观点数量当质量 | **Adapt disagreement only** |
| [TIKR](https://support.tikr.com/hc/en-us/articles/39071375390235-How-do-I-use-TIKR-s-Estimates-feature) | 历史财务、Forward Estimates、分析师数量和研究资料 | 将实际值与市场预期明确分开，帮助构建Market-Implied View | 把Consensus当成真实价值 | **Adapt expectations layer** |
| [FactSet Workstation](https://www.factset.com/marketplace/catalog/product/factset-workstation) | 统一数据、研究、筛选、警报、风险归因、内部研究记录和AI工作流 | 永久实体标识、内部研究记录、决策审计和Security Explanation | 全前台交易与平台规模 | **Adapt research operating model** |

## 6. Best-of-Breed能力地图

| 本项目能力 | 最佳外部参考 | V2决策 |
|---|---|---|
| Point-in-Time与实验工作流 | Qlib、Zipline、LEAN | 借鉴数据版本、日历和重放，不整体引入 |
| Provider抽象 | OpenBB | 设计自己的EvidenceProvider协议 |
| A股数据覆盖 | AKShare、Tushare | 多Provider互证，建立质量层和fallback |
| 因子有效性分析 | Alphalens | 复用/适配IC、分层和换手方法 |
| 向量化历史验证 | VectorBT | 用于规则与候选结果批量检验 |
| 风险与绩效 | Empyrical、Pyfolio、QuantStats | 采用成熟指标，不重复造轮子 |
| 组合模型 | PyPortfolioOpt、Riskfolio、skfolio | 延后到Asset Expression成熟之后 |
| 证据搜索与引用 | AlphaSense、FinChat | 自研Evidence Ledger，借鉴引用与第一方内容优先 |
| 市场态势与工作台 | Bloomberg、Koyfin | 借鉴信息层级，不复制UI |
| 研究一致性 | Morningstar、FactSet | 建立统一研究模板、peer context和审计记录 |
| 多观点与反方 | Seeking Alpha、Lumibot | 明确Bull/Bear/Unknown，不采用评级语言 |
| 市场预期层 | TIKR、Koyfin、FactSet | 区分历史实际、Consensus和Research View |
| Thesis Tree/Version | 无成熟直接方案 | **Build** |
| Price Move Attribution | FactSet Security Explanation提供局部参考 | **Build** |
| Mispricing Opportunity生命周期 | 无成熟直接方案 | **Build** |
| Decision Quality历史评价 | 无成熟直接方案 | **Build** |

## 7. Adopt / Adapt / Build / Defer / Reject

### Adopt

- 标准风险与绩效指标；
- 因子IC、分层收益、换手等验证方法；
- 市场日历、企业行动和基准比较的成熟定义；
- Provider接口与结构化返回的设计思想。

### Adapt

- Qlib的实验与数据工作流；
- VectorBT的批量历史验证；
- LEAN/RQAlpha/Zipline的事件重放；
- OpenBB的数据Provider抽象；
- AlphaSense的逐段引用和跨文档综合；
- FinChat的公司特有KPI和第一方材料优先；
- FactSet的内部研究记录和价格变动解释；
- Koyfin的市场态势与Watchlist变化体验；
- Morningstar的统一研究方法与peer comparison。

### Build

- Thesis Tree、Dependency和Version；
- Evidence/Counter Evidence对称账本；
- EvidenceSet与历史时点输入快照；
- Mispricing Opportunity；
- Price Move Attribution及Temporary/Structural/Unknown；
- Research Candidate与Action Assessment；
- Action Candidate固定Alert门槛；
- Research Quality与Decision Quality评价；
- 过程正确/结果错误的复盘分类。

### Defer

- 组合权重优化；
- 多市场实盘规则；
- 高频事件引擎；
- 插件市场；
- 分布式强化学习；
- 多Agent自动R&D。

### Reject

- 自动交易作为核心目标；
- RL Agent直接决定资产买卖；
- 强买/买入/卖出式评级；
- 用大量技术指标替代错误定价研究；
- 根据单一综合分每天推荐资产；
- 把回测收益当作Thesis正确性的唯一证明。

## 8. 对当前Vibe-Trading的具体影响

1. 不引入另一套完整量化框架替代现有回测系统。
2. 首先补齐PIT数据、Evidence和实验版本，而不是增加更多因子。
3. AKShare继续作为快速数据源，但必须增加Provider质量、时点和fallback层。
4. V1的Score Breakdown只作为Discovery内部特征，不再成为用户结论。
5. Agent/Swarm可借鉴Lumibot的Bull/Bear审查，但输出必须进入结构化Evidence与Assessment。
6. 历史验证可优先借鉴Qlib、VectorBT和Alphalens方法，不引入其交易执行链。
7. Web工作台学习Koyfin/Bloomberg的由市场到资产下钻，但首页首先展示Market State、Thesis Changes和Research Queue。
8. Evidence Engine学习AlphaSense的引用精度和FinChat的第一方资料聚合，但核心记录自建。

## 9. V2.1产品能力结论

本项目真正的差异化不是“拥有AI”或“拥有更多数据”，而是把外部成熟能力组织成以下闭环：

```text
可信事实
→ 长期Thesis记忆
→ 市场隐含预期
→ 为什么市场卖出
→ Temporary / Structural判断
→ Mispricing Opportunity
→ 最佳Asset Expression
→ Research Candidate
→ Action Assessment
→ 历史验证与持续修正
```

现有工具普遍能完成其中两到四步，但没有完成整个闭环。这是本项目未来五年的核心建设价值。

## 10. Source Index

开源项目来源均为表格所链接的官方GitHub仓库，仓库状态与项目描述核查于2026-07-21。产品能力主要依据：

- [Bloomberg Terminal官方页](https://professional.bloomberg.com/products/bloomberg-terminal/)
- [Morningstar Direct官方页](https://www.morningstar.com/business/products/direct)
- [Koyfin Features](https://www.koyfin.com/features/)
- [FinChat官方页](https://finchat.io/)
- [AlphaSense Platform](https://www.alpha-sense.com/platform/generative-search/)
- [AlphaSense生成式研究与引用](https://www.alpha-sense.com/solutions/generative-ai-investment-research/)
- [Seeking Alpha Premium Features](https://help.seekingalpha.com/premium/seeking-alpha-premium-feature-list)
- [TIKR Estimates说明](https://support.tikr.com/hc/en-us/articles/39071375390235-How-do-I-use-TIKR-s-Estimates-feature)
- [FactSet Workstation](https://www.factset.com/marketplace/catalog/product/factset-workstation)

## 11. 研究限制

- 商业平台研究仅基于公开官方资料，没有使用付费终端实际操作；未公开能力标记为不作判断。
- GitHub活跃度与Stars仅作为生态背景，没有进入最终能力决策。
- 本报告判断的是“对本项目使命的适配度”，不是对这些项目整体质量的排名。
- 任何依赖引入仍需在Sprint V2.4单独评估许可证、维护成本、数据授权和与现有代码的重叠。

