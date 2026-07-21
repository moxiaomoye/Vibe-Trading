# Thesis Engine V2 设计

版本：V2.2  
状态：领域与应用设计，不修改代码或数据库

## 1. 使命

Thesis Engine是AI Investment Researcher的长期记忆和因果推理核心。它不预测价格，也不直接产生Research Candidate；它负责持续回答：

> 一个长期投资逻辑为什么成立、哪些证据正在支持或削弱它、它影响哪些下游机会、什么事实会使它失效，以及下一次应在何时重新研究。

Thesis不是标签、主题词或AI每日摘要，而是可版本化、可证伪、可重放的研究对象。

## 2. 责任边界

### Thesis Engine负责

- Thesis Tree与跨树依赖；
- ThesisVersion；
- 核心主张、因果链和假设；
- Evidence与Counter Evidence关联；
- Catalyst；
- Kill Criteria；
- Confidence变化；
- Review调度；
- 受上游变化影响的下游传播建议；
- 历史时点重建。

### Thesis Engine不负责

- 判断股票是否便宜；
- 计算具体资产估值；
- 生成买卖建议；
- 自动下单；
- 根据价格涨跌确认Thesis；
- 直接决定Opportunity Alert；
- 保存未经验证的新闻摘要作为事实。

## 3. Thesis类型

| Scope | 作用 | 示例 |
|---|---|---|
| `Macro` | 宏观和制度背景 | 利率周期、国产替代政策环境 |
| `Theme` | 跨行业长期逻辑 | AI产业、机器人 |
| `Industry` | 行业供需和盈利结构 | 半导体设备、光模块 |
| `ValueChain` | 产业链具体环节 | AI CapEx、GPU、PCB、服务器 |
| `Company` | 公司经营逻辑 | 某公司的份额、产品或成本优势 |

证券价格和估值判断不直接写入长期业务Thesis，而由Mispricing和Asset Expression域引用Thesis。

## 4. Thesis Tree与依赖图

### 4.1 Tree

树表达研究分解关系：

```text
AI产业
├── AI基础设施
│   ├── Hyperscaler CapEx
│   ├── GPU与加速卡
│   ├── 高速互联/光模块
│   ├── PCB
│   ├── 服务器
│   └── 电力与散热
└── AI应用与变现
```

每个节点有自己的核心主张、证据、反方和Kill Criteria。父节点成立不自动证明所有子节点成立。

### 4.2 Dependency Graph

树之外允许：

- `depends_on`：下游依赖上游成立；
- `supports`：一个Thesis为另一个提供支持；
- `conflicts_with`：两个逻辑存在冲突；
- `substitutes`：一个路径可能替代另一个；
- `amplifies`：上游变化会放大下游影响。

依赖关系需要Evidence和有效期，不能由AI永久写死。

### 4.3 传播规则

上游变化只产生 `ImpactProposal`，不自动修改下游Thesis：

```text
上游ThesisVersion变化
→ 查找相关Dependency
→ 生成下游ImpactProposal
→ 收集下游独立Evidence
→ AI复核
→ 生成或不生成下游新Version
```

这防止“微软CapEx下降”被机械解释成所有AI资产逻辑同时失效。

## 5. ThesisVersion

### 5.1 不可变原则

- 每次实质研究变化创建新Version；
- 旧Version永久保留；
- 小型格式修正不改变研究Version，但进入审计日志；
- 每个Version绑定EvidenceSet和信息截止时间；
- 历史回测只能加载当时已生效的Version。

### 5.2 Version内容

```text
Thesis Identity
Version Number
Effective From
Core Claim
Causal Chain
Key Assumptions
Supporting Evidence
Counter Evidence
Catalysts
Kill Criteria
Confidence Internal
Confidence Band
Company/Industry Thesis Status
Change Summary
Change Reason
Open Questions
Next Review
Evidence Cutoff
Model / Prompt Version
```

### 5.3 触发新Version的事件

- 新证据实质改变核心主张；
- 关键假设增强或减弱；
- Catalyst发生或失效；
- Kill Criterion被触发或解除；
- 上游Thesis产生Material Impact；
- 定期Review改变Confidence或状态；
- 发现过去Evidence错误或存在重大冲突。

价格变化本身不会触发Version，除非它产生了需要研究的市场预期变化或新Evidence。

## 6. Evidence Ledger

Evidence facts and research judgments are separate. Source facts are immutable and neutral. `EvidenceAssociation`
records why a fact supports, counters, or is neutral to one specific Thesis, with assessor, rationale, assessment
time, and append-only supersession. Thesis initialization and review validate association direction rather than
treating direction as a permanent property of the source document.

### 6.1 证据分层

优先级从高到低：

