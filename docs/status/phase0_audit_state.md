# Phase 0 Audit State — Architecture Audit & Contract Freeze

Date: 2026-08-05
Commit audited: `6d6e134` (main, ahead of origin/main by 2)
Status: AUDIT COMPLETE — awaiting human review (no development started)

## 1. Audit time and scope

只读离线审计（git/tree/cat/grep），未执行 python/pytest/npm/curl，无外部
HTTP 请求，未修改生产代码。

## 2. Inspected areas

| 区域 | 文件 | 结论 |
|---|---|---|
| Provider Layer | `agent/src/value_hunter/providers.py` | `ValueHunterProvider` ABC、`DemoProvider`、`AkshareProvider`、`HistoricalAkshareProvider`（as_of 时点重建）、`build_provider`、`normalize_ashare_symbol` |
| 领域模型 | `agent/src/value_hunter/models.py` | `IndexObservation/MarketObservation/CandidateObservation/ScoreBreakdown/CandidateResult/MarketResult/ScanResult`，`ScanResult.research_context` 为未类型化 dict |
| 评分 | `agent/src/value_hunter/scoring.py` | `score_market`（trend/drawdown/breadth/panic 分量）、`score_candidate`（A/B/C/Reject + missing_fields 门禁） |
| 编排 | `agent/src/value_hunter/service.py`、`scheduler.py` | 单例、锁、通知去重指纹、每日调度 |
| 存储 | `agent/src/value_hunter/store.py` | SQLite `scans`/`notifications`，payload_json 快照 |
| 配置 | `agent/src/value_hunter/config.py`、`config/panic_value_config.yaml`、`config/watchlist.yaml` | 阈值/权重可配，`resolve_panic_sensitivity` 0-100 → 1/2/3 档确认 |
| Market data | `agent/src/market_data.py`、`backtest/loaders/registry.py` | `fetch_market_data` + `FALLBACK_CHAINS`（a_share: tencent→mootdx→eastmoney→baostock→akshare→tushare→local） |
| Research Pipeline | `agent/src/investment_research/application/research_mvp.py` | `build_research_run`、`_market_state`（四态）、`_panic_profile`（3 项检查） |
| Historical Evaluation | 同上 + `_forward_metrics/_classify_outcome/_rebuild_historical_evaluation` | 快照优先，缺失时按 as_of 重建并持久化；T+5/20/60 + 超额 + 最大回撤 |
| Notification Outbox | `agent/src/investment_research/operations/models.py`、`repositories/sqlite_operations.py`（schema v6）、`operations/delivery.py` | `OutboxMessage` 幂等键、JobRun、FeishuWebhookTransport/OutboxDispatcher |
| 历史验证域 | `agent/src/investment_research/validation/models.py` | `ReplayManifest`（五版本字段）、`classify_process_outcome`（合理失败/运气赚/典型错误） |
| API | `agent/src/api/research_mvp_routes.py`、`value_hunter_routes.py` | POST research-run / historical-evaluation / feishu-preview，require_auth，to_thread |
| Frontend 入口 | `frontend/src/router.tsx`、`pages/InvestmentResearch.tsx`、`lib/api.ts` | `/investment-research` 路由、日期选择器（默认 2025-04-07）、历史面板、飞书 preview UI、TS 类型（api.ts:449-592） |
| 文档 | `docs/PROJECT_VISION.md`、`docs/exec-plans/research-mvp-v1.md`、`docs/architecture/*_V2.md` | 证据驱动研究定位；MVP 计划 M0-M6 完成状态；无危机案例库 |

## 3. Architecture risks found

1. **research_context 未类型化**：`ScanResult.research_context` 是 dict，
   快照载荷无 Pydantic 校验（契约 §2 要求强类型）。
2. **规则版本未冻结**：评分规则在代码中（scoring.py）+ yaml 覆盖，无
   rules_version 指纹；改规则会静默改变历史结论（契约 §7 要求版本化）。
3. **Crisis Library 不存在**：历史评估是单日期快照，无案例时间线；
   `limit_down_count`/`turnover_zscore` 历史恒为 None，高敏感档 PANIC
   判定在历史回溯下自动降级为 CAUTION（行为约定，需人工确认）。
4. **载荷结构无共享 schema**：前端 TS 类型与后端 dict 手工同步，漂移风险。
5. **快照重复**：research run 每次生成新 run_id 保存；历史评估按 as_of
   扫描 history(200) 取最新匹配，同日多快照时首条生效。
