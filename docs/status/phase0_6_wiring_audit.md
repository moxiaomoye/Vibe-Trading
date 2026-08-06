# Phase 0.6 Wiring Audit — ResearchContext 接线审计

Date: 2026-08-05
Commit audited: `cbf6c9f` (Phase 0.5 落地后)
Status: AUDIT COMPLETE — 只读，未修改任何文件
目标：确认 Phase 0.5 新增 Contract 是否真正接入现有研究流程。

---

## 1. ResearchContext 是否进入 research_mvp 主流程

**结论：半接入 —— 三个输出点都构造并验证了 ResearchContext，但它只在
输出边界作为"验证 + 富化"层，不参与流程内部的数据流。**

接入点（`agent/src/investment_research/application/research_mvp.py`）：

| 路径 | 行号 | 行为 |
|---|---|---|
| `build_research_run`（实时研究） | :279 | `attach_contract_metadata(scan.to_dict(), report, ...)` |
| `build_historical_evaluation`（存储快照路径） | :458 | 同上，`provider=snapshot["mode"]` |
| `_rebuild_historical_evaluation`（重建路径） | :576 | 同上，`provider=provider.name` |

证据：

- `attach_contract_metadata` 内部确实构造 `ResearchContext.from_scan_payload(...)`
  （`models/research_context.py:245`），Pydantic 校验真实发生。
- 但构造后立即 `model_dump()` 成 dict 附到响应上（`:256`），流程内部（扫描、
  评分、候选载荷、T+ 计算、存储、飞书）全部继续使用 dict。
- ResearchContext **没有任何消费者**：`agent/src` 中除 `models/` 自身与
  `research_mvp.py` 外无引用（grep 证实）。

## 2. 关键路径是否仍为 dict 直接传递

**结论：是 —— dict 仍是唯一关键路径数据形式。**

证据链（全部 dict）：

- `scan.to_dict()` → `service.store.save_scan(scan.to_dict())`
  （`research_mvp.py:239,500`；`value_hunter/service.py:76-77`；`store.py` 存
  `payload_json`）
- `_candidate_payload` / `_watchlist_scan_payload` 返回 dict
  （`research_mvp.py:65,185`）
- `_forward_metrics` / `_candidate_forward_payload` 返回 dict（`:303,:352`）
- 路由返回 dict（`api/research_mvp_routes.py`）
- 存储快照为 JSON dict，历史评估直接读取后再次传递（`:395-448`）

**含义**：Phase 0.5 的 ResearchContext 是"响应出口处的类型化校验层"，
不是"内部数据流的类型"。dict 无 schema 校验地穿过 store → 读取 → 富化全链路。

## 3. Artifact metadata 是否从入口传递到输出

**结论：否 —— Artifact 在输出时临时合成，未随快照持久化，未跨环节传递。**

证据：

- `service.store.save_scan(scan.to_dict())` 先于 `attach_contract_metadata`
  执行（live `:239` vs `:279`；重建 `:500` vs `:576`），而 `ScanResult.to_dict()`
  只有 `research_context = {schema_version, panic_sensitivity}` 两个键
  （`value_hunter/models.py:145,164`）—— **artifact 不在存储载荷中**。
- 存储路径的历史评估对同一快照每次生成**新的** `created_at`、新的
  `content_hash`（`models/research_context.py:159,253`）—— artifact 不可从
  存储恢复，同一研究结果每次评估身份不同。
- `render_feishu_preview` / `prepare_feishu_delivery` 不使用 artifact
  （`research_mvp.py:580+`）。
- 唯一真实的"入口→输出"是 HTTP 响应本身（路由返回含 artifact 的 report），
  但这是单跳，不是传递。

## 4. DataQuality 是附加字段还是统一契约

**结论：附加字段 —— 尚未成为统一契约。**

证据：

- `report["data_quality"] = {issues, counts, all_available}` 在输出时一次性
  附加（`models/research_context.py:257-260`）。
- **无任何读取方**：`agent/src` 中不存在对 `report["data_quality"]` /
  `["artifact"]` 的消费代码；前端 TS 类型（`frontend/src/lib/api.ts`）未含
  这两个键（前端未改动，仅记录）。
- 流程内部仍是旧表达：`None` + `data_gaps` 字符串列表；`classify_data_quality`
  的 four-state 仅在生成 issues 时使用，未影响任何判断路径。
- `data_gaps`（字符串）仍是事实上的内部质量契约，`DataQualityReport` 是其
  出口投影。

## 5. 是否存在第二套 Context 模型

**结论：存在双表示，未统一。**