1. 公司公告、法定披露、监管文件；
2. 公司财报、投资者材料、管理层原始表达；
3. 官方政策、行业统计和交易所数据；
4. 可验证的供应链、竞争对手和市场数据；
5. 可靠机构研究与Consensus；
6. 主流新闻；
7. 社交媒体、传言和无法独立验证的观点。

低层级证据可以触发Review，但不能单独导致高Confidence结论。

### 6.2 正反对称

AI每次更新必须执行两轮：

1. 构建最强支持论证；
2. 独立构建最强反对论证。

最终综合不得简单用支持条数减反对条数。证据质量、独立性、时效性、因果距离和对核心假设的影响更重要。

### 6.3 Evidence Freshness

每种证据定义刷新规则：

| Evidence类型 | 默认新鲜度 |
|---|---|
| 日行情/市场宽度 | 当前交易日 |
| 资金流和ETF成分 | 1—5个交易日，按来源说明 |
| 财务报表 | 至下一报告或重大预告 |
| 管理层指引 | 至新指引或撤回 |
| 政策文件 | 至修订、到期或执行变化 |
| 行业供需 | 按月/季度数据频率 |
| 新闻 | 需要后续官方或独立来源确认 |

Freshness过期不会删除Evidence，而是降低当前判断可用性并触发Review。

### 6.4 冲突处理

当Evidence冲突：

- 保留全部原始Evidence；
- 标记冲突类型：数值、时间、定义、来源或解释；
- 优先核对原始披露和口径；
- 未解决时结论显示Uncertain；
- 不允许AI静默选择更符合既有Thesis的一方。

## 7. Catalyst

Catalyst不是“可能上涨的事件”，而是能够验证或否定Thesis的研究事件。

每个Catalyst包含：

- 事件；
- 预计时间窗口；
- confirmed或inferred；
- 将验证的Thesis假设；
- 预期可观察指标；
- 可能结果及对Thesis的不同影响；
- 事件后Review SLA。

示例：云厂商财报不是天然利好，而是验证AI CapEx规模、结构和持续性的Catalyst。

## 8. Kill Criteria

Kill Criteria必须满足：

- 可观察；
- 有来源；
- 有明确时间窗；
- 指向核心假设；
- 触发后有预定义Review动作；
- 标明是Draft还是Owner确认。

示例结构：

```text
假设：Hyperscaler AI CapEx将维持增长
指标：主要云厂商合计AI相关CapEx指引
失效条件：连续两个报告期实质下调，且不是项目时点延迟
数据源：公司财报与指引
触发动作：AI CapEx Thesis进入Impaired并立即复核所有下游节点
```

AI可提出Kill Criteria草案，但未经Owner确认前标记为 `Draft Monitoring Rule`。

## 9. Confidence

### 9.1 含义

Confidence衡量：

- Evidence质量与完整性；
- 因果链稳健度；
- 替代解释强度；
- 关键假设的不确定性；
- Thesis历史稳定性；
- 反方证据覆盖程度。

它不表示股价上涨概率。

### 9.2 表达

- 内部：0—100连续值，用于版本比较和历史校准；
- 对外：Low / Medium / High；
- 每次变化必须给出主要贡献因素；
- 不能因价格表现自动调整。

建议初始Band：

- Low：`< 60`
- Medium：`60—84`
- High：`>= 85`

该阈值在历史校准前属于设计默认值，不代表统计概率。

### 9.3 变化约束

单条非决定性新闻不应导致大幅变化。若内部Confidence单次变化超过10点，必须：

- 指出Material Evidence；
- 说明影响的核心假设；
- 生成新Version；
- 触发下游ImpactProposal。

## 10. Review Engine

### Review类型

- `Periodic`：按固定周期；
- `EvidenceChange`：出现Material Evidence；
- `Catalyst`：事件发生后；
- `KillCriterion`：触发失效条件；
- `DependencyImpact`：上游变化；
- `MarketDislocation`：关联资产出现异常价格变化；
- `Manual`：用户主动要求。

### Review优先级

1. Kill Criterion；
2. Material反方证据；
3. 重大Catalyst；
4. 上游传播；
5. 到期Review；
6. 价格异常但原因未知。

### Review结果

- No Change；
- Confidence Updated；
- New ThesisVersion；
- Status Changed；
- Downstream Impact Proposed；
- Thesis Broken/Retired；
- Evidence Insufficient。

## 11. AI更新契约

AI输入：

```text
Current ThesisVersion
New EvidenceSet
Outstanding Counter Evidence
Open Questions
Catalysts
Kill Criteria
Upstream Impact Proposals
Information Cutoff
```

AI结构化输出：

```text
material_change: boolean
proposed_status
core_claim_change
assumption_changes[]
supporting_evidence_ids[]
counter_evidence_ids[]
conflicts[]
kill_criteria_assessment[]
confidence_internal
confidence_change_reasons[]
downstream_impact_proposals[]
open_questions[]
next_review_at
strongest_opposing_view
unknowns[]
```

