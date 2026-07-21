# Mispricing Opportunity Engine V2

版本：V2.3  
状态：领域与应用设计，不修改代码或数据库

## 1. 使命

Mispricing Opportunity Engine负责判断：

> 市场价格正在反映什么预期，研究系统对长期价值的判断有何不同，这个差异为什么出现，以及它是否值得分配研究时间。

它寻找的是“可能的错误定价”，不是便宜、超跌、龙头、高增长或技术超卖。

## 2. 输入与输出

### 输入

- 当前及历史MarketState；
- 有效ThesisVersion；
- Asset和AssetExpression；
- 价格、估值、财务、预期、行业、资金流和公告Evidence；
- 关联Catalyst、Kill Criteria和未解决EvidenceConflict；
- 同行业、同Thesis及基准资产的相对数据。

### 输出

- `MarketImpliedView`；
- `PriceMoveAttribution`；
- `PermanenceAssessment`；
- `MispricingOpportunity`；
- `AssetExpressionComparison`；
- `ResearchCandidate`；
- `ActionAssessment`；
- `AlertEligibility`。

## 3. Discovery Funnel

```text
全市场Asset
→ 可研究Universe
→ Thesis Exposure已证明
→ 出现价格/预期偏离
→ 解释为什么市场卖出
→ 判断Temporary / Structural / Unknown
→ 验证长期Thesis完整性
→ 比较Asset Expression
→ Research Candidate
→ AI Action Assessment
```

每一层都保存被排除数量和原因。只有最终少数候选进入用户视野；被排除对象保留用于False Positive和Missed Opportunity复盘。

## 4. Market-Implied View

系统必须先解释价格在交易什么，再表达不同观点。

字段：

- 当前估值与历史/同行位置；
- 市场一致预期及修订方向；
- 价格反应隐含的增长、利润率或风险变化；
- 市场主要叙事；
- 已被充分计价的利好；
- 可能被过度计价的利空；
- 证据来源和时间；
- 未知项。

Consensus不是市场真实想法的完整替代。价格、估值、卖方预期、行业表现和资金行为只能共同形成“市场隐含观点”的估计。

## 5. Price Move Attribution

### 原因分类

| Category | 示例 |
|---|---|
| Fundamentals | 订单、收入、利润率、现金流真实恶化 |
| Expectations | 业绩增长但低于更高市场预期 |
| Valuation | 无基本面变化的估值压缩 |
| Passive Flow | ETF赎回、指数调整、被动减仓 |
| Active Flow | 主动基金减仓、风格切换 |
| Liquidity | 杠杆去化、融资平仓、市场深度下降 |
| Macro/Rates | 利率、汇率、商品和经济预期 |
| Policy | 监管、产业政策和制度变化 |
| Event | 事故、诉讼、调查、交易或突发事件 |
| Technical | 止损、趋势和量化交易放大 |
| Unknown | 公开Evidence不足 |

一轮下跌允许多个原因。系统必须区分“触发原因”“放大机制”和“背景条件”。

### 原因持续性

- `Temporary`：影响时间有限，长期现金流或Thesis未被实质改变；
- `Structural`：改变长期需求、竞争、资本回报或治理；
- `Uncertain`：当前Evidence不足或原因相互冲突。

AI不得为了形成Opportunity而强行选择Temporary。Unknown和Uncertain是合法且重要的结果。

### 归因输出

每个原因包含：

- 描述；
- 角色：Trigger / Amplifier / Background；
- 相对重要性；
- Temporary / Structural / Uncertain；
- 支持Evidence；
- Counter Evidence；
- 替代解释；
- Confidence；
- 下一验证事件。

## 6. Mispricing判断

Mispricing Hypothesis必须同时存在：

1. 有效的长期Thesis；
2. 明确的Market-Implied View；
3. 不同于市场的Research View；
4. 可描述的Variant Wedge；
5. 有Evidence支持价格偏离主要由暂时或可逆因素造成；
6. 有明确反方与失效条件；
7. 有潜在收敛路径或下一验证窗口。

### 常见非Mispricing

- 行业永久萎缩导致低PE；
- 盈利处于周期顶部导致表面低估值；
- 高增长已完全计价；
- 公司治理或会计质量恶化；
- 只有跌幅，没有价值证据；
- 只有政策口号，没有盈利传导；
- 只有价格异常，原因完全未知；
- Thesis成立，但当前资产不是纯粹表达。

