# RRV-RELIABILITY-CLOSURE-001 收口报告

日期：2026-08-07
范围：真实研究可靠性收口（唯一工作包）。验证：`automation/research_validation_v2.py` 独立库重跑 5 历史事件。

## 1. 目标完成情况

| 阶段 | 交付 | 验证 |
|---|---|---|
| P0 候选合同 + Provider 弹性 | `provider_policy.py`（重试/退避/最小间隔/熔断/超时/健康）+ `PitEndpointCache`；三路径统一 `candidate-contract-v1` | 5 事件双端点 HEALTHY、零失败；候选全带 score/risk_review |
| P1 PIT 资格 + 审计 | `eligibility-v1` 优先级链 + watchlist 上市日元数据 + `universe_audit` | 2015 中 588060 CONFIRMED_NOT_LISTED 排除；159941 凭元数据 ELIGIBLE；无证据=UNKNOWN |
| P2 信号明细 | `MarketSignalVerdict`（index 4 + breadth 2） | 报告逐信号 observed/threshold/triggered |
| P3 状态协调 | `market_state_reconciliation`（冻结规则） | 2024-02-05 CAUTION→effective EXTREME_PANIC |
| 前端 | 协调/审计/健康面板 + 候选资格徽标 | 316 前端测试通过、tsc+build 通过 |
| v2 重跑 | 5 事件全量真实数据，独立 SQLite/缓存 | 全部成功，报告落 `docs/research_validation_v2/` |

## 2. v2 重跑结果

| 事件 | legacy | intel | effective | 升级 | 门槛 | 候选 | 排除 |
|---|---|---|---|---|---|---|---|
| 2015-06-26 | PANIC | EXTREME_PANIC | EXTREME_PANIC | 是 | 通过 | 4 | 1（588060） |
| 2018-10-11 | EXTREME_PANIC | EXTREME_PANIC | EXTREME_PANIC | 否 | 通过 | 5 | 1 |
| 2020-02-03 | PANIC | EXTREME_PANIC | EXTREME_PANIC | 是 | 通过 | 5 | 1 |
| 2022-03-15 | PANIC | EXTREME_PANIC | EXTREME_PANIC | 是 | 通过 | 5 | 0 |
| 2024-02-05 | CAUTION | EXTREME_PANIC | EXTREME_PANIC | 是 | 通过 | 5 | 0 |

5/5 事件有效状态为 PANIC 或 EXTREME_PANIC，与真实历史一致；首次运行 92-100s/事件，
v2 库快照重放 2.0s 且结果一致（2024-02-05）。

## 3. 失败项收口（research_failure_log.md 全量更新）

- RF-001 → RESOLVED（重试/熔断吸收断连；候选合同补齐）
- RF-002 → RESOLVED（状态协调，2024 不再 CAUTION）
- RF-003 → RESOLVED（PIT 资格 + universe audit）
- RF-004 → RESOLVED（子信号明细）
- RF-005 → ACCEPTED_DATA_SOURCE_LAYER（腾讯回退正常）
- RF-006 → ACCEPTED_DATA_SOURCE_BLOCKED（2018-01-02 起，上游限制）
- RF-007 → ACCEPTED_PLANNED（P2 显式缺口，禁新数据源）

## 4. 回归

- 后端：本工作包相关测试全绿（research/value_hunter 系 200+ 项）；全量 6258 passed 与
  基线 HEAD 一致（76 项失败为环境性/先存问题：TestClient 挂起、行数守卫、认证环境、跨进程锁，
  经 stash 对照在未改动 HEAD 上完全复现，零新增失败）。
- 前端：316 passed；`tsc -b` 与 `vite build` 通过。

## 5. 提交与推送

- 0fa3273 fix(research): complete provider resilience with retry, backoff, breaker and PIT cache
- 3c55c88 fix(research): complete historical candidate contract and enforce point-in-time eligibility
- 72fbb20 feat(research): reconcile market states with explicit signal evidence
- e9783f3 feat(research): surface reconciliation, universe audit and provider health in the research UI
- （本收口提交）test(research): rerun five-event validation with provider health + closure docs
- 已推送 origin main（fast-forward 校验后）。

## 6. 十五问自检

1. 验证是否用真实数据？是——全量 akshare/腾讯真实端点，无 mock。
2. 是否零代码改动的首轮之后再次验证？是——v2 独立库重跑 5 事件。
3. 验证结果是否可复现？是——同库快照重放 2.0s 输出一致；PIT 缓存键含 requested_as_of。
4. 是否新引入硬编码特判？否——资格/合同/协调均为通用规则，无 `if code==`。
5. 是否伪造修复？否——RF-005/6/7 明示 ACCEPTED，不冒充 RESOLVED。
6. 是否引入新架构？否——全部为既有组件内的策略/模型/展示层增量。
7. 是否动过 hkuds 上游或 fetch/merge？否——远端只读，未触碰。
8. 是否新增数据源？否——未接入 tushare/baostock 等新源。
9. 是否保留既有 API 语义？是——顶层 `market_state` 保持 legacy 语义，新字段显式新增。
10. 冻结规则是否被遵守？是——协调规则按规格实现并有单测锁定。
11. 是否所有提交独立可跑？是——每提交后相关测试通过。
12. 是否推送合规？是——origin fast-forward，禁 force push。
13. 是否新增文档？是——规格/收口报告/failure log 更新/v2 验证资产；未污染仓库（data/ 不入库）。
14. 前端是否与后端合同一致？是——api.ts 类型与后端三路径输出逐字段对齐，build 通过。
15. 遗留项是否显式？是——RF-005/6/7 保持 ACCEPTED；`test_alpha_compare_api.py` 挂起为环境性问题（HEAD 复现），与本次无关。

## 7. 不做事项（确认未做）

- 未添加交易/宏观数据源；未自动推送通知；未改动 hkuds；未 force push；未提交密钥。