输出验证失败时：

- 不创建新Version；
- 保存失败运行；
- 将Thesis标记为Review Pending；
- 日报披露更新失败或Evidence不足。

## 12. 研究工作流

### 新建Thesis

```text
提出研究问题
→ 定义Core Claim和因果链
→ 建立最小EvidenceSet
→ 建立Counter Evidence
→ 定义Kill Criteria草案
→ 确定父节点和依赖
→ AI Red-Team
→ 生成Version 1 Draft
→ Owner确认后Active
```

### 每日维护

```text
新Evidence摄取
→ 关联可能受影响Thesis
→ Materiality分类
→ Review Queue
→ AI更新
→ 新Version或No Change
→ 传播ImpactProposal
→ Daily Thesis Update
```

### 失效

```text
Kill Criterion触发
→ Thesis进入Review Pending
→ 核验Evidence与口径
→ AI生成最强保留理由与最强失效理由
→ 状态Impaired/Broken/Active
→ 新Version
→ 通知所有关联Opportunity重新评估
```

## 13. 历史重放

重建历史日期T的Thesis时：

- 仅加载`as_of_available_at <= T`的Evidence；
- 加载T时生效的ThesisVersion和Dependency；
- 使用当时的Prompt/Model版本，或明确标记使用现代模型重跑；
- 隐藏T之后的价格、公告和结果；
- 先锁定更新，再揭晓未来；
- 比较当时版本、当前版本和真实结果，但不改写历史。

## 14. Research Quality评价

Thesis Engine评价指标：

- Evidence可追溯率；
- Counter Evidence覆盖率；
- Kill Criteria可验证率；
- Review按时率；
- ThesisVersion变化可解释率；
- Confidence校准；
- 冲突Evidence显式率；
- 下游传播准确率；
- 事后发现的公开证据遗漏率；
- Thesis不必要波动率。

“Thesis不必要波动率”用于防止AI每天因普通新闻频繁修改长期逻辑。

## 14.1 Evidence Set Readiness与人工评审

Version 1初始化前，系统只输出分类门槛，不输出就绪度分数：无已审证据、缺支持证据、缺反证、
证据质量待复核、可进入人工评审、已获准准备初始化。每个状态都必须给出首要否定问题。

Evidence Set Review采用追加式人工决策。批准必须覆盖时间截点上的完整当前关联集合，同时具备支持证据、
反证、最强反证标识、审阅者、理由、信息截点和批准引用；有质量警告时必须记录例外理由。任何后续关联
都会使旧批准过期。批准只允许准备初始化提案，不创建Thesis Version，也不代替核心主张、催化剂、
Kill Criteria、Confidence和下次复核时间的人工判断。

Manifest V3必须引用该实体的真实`review_id`。应用服务、初始化CLI和SQLite原子写入事务分别校验
批准状态、Thesis、完整关联集合、信息截点、批准时间、最强反证与批准引用。Version 1初始化审计永久
保存`evidence_set_review_id`，因此一个没有来源的文本批准号不能替代真实评审。

## 15. MVP边界

V2.2之后的首个Thesis MVP只覆盖：

- 一棵AI基础设施Thesis Tree；
- 5—8个节点；
- 公告/财报/管理层指引/行业数据四类Evidence；
- Version、Counter Evidence、Catalyst、Kill Criteria和Review；
- 手工确认的初始Thesis；
- AI每日只处理Material Evidence；
- 不生成Action Candidate；
- 不扩展港美股。

## 16. 验收场景

1. 微软CapEx指引下降，只生成下游ImpactProposal，不自动判定全部AI Thesis失效。
2. 同一证据同时支持GPU需求、反对某公司利润率时，可关联不同方向。
3. 新闻与公司公告冲突时显示Uncertain并等待核验。
4. 股价暴跌但没有新基本面证据时，不自动降低Thesis Confidence。
5. Kill Criterion触发后产生新Version、状态变化和下游复核。
6. 普通重复新闻不会生成新Version。
7. 历史日期只能看到当时已公开Evidence。
8. AI输出格式失败时历史Thesis不受污染。
9. Confidence大幅变化必须具有Material Evidence和原因。
10. 任一Version均能重建其EvidenceSet和生成上下文。

## 17. 后续接口

Thesis Engine向Mispricing Opportunity Engine提供：

- 当前有效ThesisVersion；
- Thesis状态和Confidence；
- 因果链与关键假设；
- 支持/反对EvidenceSet；
- Catalyst和Kill Criteria；
- 下游影响；
- Next Review。

Mispricing Engine不得绕过Thesis Engine自行生成长期逻辑。
