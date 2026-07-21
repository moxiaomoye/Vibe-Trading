# AI Investment Researcher 领域模型 V2

版本：V2.0  
状态：概念设计，不对应当前数据库迁移

## 1. 设计目标

V1以股票观察值和总分为中心。V2改为以长期Thesis和Mispricing Opportunity为中心，使系统能够保存“为什么值得研究、为什么市场卖出、判断如何变化、什么时候失效”，而不仅是某天某只股票得了多少分。

领域主链：

```text
MarketState
  → Thesis / ThesisVersion
    → MispricingOpportunity
      → AssetExpression
        → ResearchCandidate
          → ActionAssessment
            → Review / OutcomeEvaluation
```

Evidence贯穿全部对象，不属于任何单一模块。

## 2. 聚合边界

### 2.1 Market Intelligence Aggregate

#### MarketState

表示某个市场在明确时点的研究状态。

关键字段：

- `market_state_id`
- `market`
- `as_of`
- `regime`: Bull / Recovery / Correction / Panic / Crash / Bubble / Uncertain
- `stress_level`
- `liquidity_state`
- `breadth_state`
- `valuation_state`
- `dominant_factors`
- `supporting_evidence_ids`
- `counter_evidence_ids`
- `data_completeness`
- `model_version`
- `created_at`

MarketState是有证据的分类，不是单一指数分数。内部指标可以连续化，但对外必须解释状态变化原因。

#### MarketStateTransition

记录状态变化，而不是覆盖昨日结果：

- `from_state`
- `to_state`
- `changed_at`
- `change_reasons`
- `evidence_ids`
- `materiality`

### 2.2 Thesis Aggregate

#### Thesis

长期投资逻辑的稳定身份。

关键字段：

- `thesis_id`
- `name`
- `parent_thesis_id`
- `scope`: macro / theme / industry / value_chain / company
- `market_scope`
- `status`: Draft / Active / Watch / Impaired / Broken / Retired
- `current_version_id`
- `owner`
- `created_at`
- `retired_at`

示例树：

```text
AI产业
├── AI CapEx
│   ├── GPU与加速卡
│   ├── 光模块与网络
│   ├── PCB
│   └── 服务器与散热
└── AI应用变现
```

#### ThesisVersion

Thesis每次实质变化生成新版本，历史只追加、不覆盖。

关键字段：

- `thesis_version_id`
- `thesis_id`
- `version_number`
- `effective_from`
- `supersedes_version_id`
- `core_claim`
- `causal_chain`
- `assumptions`
- `supporting_evidence_ids`
- `counter_evidence_ids`
- `catalyst_ids`
- `kill_criteria`
- `confidence_internal`
- `confidence_band`
- `change_summary`
- `change_reason`
- `next_review_at`
- `model_prompt_version`

#### ThesisDependency

表达Thesis树之外的影响关系：

- `upstream_thesis_id`
- `downstream_thesis_id`
- `relationship`: supports / depends_on / conflicts_with / substitutes / amplifies
- `strength`
- `evidence_ids`
- `effective_period`

微软CapEx变化可以沿依赖图影响GPU、光模块、PCB和服务器Thesis，但每条影响必须具有独立证据。

#### Catalyst

- `catalyst_id`
- `thesis_id`
- `event_type`
- `expected_window`
- `confirmed_or_inferred`
- `expected_impact`
- `evidence_ids`
- `status`

#### KillCriterion

- `criterion_id`
- `thesis_id`
- `description`
- `observable_metric`
- `threshold_or_condition`
- `evaluation_window`
- `source_requirement`
- `approval_status`
- `triggered_at`

Kill Criterion必须可观测、可验证，不能只写“行业逻辑恶化”。

### 2.3 Evidence Aggregate

#### Evidence

统一保存事实证据与来源，不为支持和反对分别建立两套结构。

关键字段：

- `evidence_id`
- `evidence_type`: filing / earnings / market_data / announcement / policy / industry / estimate / flow / news / derived
- `source_name`
- `source_locator`
- `event_time`
- `published_at`
- `ingested_at`
- `as_of_available_at`
- `raw_fact`
- `interpretation`
- `magnitude`
- `quality`
- `freshness_state`
- `conflict_state`
- `related_entity_type`
- `related_entity_id`
- `supersedes_evidence_id`
- `content_hash`

事实和解释必须分别保存。Evidence不能直接被删除；错误证据通过纠正记录和supersedes关系处理。

#### EvidenceAssociation

Evidence direction is contextual and must not be stored as an intrinsic property of the source fact:

- `association_id`
- `evidence_id`
- `subject_type`: thesis / market / asset / opportunity / validation
- `subject_id`
- `direction`: supporting / counter / neutral
- `assessed_at`
- `assessor`
- `rationale`
- `supersedes_association_id`

The same immutable Evidence may support one Thesis and counter another. Reclassification appends a superseding
association; it never rewrites the prior judgment.

#### EvidenceConflict

- `conflict_id`
- `evidence_ids`
- `conflict_type`
- `resolution_status`
- `resolution_reason`
- `resolved_by`
- `resolved_at`