6. **outbox body 为纯文本**：只存渲染文本，无结构化载荷与版本（契约 §7）。

## 4. Deliverables produced

- `docs/architecture/research_core_contract_v1.md`（228 行，7 章：Product
  Boundary / ResearchContext / PIT Rules / Signal Bundle / Crisis Library /
  Research Decision / Artifact Versioning）
- `docs/research/crisis_library_seed.yaml`（schema v1 + 3 案例：
  2020-03 全球流动性冲击、2022-04 宏观估值折价、2024-02 微盘股量化踩踏）
- 本文件

docs/ 在 .gitignore 内；三个文件均未提交，待人工审核后决定是否入库。

## 5. Not inspected

- 大型日志与运行时产物（logs/、.pytest_cache、.venv、node_modules）
- 数据库完整内容（仅读 schema 定义）
- `archives/`、`work/`、`tools/`、`scripts/`、`wiki/`（非 Research Core 相关）
- 交易/连接器代码（`trading/connectors/*`，超出产品边界）
- `任务.txt`（空文件）

## 6. Next steps (waiting for human review)

1. 审核并批准 research_core_contract_v1.md（尤其 §3 PIT 例外声明、
   §6 Invalidation 的 measure 枚举、§7 rules_version 引入方式）。
2. 确认 crisis_library_seed.yaml 的 id/date/crisis_tag 取值（三个种子
   日期为窗口起始日，非事件单日）。
3. 决定三项风险的处理优先级：research_context 强类型化（§2）、
   rules_version 指纹（§7）、Crisis Library 落地（§5）。
4. 批准后进入 Phase 1 数据接入；本阶段不开始任何开发。

---

## Phase 0.5 completion record（契约落地）

Date: 2026-08-05
Scope: Phase 0 审计发现的 4 项基础风险工程化落地；未进入 Phase 1，未接入
新数据源，未修改 Provider/评分/候选/交易逻辑，未新增平行系统。

### Delivered

| 风险 | 落地 |
|---|---|
| 1. ResearchContext 未类型化 | 新增 `agent/src/investment_research/models/research_context.py`：`ResearchContext`（Pydantic，纯数据对象：as_of_date / requested_date / market_snapshot / valuation_snapshot / data_quality / artifact_metadata），`from_scan_payload()` 复用既有 scan 载荷，无 API/DB/网络方法 |
| 2. Artifact Versioning 不完整 | `models/artifact.py`：`ArtifactMetadata`（research_id / created_at(UTC aware) / as_of_date / requested_date / rules_version / provider_version / schema_version / rules_fingerprint / content_hash），canonical JSON + SHA-256 内容哈希，research_id 形如 `20250407-panic-core-v1` |
| 3. 历史研究缺 rules_version | `models/rules_version.py`：`RULES_VERSION="panic-core-v1"` + `rules_fingerprint(profile)`（对解析后的恐慌阈值做规范投影指纹，live/存储/重建路径同阈值同指纹；不改任何阈值） |
| 4. Data Quality 无统一表达 | `models/data_quality.py`：`missing/available/estimated/unavailable` 四态；`classify_data_quality` 保证 0.0 视为 available（缺失不会被误认为 0）；`DataQualityReport` 聚合 |

### Wiring（research_mvp 输出）

- `build_research_run` / `build_historical_evaluation`（存储路径）/
  `_rebuild_historical_evaluation`（重建路径）均在报告上附加
  `artifact` 与 `data_quality` 块；存储快照与前端既有契约不变。

### Verification

- 新增 `agent/tests/test_research_contract_models.py`（22 项契约测试）。
- 更新 `test_research_mvp_routes.py` 统一契约键断言（+artifact/+data_quality）。
- 相关套件 73 passed（research_mvp routes、value_hunter service/scoring/
  provider_cache/routes、panic config）。
- `git diff --check` 通过。

### Boundary compliance

- 修改仅限 `agent/src/investment_research/`（新增 models/ 子包）与相关测试。
- 未触碰 frontend/、docker/、providers.py、scoring.py、config 阈值。

### Remaining risks（进入 Phase 1 前仍开放）

- Crisis Library（§5）仍未落地 —— 属于 Phase 1 范围，本阶段明确排除。
- 前端 TS 类型与后端新增 artifact/data_quality 块的同步属于 Phase 1。
- 快照内 `research_context` 仍未强类型化（需 value_hunter 边界变更，已记录）。
