# Capability Matrix 研究框架

版本：V2.0 Draft  
用途：Sprint V2.1正式外部调研的统一评价标准  
注意：本文件定义问题和证据标准，不代表最终项目选型结论

## 1. 研究目的

调研不是寻找“功能最多的量化平台”，也不是把优秀项目全部拼接进Vibe-Trading。

唯一问题是：

> 哪些外部能力可以提高本项目发现Mispricing Opportunity、维护长期Thesis、形成可追溯Evidence和持续改善Decision Quality的能力？

## 2. 评价决策

每项能力只能进入以下一种决策：

- `Adopt`：能力成熟且与架构边界一致，可以直接采用依赖或方法。
- `Adapt`：思想有价值，但必须改造为Thesis/Mispricing研究语义。
- `Build`：属于本项目核心差异化，外部方案不能替代。
- `Defer`：未来可能有价值，但当前Research ROI不足。
- `Reject`：与项目使命冲突或会诱导系统退化成交易工具。

## 3. 统一评价字段

每个项目或产品必须记录：

| 字段 | 内容 |
|---|---|
| Identity | 名称、官方地址、类型、许可证/商业属性 |
| Primary Job | 它真正解决什么问题 |
| Best Capability | 最值得借鉴的一项能力 |
| Research Workflow | 它位于研究流程哪个阶段 |
| Point-in-Time | 是否支持时点正确性 |
| Evidence | 是否支持来源、引用、正反证据和版本 |
| Thesis | 是否支持长期逻辑跟踪 |
| Mispricing | 是否帮助识别市场隐含预期与价值偏离 |
| Explainability | 结论能否追溯和反驳 |
| Validation | 是否支持历史重放、实验与校准 |
| Asset Coverage | 股票、ETF、指数、行业及市场范围 |
| Integration Cost | 数据、技术、运维和许可证成本 |
| Lock-in Risk | 是否形成数据或架构锁定 |
| Mission Fit | 对项目北极星的贡献 |
| Decision | Adopt / Adapt / Build / Defer / Reject |
| Why Not More | 为什么不融合更多能力 |

## 4. 能力域

### A. 数据与事实

- Security Master；
- Market Calendar；
- Point-in-Time Fundamentals；
- Corporate Actions；
- Index/ETF Constituents History；
- Announcement/Filings；
- Data Quality；
- Provider Fallback；
- Data Lineage。

### B. 市场与机会发现

- Market Regime；
- Market Breadth；
- Liquidity Stress；
- Flow/ETF Attribution；
- Valuation Context；
- Expectations Gap；
- Mispricing Discovery；
- Asset Expression；
- Candidate Compression。

### C. Thesis与Evidence

- Thesis Tree；
- Thesis Version；
- Causal Dependencies；
- Supporting Evidence；
- Counter Evidence；
- Catalyst；
- Kill Criteria；
- Evidence Freshness；
- Conflict Resolution；
- Review Scheduling。

### D. AI研究

- Document Retrieval；
- Citation Grounding；
- Structured Extraction；
- Price Move Attribution；
- Red-Team Analysis；
- Action Assessment；
- Confidence Calibration；
- Reproducibility；
- Cost Control。

### E. 验证与决策质量

- Backtest；
- Point-in-Time Replay；
- Experiment Tracking；
- Benchmarking；
- False Positive Analysis；
- Missed Opportunity Review；
- Process-versus-Outcome Evaluation；
- Research Quality Metrics。

### F. 交付与工作流

- Daily Intelligence；
- Thesis Change Feed；
- Research Candidate Report；
- Opportunity Alert；
- Watch/Research/Prepare/Action Candidate；
- Collaboration；
- Audit Trail；
- Notification Reliability。

## 5. 研究对象清单

### 开源项目候选池

正式调研至少覆盖30个项目，首批包括：

1. Microsoft Qlib
2. VectorBT
3. Backtrader
4. Hikyuu
5. FinRL
6. PyPortfolioOpt
7. AKShare
8. Tushare
9. RQAlpha
10. Empyrical / Empyrical Reloaded
11. Zipline Reloaded
12. Lean
13. vn.py
14. Backtesting.py
15. bt
16. QSTrader
17. Alphalens Reloaded
18. QuantStats
19. OpenBB
20. NautilusTrader
21. Lumibot
22. pandas-ta
23. mlfinpy
24. TensorTrade
25. Freqtrade
26. Jesse
27. Riskfolio-Lib
28. skfolio
29. FinanceToolkit
30. OpenBB Platform相关数据扩展

正式研究时可根据活跃度、官方维护状态和任务适配性替换重复或失活项目，并记录替换原因。

### 商业产品候选池

1. Bloomberg Terminal
2. Morningstar Direct/Investor
3. Koyfin
4. FinChat
5. AlphaSense
6. Seeking Alpha
7. TIKR
8. FactSet
9. Koyfin/市场可视化同类产品
10. 主流卖方/买方Thesis工作流公开案例

商业产品只研究公开可验证的产品能力，不推断未公开内部实现。

## 6. 证据标准

- 技术项目优先使用官方GitHub仓库、官方文档、许可证和发布记录；
- 产品优先使用官方功能页、帮助文档和公开演示；
- 每项结论附来源链接和核查日期；
- Stars、提交频率和下载量只代表生态信号，不代表研究价值；
- 不以README宣传语直接认定能力成熟；
- 对关键能力至少寻找一个实际接口、数据模型或工作流证据；
- 无公开证据的能力标记为Unknown。

## 7. 评分方式

最终矩阵不输出单一“总分冠军”。每个能力采用：

- `Strong`：直接、成熟支持；
- `Partial`：部分支持或需要明显改造；
- `Weak`：与该能力关联有限；
- `None`：没有相关能力；
- `Unknown`：公开证据不足。

同时必须给出文字判断，防止评分掩盖产品定位差异。

## 8. V2.1最终交付

- 30个以上GitHub项目逐项能力矩阵；
- 7个以上投资研究产品能力矩阵；
- 按领域能力汇总的Best-of-Breed地图；
- Adopt/Adapt/Build/Defer/Reject清单；
- 本项目能力缺口；
- 未来一年可落地能力顺序；
- 明确不引入的项目及原因；
- 所有结论的来源索引。