#### EvidenceSet

一次AI判断实际使用的Evidence快照：

- `evidence_set_id`
- `member_ids`
- `cutoff_time`
- `completeness`
- `missing_categories`
- `hash`

该对象保证历史重放时输入边界明确。

#### ThesisEvidenceReadiness

| 字段 | 说明 |
|---|---|
| thesis_id / as_of | Thesis与信息截点 |
| verdict | 分类门槛，不是分数 |
| supporting/counter/neutral_association_ids | 当前关联版本头 |
| blocking_gaps / quality_warnings | 阻塞缺口与来源质量问题 |
| first_rejection_question | 首要否定问题 |
| approval_review_id | 当前集合仍有效的人工批准，可空 |

#### EvidenceSetReview

追加式人工评审记录。`Approve`要求完整当前关联集合、支持证据、反证、最强反证、审阅者、理由、
信息截点和批准引用；质量警告需要明确例外理由。新Evidence Association产生后旧批准不再代表当前集合。
该实体不创建Thesis Version。Manifest V3与`ThesisInitializationAudit.evidence_set_review_id`形成可追溯
绑定；初始化事务必须在持久化账本中找到同一Thesis的真实批准记录。

### 2.4 Asset Aggregate

#### Asset

统一资产主数据：

- `asset_id`
- `asset_type`: Stock / ETF / Index / Sector
- `symbol`
- `name`
- `market`
- `currency`
- `listing_status`
- `industry_membership`
- `benchmark_membership`
- `valid_from`
- `valid_to`

#### AssetExpression

表达某项Thesis或Opportunity可以通过哪些资产承载：

- `asset_expression_id`
- `thesis_id`
- `opportunity_id`
- `asset_id`
- `expression_role`: direct / upstream / downstream / diversified / hedge / benchmark
- `exposure_evidence_ids`
- `exposure_strength`
- `purity`
- `liquidity`
- `idiosyncratic_risk`
- `selection_reason`
- `rejection_reason`

“最佳表达”不等于涨幅最大，而是在Thesis暴露、估值、风险、流动性和公司质量之间取得最合理的研究表达。

### 2.5 Mispricing Aggregate

#### MispricingOpportunity

核心领域对象，代表一个可证伪的错误定价假设。

关键字段：

- `opportunity_id`
- `title`
- `thesis_id`
- `market_state_id`
- `opportunity_type`: panic / liquidity / multiple_compression / temporary_event / expectations_reset / forced_flow / other
- `market_implied_view`
- `research_view`
- `variant_wedge`
- `why_now`
- `expected_convergence_path`
- `time_horizon`
- `supporting_evidence_ids`
- `counter_evidence_ids`
- `price_move_attribution_id`
- `confidence_internal`
- `confidence_band`
- `status`: Hypothesis / Open / Strengthening / Weakening / Invalidated / Closed
- `created_at`
- `next_review_at`

#### PriceMoveAttribution

回答“为什么别人卖”。允许多个并存原因，不强迫给出单一故事。

- `attribution_id`
- `asset_id`
- `as_of`
- `causes[]`
- `unexplained_share`
- `alternative_explanations`
- `evidence_set_id`
- `confidence_internal`

每个 `cause` 包含：

- `category`: fundamentals / expectations / valuation / passive_flow / active_flow / liquidity / macro_rates / policy / event / technical / unknown
- `description`
- `estimated_importance`
- `permanence`: Temporary / Structural / Uncertain
- `evidence_ids`
- `counter_evidence_ids`

如果证据不足，正确输出是Uncertain或Unknown，而不是让AI强行归因。

### 2.6 Research Candidate Aggregate

#### ResearchCandidate

代表某个机会与资产表达被分配了研究优先级。

关键字段：

- `candidate_id`
- `opportunity_id`
- `asset_expression_id`
- `created_at`
- `status`: Active / Deferred / Rejected / Archived
- `why_research`
- `first_rejection_question`
- `research_priority`: Immediate / High / Normal / Low
- `evidence_set_id`
- `evidence_freshness`
- `open_questions`
- `next_review_at`
- `latest_action_assessment_id`

ResearchCandidate不以总分作为核心身份。内部指标可以帮助排序，但用户首先看到的是研究论证。

#### ActionAssessment

AI对候选行动阶段的版本化判断：

- `assessment_id`
- `candidate_id`
- `action_level`: Watch / Research / Prepare / ActionCandidate
- `confidence_internal`
- `confidence_band`
- `reasoning_summary`
- `supporting_evidence_ids`
- `counter_evidence_ids`
- `missing_evidence`
- `thesis_integrity`
- `mispricing_strength`
- `fundamental_integrity`
- `market_context_fit`
- `review_trigger`
- `next_review_at`
- `model_id`
- `prompt_version`
- `evidence_set_id`
- `created_at`

AI拥有Action Level最终研究判断权。判断不可静默覆盖，任何变化都形成新Assessment。

#### AlertEligibility

