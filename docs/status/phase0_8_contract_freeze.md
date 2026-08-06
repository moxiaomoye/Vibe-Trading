# Phase 0.8 Contract Freeze — Research Pipeline 契约冻结

Date: 2026-08-06
Status: FROZEN（架构冻结完成，未提交 git）
目的：冻结 Phase 0.5–0.7 建立的 Research Contract，禁止任何新研究功能
回归裸 dict；之后才允许进入 Phase 1（Market Intelligence Layer）。

---

## 1. 冻结的数据流（唯一路径）

```
Provider (typed dataclass)
      ↓
ScanResult (typed)
      ↓
ResearchContext (Pydantic)   ← 唯一研究上下文
      ↓
ArtifactMetadata + DataQualityReport   ← 输出契约
      ↓
Report (dict)                ← API 输出载荷（唯一允许的 dict）
```

## 2. Report 顶层契约（冻结键集）

`trade_date` / `market_state` / `panic_sensitivity` / `market_summary` /
`candidates` / `data_gaps` / `artifact` / `data_quality` / `research_run_id`

变更记录（2026-08-06, Phase 1）：新增 `market_intelligence`（Market
Intelligence Contract，typed block，见 phase1_market_intelligence.md）。
该键由冻结链路（ResearchContext → attach）写入，禁止裸 dict 直拼。

## 3. ArtifactMetadata 冻结字段

| 字段 | 含义 | 确定性来源 |
|---|---|---|
| `artifact_version` | artifact 格式版本（=1） | 常量 |
| `research_id` | `{YYYYMMDD}-{rules_version}` | as_of_date + rules_version |
| `research_run_id` | 研究运行实例 ID | 扫描 run_id 的确定性推导 |
| `created_at` | 生成时间（信息性，不参与任何哈希） | 实时 |
| `as_of_date` / `requested_date` | 时点日期 | 输入 |
| `rules_version` | 规则身份（panic-core-v1） | 常量 |
| `rules_fingerprint` | 阈值指纹（7 个规范键） | profile |
| `provider_version` | 数据源版本标签 | provider 名 |
| `data_snapshot_id` | 输入快照指纹（mode+market+candidates） | 输入 |
| `content_hash` | 报告内容哈希（排除 artifact 自身） | 报告 |

**可复现保证**：同输入快照 + 同规则 + 同路径 ⇒ 相同 data_snapshot_id、
research_run_id、content_hash；created_at 不参与任何哈希。

## 4. research_run_id 语义

- `make_research_run_id(payload) = uuid5("research:{scan_run_id}")`
- live / stored / rebuild 三路径对同一扫描收敛为同一 run id
- 贯穿 ResearchContext → ArtifactMetadata → Report 顶层键 → 存储快照
- 查询入口：用 run_id 直接定位"某次研究"，无需重跑

## 5. 允许的 dict 边界（Adapter Allowlist）

新代码一律不得新增裸 dict 研究载荷。仅以下 sanctioned 接缝可以接受 dict：

1. `ResearchContext.from_scan_payload`（legacy/adapter 入口）
2. `attach_contract_metadata(scan_payload, report, ...)`（输出装配）
3. `_context_from_snapshot`（存储恢复接缝：新快照 model_validate / 旧快照适配）
4. Report 构建/渲染层（`_candidate_payload`、`_forward_*`、`render_*`、
   `prepare_*`）—— 输入为 typed 对象，输出为 API 载荷

研究流程内部（scan → 评分 → 载荷）一律走 typed dataclass / Pydantic。

## 6. Enforcement（由测试强制，无法绕过）

`agent/tests/test_research_contract_enforcement.py`：

1. 分层：value_hunter 任何模块不得 import investment_research（AST 扫描）
2. 入口约束：`build_research_run` / `build_historical_evaluation` /
   `_scan_historical_provider` / `_rebuild_historical_evaluation` 必须引用
   sanctioned context 接缝（ResearchContext / _context_from_snapshot）
3. 字段冻结：ArtifactMetadata 必须包含 5 个身份字段
4. 报告形状：attach 后必须含 artifact / data_quality / research_run_id
5. 往返确定性：context model_dump(mode="json") → model_validate 后
   research_run_id 不变

**新增研究功能时**：要么接收/构造 ResearchContext，要么显式改本测试白名单
（等于声明新的 sanctioned 接缝，需人工评审）。

## 7. 强类型覆盖审计结果（Phase 0.8 任务1）

扫描 `investment_research/` 全部 dict 注解（51 处）：

- `application/research_mvp.py`：全部属于 4 类 sanctioned 边界
  （输出载荷 / 适配器输入 / 行辅助 / MarketFetcher 类型）
- `models/*`：仅 adapter 输入（Mapping）与模型字段，符合契约
- `intelligence/`（daily_thesis / daily_research）：独立旧领域，自带
  `to_dict/from_dict` 双向类型化，不在 research_mvp 冻结范围（记录在案，
  不迁移、不修改）
- `integrations/issuer_disclosures.py`：SEC 披露抓取，无研究上下文

结论：research_mvp 关键路径无违规裸 dict 传递。

## 8. 依赖方向（已冻结）

`value_hunter` ⊥ `investment_research`（零引用，enforcement 测试守卫）。
`investment_research` → `value_hunter`（只读复用，单向）。

## 9. 未纳入本冻结（Phase 2+ 记录）

- ScanResult.research_context 仍为 dict 字段（value_hunter 层；未来改
  research_run_id + repository 查询，本阶段不动）
- frontend TS 类型未同步 artifact/data_quality/research_run_id
- intelligence/ 旧领域未迁移

停止，等待人工审核；不进入 Phase 1。