## 7. Asset Expression

同一Opportunity比较股票、ETF、指数和行业：

- Thesis暴露强度；
- 暴露纯度；
- 估值与预期；
- 公司质量；
- 流动性；
- 单一公司风险；
- 行业集中度；
- ETF跟踪误差、费率、溢价和成分；
- 证据完整度；
- 与Opportunity收敛路径的匹配程度。

系统不默认个股优于ETF。若公司级Evidence不足或个股风险过大，ETF可能是更好的研究表达。

## 8. Research Candidate

候选报告至少包含：

```text
Asset
Related Thesis / Version
Mispricing Opportunity
Why Now
Market-Implied View
Research View
Why the Market Is Selling
Temporary / Structural / Uncertain
Supporting Evidence
Counter Evidence
Evidence Gaps
Best Expression Reason
First Rejection Question
Kill Criteria
Confidence Band
Research Priority
Action Level
Next Review
```

研究优先级：

- `Immediate`：24小时内研究；
- `High`：7天内完成核心验证；
- `Normal`：下一Review周期；
- `Low`：保留观察，不占用主动研究时间。

## 9. Action Assessment

AI综合决定：Watch / Research / Prepare / Action Candidate。

AI必须分别评价：

- Thesis Integrity；
- Mispricing Strength；
- Fundamental Integrity；
- Evidence Completeness；
- Market Context Fit；
- Asset Expression Quality；
- Strongest Counter Case；
- Unknowns；
- Timing和Next Review。

等级可以升降，不要求线性晋级。每次变化创建不可变Assessment。

## 10. Alert Eligibility

通知层不重新研究，只检查保存后的Assessment：

```text
Action Level = Action Candidate
AND Confidence >= 85
AND Thesis status有效
AND Evidence完整
AND Market = Panic或等效系统压力
AND Mispricing显著
```

全部通过才创建Opportunity Alert。AI可以把候选判为Action Candidate，但未通过固定门槛时只进入日报。

## 11. AI结构化输出

```text
market_implied_view
research_view
variant_wedge
why_now
price_move_causes[]
permanence_assessment
supporting_evidence_ids[]
counter_evidence_ids[]
alternative_explanations[]
unknowns[]
thesis_integrity
mispricing_strength
fundamental_integrity
best_asset_expression
first_rejection_question
research_priority
action_level
confidence_internal
confidence_reasons[]
kill_criteria_status[]
next_review_at
```

所有Evidence引用必须存在于输入EvidenceSet；出现未知ID或事实时本次输出无效。

## 12. 去重与生命周期

同一Thesis、同一偏离原因和相同资产范围形成一个Opportunity，不因每日运行重复创建。

生命周期：

```text
Hypothesis → Open → Strengthening → Closed
                 ↘ Weakening → Invalidated
```

关闭原因：价格与价值偏离收敛、Thesis失效、原因转为Structural、Evidence被推翻、资产表达不再有效或研究窗口结束。

## 13. 失败模式

- 数据不足：输出Evidence Gap，不生成高优先级Candidate；
- 原因未知：保留Watch，不强行归因；
- Thesis与资产暴露不清：进入Exposure Not Proven；
- 市场正常但个股暴跌：优先排查公司级事件，不自动认定系统性错杀；
- 市场恐慌但基本面破坏：Reject Mispricing；
- AI输出不一致：保存失败运行，不覆盖Assessment；
- 多个解释接近：保留替代解释并提高Review频率。

## 14. 验收场景

1. ETF赎回和量化止损放大下跌，基本面无变化：可形成Temporary假设。
2. 财报同比高增长但环比和指引弱：归入Expectations/Fundamentals，而不是简单错杀。
3. 行业Thesis成立但公司治理恶化：个股被Reject，ETF仍可成为表达。
4. PE低但周期利润在顶部：不得形成价值错杀。
5. 市场恐慌且原因不明：最多Watch，明确Unknown。
6. AI判定Action Candidate但Confidence为82：不发送Alert。
7. Confidence 90但Market不是Panic：进入日报，不发送Alert。
8. 后续证据表明原因Structural：Opportunity Weakening或Invalidated，Action Level降级。