通知层的确定性检查结果：

- `assessment_id`
- `is_action_candidate`
- `confidence_gate_passed`
- `thesis_gate_passed`
- `evidence_gate_passed`
- `market_gate_passed`
- `mispricing_gate_passed`
- `eligible`
- `evaluated_at`

它不改变AI的Action Level，只决定是否发送Opportunity Alert。

### 2.7 Review Aggregate

#### ResearchReview

- `review_id`
- `entity_type`
- `entity_id`
- `scheduled_at`
- `trigger_type`: periodic / evidence_change / price_move / catalyst / kill_criterion / manual
- `questions`
- `status`
- `completed_at`
- `resulting_version_id`

#### DecisionLog

保存系统向用户呈现了什么，以及用户是否采取后续研究动作；不要求记录交易。

- `decision_log_id`
- `candidate_id`
- `presented_action_level`
- `presented_at`
- `user_disposition`: ignored / reviewed / deferred / independently_acted / unknown
- `notes`

#### OutcomeEvaluation

分别评价过程和结果：

- `evaluation_id`
- `candidate_id`
- `evaluation_horizon`
- `process_quality`
- `evidence_quality`
- `thesis_accuracy`
- `attribution_accuracy`
- `confidence_calibration`
- `price_outcome`
- `benchmark_relative_outcome`
- `max_drawdown`
- `unexpected_event`
- `information_was_available`
- `false_positive_classification`
- `lessons`

False Positive不能仅由价格下跌定义。若当时研究过程合理但后来发生不可知事件，应标记为随机或不可预知损失，而不是伪造事后错误。

### 2.8 Intelligence Delivery Aggregate

#### DailyResearchReport

- `report_id`
- `trade_date`
- `market_state_id`
- `thesis_changes`
- `new_opportunity_ids`
- `candidate_changes`
- `action_candidate_ids`
- `today_conclusion`
- `data_cutoff`
- `generated_at`
- `report_version`

#### OpportunityAlert

- `alert_id`
- `candidate_id`
- `assessment_id`
- `eligibility_snapshot`
- `created_at`
- `next_review_at`

#### DeliveryAttempt

每个渠道独立记录：

- `delivery_id`
- `content_id`
- `channel`
- `status`
- `attempt_count`
- `last_error`
- `next_retry_at`
- `delivered_at`

一个渠道成功不得阻止另一个失败渠道重试。

## 3. 状态生命周期

### Thesis

```text
Draft → Active → Watch → Impaired → Broken → Retired
              ↘ Active
```

Broken不因价格反弹自动恢复；必须通过新Evidence和新Version重新评估。

### Mispricing Opportunity

```text
Hypothesis → Open → Strengthening → Closed
                 ↘ Weakening → Invalidated
```

### Research Candidate

```text
Active → Deferred → Active
   ├── Rejected
   └── Archived
```

### Action Level

Action Level不是单向晋级，可以随证据变化升降：

```text
Watch ↔ Research ↔ Prepare ↔ Action Candidate
```

每次变化必须记录触发证据和原因。

## 4. 领域不变量

1. ResearchCandidate必须关联一个MispricingOpportunity。
2. MispricingOpportunity必须关联至少一个有效ThesisVersion。
3. ActionAssessment必须绑定不可变EvidenceSet。
4. ThesisVersion、ActionAssessment和Evidence历史只追加。
5. Evidence必须具有as-of可得时间。
6. AI解释不能覆盖原始事实。
7. Opportunity Alert必须引用通过门槛的ActionAssessment。
8. Daily Report允许没有候选，但不允许没有Today Conclusion。
9. Confidence内部值不能被描述成上涨概率。
10. Asset价格变化不能单独确认或否定Thesis。

## 5. 研究输出契约

每个候选的标准Research Report必须包含：

```text
Research Candidate
Asset
Related Thesis / Thesis Version
Mispricing Opportunity
Why Now
Why Worth Researching
Why the Market Is Selling
Temporary / Structural / Uncertain
Market-Implied View
Research View
Supporting Evidence
Counter Evidence
Evidence Gaps
Thesis Integrity
Kill Criteria
Confidence Band
Research Priority
Action Level
Next Review Time
```

不得用单一“92分”替代这些内容。

## 6. V1到V2概念映射

| V1概念 | V2处理 |
|---|---|
| `MarketObservation` | 保留数据角色，归入MarketState证据输入 |
| `MarketResult.score` | 降级为内部压力指标，不再作为产品结论 |
| `CandidateObservation` | 拆为Asset事实、财务证据和市场证据 |
| `ScoreBreakdown` | 作为内部筛选特征，不再成为核心领域对象 |
| `CandidateResult` | 被ResearchCandidate + ActionAssessment替代 |
| `ScanResult` | 被DiscoveryRun + DailyResearchReport替代 |
| `notification_required` | 被AlertEligibility替代 |
| `risk_flags` | 转化为Evidence、Counter Evidence和Kill Criteria输入 |

该映射只用于后续迁移设计，本阶段不修改现有模型或数据库。