| 表示 | 位置 | 类型 | 生命周期 |
|---|---|---|---|
| `ScanResult.research_context` | `value_hunter/models.py:145` | `dict[str, Any]`（未类型化） | 持久化侧：随快照入库、随历史评估读出 |
| `ResearchContext` | `investment_research/models/research_context.py:84` | Pydantic | 输出侧：每次响应临时构造 |

两者字段不一致：dict 只有 `schema_version + panic_sensitivity`；Pydantic 含
market_snapshot/valuation_snapshot/data_quality/artifact_metadata。不是第二个
"模型实现"，但确实是两套承载同一语义的数据结构，且持久化侧仍是未类型化 dict
（契约 §2 要求强类型，尚未达成）。

## 6. 审计结论汇总

| 检查项 | 结论 |
|---|---|
| 1. ResearchContext 进入主流程 | 半接入（输出边界构造+校验，非内部数据流类型） |
| 2. 关键路径 dict 传递 | 存在且为主流（store/candidates/T+/路由全 dict） |
| 3. Artifact 入口到输出 | 未接入（输出时合成，快照不持久化，同快照每次评估身份不同） |
| 4. DataQuality 统一契约 | 仍是附加字段（无消费者，内部仍 None+data_gaps） |
| 5. 第二套 Context | 存在双表示（持久化 dict vs 输出 Pydantic），未统一 |

## 7. 风险提示（仅记录，不实施）

1. **Artifact 身份不稳定**：存储路径每次评估生成新 created_at/content_hash，
   research_id 稳定但 artifact 整体不可复现 —— 违背契约 §7"同一输入同一 hash"。
2. **无 schema 校验的持久化**：快照以原始 dict 入库，损坏/漂移无法在写入或
   读取时被发现。
3. **DataQuality 与 data_gaps 双轨**：两个质量表达并存，未来可能不一致。
4. 上述均为 Phase 1 接线工作项；本审计不产生代码变更。

## 8. 未检查内容

- 运行期行为（未执行任何代码/网络调用，纯静态审计）。
- frontend 消费端（本阶段禁止修改，仅确认其类型未含新键）。

---

# Phase 0.7/1.0 迁移记录（Small Migration 已实施，2026-08-06）

审计后接线工作完成，未提交 git（等待整体完成后统一提交）。测试：
`research_contract_models + research_mvp_routes + value_hunter
(service/scoring/provider_cache/routes) + panic_value_config` = **79 passed**。

## 对审计问题的处置

| 审计问题 | 处置 | 证据 |
|---|---|---|
| 1. ResearchContext 半接入 | 三个流程入口均构造 context；`attach_contract_metadata` 新增 `context=` 直接接收（不再在输出端重建） | `research_mvp.py` build_research_run / build_historical_evaluation / _rebuild_historical_evaluation |
| 2. 双 Context | 统一：新快照 `research_context` 携带完整序列化 `context`（`model_dump(mode="json")`），存储→恢复全链路保留；旧 dict 快照经 `_context_from_snapshot` 适配器（`from_scan_payload`）兼容 | `research_mvp.py:_context_from_snapshot` |
| 3. Artifact 不可复现 | 新增 `data_snapshot_id`（输入快照指纹：mode+market+candidates，排除 universe/research_context/errors）；存储路径恢复持久化 artifact（created_at 延续首次生成）；`content_hash` 仅覆盖报告内容，与 created_at 无关 | `artifact.py:compute_data_snapshot_id`；测试 test_historical_evaluation_reproduces_artifact_from_stored_snapshot |
| 4. DataQuality 双轨 | 数据质量表达统一由 context 承载（存储路径从持久化 context 恢复，不再重算）；`data_gaps` 保留为报告层摘要 | context 持久化断言 |
| 5. schema_version | 更名主字段为 `artifact_version`，保留 `schema_version` 兼容属性 | `artifact.py:ArtifactMetadata` |

## 变更文件

- `agent/src/investment_research/models/artifact.py`（+compute_data_snapshot_id，
  +artifact_version/data_snapshot_id 字段，schema_version 变属性）
- `agent/src/investment_research/models/research_context.py`（from_scan_payload
  生成 data_snapshot_id；attach 支持 context 参数）
- `agent/src/investment_research/application/research_mvp.py`（入口构造并持久化
  context；_context_from_snapshot 适配器；三处 attach 传 context）
- `agent/src/investment_research/models/__init__.py`（exports）
- `agent/tests/test_research_contract_models.py`（+5 断言/测试）
- `agent/tests/test_research_mvp_routes.py`（+1 可复现性测试）

## 剩余（Phase 1 范围外，仅记录）

- frontend TS 类型未同步 artifact/data_quality。
- 旧 dict 快照（research_context 为空）走适配器路径，仍输出新 contract。
- 未修改：Provider、评分、阈值、估值规则、通知触发、前端。

停止，等待人工审核；不进入 Phase 1。
