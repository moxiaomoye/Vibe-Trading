# CURRENT STATE — Vibe-Trading 长期维护 Handoff

更新：2026-08-24（Research MVP、研究可靠性收敛、经典聊天隔离与恐慌提醒
运行验收完成；PR #23 按用户要求暂不合并）
模式：LOCAL DEVELOPMENT MODE（禁止 push/PR/merge/remote 同步；本地 commit 仅
为 checkpoint，`--no-gpg-sign`）
**2026-08-06 更新**：用户明确指令允许推送 GitHub（`git push origin main`），
已执行；其余纪律不变（无 DCO、--no-gpg-sign、hkuds 上游不动）。

## 2026-08-24 当前验收状态

- 当前分支：`agent/fix-conversation-intent-routing`，HEAD `3a756d8`；PR #23
  保持未合并，当前工作未 commit/push。
- 经典聊天默认不再自动注入 Investment Research/Value Hunter 研究记忆；研究能力
  保留在显式研究页面/意图中。恐慌提醒只依赖真实 PANIC/EXTREME_PANIC 市场状态，
  无候选时也可提醒市场风险，但不会产生交易指令。
- Docker 服务健康运行于 `127.0.0.1:8899`；飞书长连接为
  configured/enabled/loaded/running，未执行真实通知发送。
- 真实研究运行：`2026-08-24`，9 个个人观察池标的均取得真实当日价格，统一研究
  API 返回 NORMAL 和 Top 5；市场宽度上游失败被明确记录为 Data Gap。
- 历史验证：`2025-04-07` 与 `2026-07-24` 均返回 PANIC、5 个当时候选，以及
  T+5/T+20/T+60 收益、最大回撤、基准超额和结果分类。
- 浏览器验收：真实点击“生成盘后研究”后，交易日、候选和 Data Gap 正常显示，
  无 API 密钥错误。Feishu Preview 保持 `send=false`。
- 本轮测试：Value Hunter/统一配置 98 项通过；聊天隔离、提醒、Provider 与研究路由
  43 项通过；前端 316 项通过；环境变量 CI 门禁通过。完整后端回归在 Windows
  上通过 1,174 项、跳过 14 项后，停在既有 POSIX `0600` 文件模式断言（Windows
  实际报告 `0666`），与本轮改动无关。全仓 `git diff --check` 仅被用户已有的
  `auto-start.log` 尾随空格阻塞，本轮修改文件自身无格式错误。

---

## 当前阶段

- **路线图 Phase 1–6 全部完成**（tasks/roadmap.yaml 队列清空）。
- 当前状态：**Real Research Validation**（不新增功能）：真实数据跑 5 个历史
  恐慌事件、人工审查报告、Research Failure Log 先记录不修。
- 首轮验证已完成（2026-08-06）：5 事件全部跑通，报告存
  `docs/research_validation/*.json`；审查见 `research_validation_review.md`；
  问题见 `research_failure_log.md`（RF-001..007）。核心发现：市场层识别
  5/5 命中；候选研究层 0/25 可评分（eastmoney/sina 批量被断连）；2024 结构性
  恐慌顶层状态失灵；2015 报告含未上市 ETF（指标未污染）。

## 已完成（本session，按提交顺序）

| Phase | 提交 | 内容 |
|---|---|---|
| 1.5 | `e1b13c1` | 历史涨跌停标的池估计 + `estimated_fields` 全链路（ESTIMATED 不占可用权重） |
| — | `f44f6a8` | 交接文档更新 |
| 2 | `f96fe9e` | Regime Detection：Macro 五维契约 + UNKNOWN 显式缺口，报告键 `market_regime` |
| 3 | `b0db04f` | ETF Research Layer：指数代理风险收益/恐慌统计（PIT 截至估值 as-of，v4） |
| 4 | `c3c88d3` | Stock Risk Analyzer：`risk_review` 契约（五维价值陷阱审查，无评级指令） |
| 5 | `cd6ed81` | Fear Memory：策展危机案例库 + PIT 查询，报告键 `fear_memory` |
| 6 | `c31302e` | Research Quality Eval：事后 Case Review 契约（非预测胜率） |
| maintenance | `0d592f8` | factors registry 测试 symlink 无权限时干净跳过（WinError 1314） |
| RRV 首轮 | 待提交 | `automation/research_validation.py` + 5 事件真实报告 + Failure Log（RF-001..007）+ 人工审查 |

## 测试状态

- 全量套件：**1038 passed, 5 skipped**（修复后 factors registry 的 9 项
  环境依赖测试干净跳过；其余全绿）。
- 研究/价值猎人相关套件：167 passed。

## 未完成 / 下一步（维护期）

1. **maintenance-weekly**：跑全量测试、检查 provider 端点健康（AKShare 依赖
   外部接口，可能漂移）、依赖版本变化、新警告（如 pct_change fill_method
   FutureWarning 已在全量输出中出现，可评估是否收敛）。
2. 可选增强（均需先设计再动契约）：
   - 历史路径补 ETF 底层指数估值（当前历史回溯为 Data Gap，见 providers 1139 行附近）。
   - Macro 数据源接入（当前 regime 恒为 UNKNOWN+缺口）。
   - PB 分位（中证指数接口当前仅 PE/股息率）。
3. 每次 session 结束必须更新本文件。

## 风险 / 纪律（不变）

- 阈值全部走版本化 Config（market-intel-v1 / market-regime-v1 /
  risk-review-v1 / research-quality-v1 / fear-memory-v1），禁止裸改常量。
- 估计必须显式标注（ESTIMATED）；缺口禁止静默填充。
- PIT 纪律：历史研究输入只可见 date <= as_of 的数据；fear_memory 案例
  start_date <= as_of 才可见；research_quality 是事后复盘，不得进入 PIT
  研究报告。
- 本地 commit 为 checkpoint，格式 feat:/fix:/refactor:/docs:，无 DCO。

## 关键文件

- `agent/src/investment_research/models/`：market_intelligence.py、
  market_regime.py、risk_review.py、fear_memory.py、research_quality.py、
  research_context.py（接线中枢）、artifact.py
- `agent/src/value_hunter/providers.py`（P1.5/P3 provider 增强）
- `agent/tests/`：对应 6 个新测试文件 + 契约/路由/缓存套件
- `automation/long_runner.py` + `tasks/roadmap.yaml`（队列，全部 done）
- `docs/status/`：phase0_8 / phase1 / phase2 / phase5 / phase6 文档 + 本文件
