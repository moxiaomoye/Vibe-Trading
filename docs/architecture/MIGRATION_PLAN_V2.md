# V1 → V2 代码迁移方案

版本：V2.4  
状态：待实施设计

## 1. 迁移策略

采用“并行新内核、共享数据适配、V1只读兼容、逐步切换UI”的Strangler模式，不在原`value_hunter`包中继续堆叠V2概念，也不一次性删除V1。

第一原则：先建立一条可验证的Thesis研究切片，再建设Mispricing和Alert。V1在迁移期继续运行，V2默认shadow mode，不影响现有日报和通知。

## 2. 目标代码边界

```text
agent/src/investment_research/
├── contracts/          # ID、枚举、DTO、错误
├── evidence/           # Evidence、EvidenceSet、来源与时点
├── thesis/             # Thesis Tree、Version、Review
├── market/             # MarketState
├── mispricing/         # Opportunity与PriceMoveAttribution
├── assets/             # Asset与Expression
├── candidates/         # Candidate与ActionAssessment
├── validation/         # 历史重放与质量指标
├── intelligence/       # Daily Report与Alert Eligibility
├── delivery/           # 飞书、邮箱Outbox Adapter
├── repositories/       # SQLite/PostgreSQL实现
└── application/        # Use Cases与调度
```

依赖方向：`contracts ← domain ← application ← adapters`。领域代码不导入FastAPI、SMTP、飞书、AKShare或具体LLM SDK。

## 3. 第一垂直切片

只实现：

```text
AI基础设施Thesis Tree
→ 5—8个Thesis节点
→ Evidence导入与版本
→ Thesis Review
→ Daily Thesis Update
```

明确不包含：Mispricing自动发现、Action Candidate、Alert、自动交易和全市场扫描。

## 4. 公共接口

### EvidenceProvider

```python
class EvidenceProvider(Protocol):
    def fetch(self, request: EvidenceRequest) -> EvidenceBatch: ...
```

返回必须包含provider、published_at、available_at、source_locator、content_hash和质量警告。

### ThesisRepository

```python
class ThesisRepository(Protocol):
    def get(self, thesis_id: ThesisId) -> Thesis: ...
    def current_version(self, thesis_id: ThesisId, as_of: datetime) -> ThesisVersion: ...
    def append_version(self, version: ThesisVersion) -> None: ...
    def due_reviews(self, as_of: datetime) -> list[ResearchReview]: ...
```

禁止update-in-place ThesisVersion。

### ThesisReviewer

```python
class ThesisReviewer(Protocol):
    def review(self, context: ThesisReviewContext) -> ThesisReviewDecision: ...
```

AI实现与确定性fixture实现共享协议，测试不依赖真实LLM。

### IntelligenceRepository

日报、Alert和DeliveryAttempt使用独立版本与渠道状态，不复用V1全局notification fingerprint。

## 5. 数据库演进

新建独立V2数据库，首期SQLite WAL：

- `assets`
- `evidence`
- `evidence_relations`
- `evidence_sets`
- `theses`
- `thesis_versions`
- `thesis_dependencies`
- `catalysts`
- `kill_criteria`
- `research_reviews`
- `research_runs`
- `daily_reports`
- `delivery_attempts`

后续Sprint再增加opportunities、attributions、asset_expressions、candidates、assessments和outcomes。

所有表具有schema_version、created_at和稳定ID。迁移脚本只前进，数据库升级前自动备份；V1的`scans`和`notifications`不迁移、不删除，只作为历史对照。

## 6. API兼容

V1 `/value-hunter/*`保持不变并标记legacy。V2使用：

```text
GET  /investment-research/status
GET  /investment-research/theses
GET  /investment-research/theses/{id}
GET  /investment-research/theses/{id}/versions
GET  /investment-research/reviews
POST /investment-research/reviews/run
GET  /investment-research/daily/{trade_date}
```

写入型Review API使用幂等键。V2响应使用版本化schema，不把内部AI推理文本暴露为公共契约。

## 7. 配置

- 全部V2配置进入现有`src.config`；
- 禁止业务模块直接`os.getenv`；
- V2默认`enabled=false`、`shadow_mode=true`；
- LLM、数据源和通知秘密只通过统一秘密引用；
- 启动时输出脱敏resolved config和schema version。

## 8. 实施顺序

1. 建立contracts、ID、枚举和错误类型。
2. 建立SQLite migration runner与repository contract tests。
3. 实现Evidence/EvidenceSet及PIT校验。
4. 实现Thesis、Version、Dependency和Review。
5. 加入fixture reviewer和AI structured reviewer adapter。
6. 建立AI基础设施种子Thesis Tree导入，不硬编码为运行逻辑。
7. 实现Daily Thesis Update shadow report。
8. 增加只读API和最小Web页面。
9. 连续运行至少20个交易日，与V1并行比较。
10. 通过质量门槛后进入Mispricing切片。

## 9. 测试

### 单元

- Version append-only；
- Evidence时间和去重；
- Dependency传播只生成Proposal；
- Confidence变化审计；
- Kill Criteria状态；
- Review优先级。

### 契约

- Provider返回字段和错误分类；
- Repository在SQLite与内存实现上一致；
- AI结构化输出拒绝未知Evidence ID。

### 集成

- 新Evidence→Review→New Version→Daily Update；
- AI失败不污染当前Version；
- 相同幂等键不重复创建Version；
- 历史日期只加载当时可得Evidence；
- 多渠道投递独立重试。

### 回归

- V1 API、扫描、页面和通知行为不变；
- 现有测试继续通过；
- 中央环境变量门禁通过；
- 新核心域覆盖率门槛85%。

## 10. 发布与回滚

- Phase 1：本地fixture；
- Phase 2：shadow mode，不通知；
- Phase 3：仅发送Daily Thesis Update给测试渠道；
- Phase 4：V2日报并行，V1仍保留；
- Phase 5：Owner确认后V2成为默认研究入口；
- Phase 6：V1只读归档。

回滚只需关闭V2开关；V1数据库和API保持原状。V2迁移不修改或删除V1表。

## 11. 质量门槛

进入Mispricing开发前必须达到：

- 100% ThesisVersion可追溯到EvidenceSet；
- 100% Evidence具有available_at；
- 历史重放无已知前视偏差；
- AI失败零历史污染；
- 20个交易日shadow运行稳定；
- Counter Evidence覆盖率达到设计基线；
- 中央配置、类型、测试和数据库迁移门禁通过。

## 12. 明确不做

- 不直接重命名现有包造成大范围破坏；
- 不把V1评分表原样迁入V2；
- 不接券商；
- 不在首个切片实现全部30个外部项目能力；
- 不先搭微服务、消息中间件或向量数据库；
- 不让AI直接写数据库；
- 不在V2核心表保存只有payload_json而不可查询的领域状态。

