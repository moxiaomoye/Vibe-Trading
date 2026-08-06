# Phase 1 Market Intelligence Layer — 设计与实现记录

Date: 2026-08-06
Status: DONE（测试 97 passed，未推送远程）
范围：Market State Engine + Market Intelligence Contract，接入冻结链路
（ResearchContext → attach → Report → 存储），未触碰 value_hunter 冻结逻辑。

---

## 1. 前置审计结论（数据可用性矩阵）

| 输入 | Live | 历史 | 说明 |
|---|---|---|---|
| 指数行情 | ✓ | ✓ | indices（收盘/日涨跌/252回撤/MA250/120日低点） |
| 市场宽度 | ✓ 全市场 | △ watchlist 池 | 历史路径带警告，已声明 |
| 涨跌停 | ✓ 近似 | ✗ None | 历史路径 Data Gap（provider 声明） |
| 成交异常 | △ amount | ✗ | zscore 永远 None（无基线不可判定） |
| 波动率 | ✗ | ✗ | 快照 Schema 无此输入（预留） |
| ERP | ✗ | ✗ | 快照 Schema 无此输入（预留） |

结论：引擎必须维度感知可用性；缺失维度显式 UNAVAILABLE，不得静默归零。

## 2. 设计决策

1. **新能力，非重设计**：value_hunter 的 market_state 冻结不动；引擎是
   investment_research 层新增纯函数。
2. **单一链路接入**：`ResearchContext.market_intelligence: MarketIntelligence`
   （typed）→ `attach_contract_metadata` 写入 report 顶层
   `market_intelligence`（确定性，随 content_hash 覆盖）。
3. **状态五态**：NORMAL / STRESS / PANIC / EXTREME_PANIC / UNKNOWN
   （UNKNOWN = 可用证据权重为 0，数据缺口显式可见，绝不冒充 NORMAL）。
4. **压力得分**：各维度权重（指数35/宽度25/涨跌停20/成交10/波动率5/ERP5，
   合计100）仅对 AVAILABLE 维度归一化；缺失不稀释不掩蔽。
5. **阈值冻结**：`MarketIntelligenceConfig`（Pydantic 默认值，运行期不可变，
   版本 market-intel-v1）。
6. **PIT 安全**：只读 as_of 快照，无任何未来数据；纯函数可复现。
7. **无交易指令**：契约只输出状态 + 证据，无 action/signal/buy/sell 字段
   （测试强制）。

## 3. 状态映射（与 value_hunter 旧状态的关系）

- 旧 `market_state`（冻结）：NORMAL/CAUTION/PANIC/EXTREME_PANIC —— 扫描器
  状态，保留不动。
- 新 `market_intelligence.state`：NORMAL/STRESS/PANIC/EXTREME_PANIC/UNKNOWN
  —— 证据驱动状态。二者并存、各自可审计；CAUTION≈STRESS 概念对应但不合并
  实现（避免触碰冻结逻辑）。

## 4. 实现文件

- `agent/src/investment_research/models/market_intelligence.py`（新）：
  MarketState / MarketDimension / MarketDimensionVerdict / MarketIntelligenceConfig
  / MarketIntelligence / evaluate_market_intelligence（纯函数）
- `agent/src/investment_research/models/research_context.py`：from_scan_payload
  计算 market_intelligence；attach 写入 report；`_market_intelligence_block`
  UNKNOWN 兜底（确定性）
- `agent/src/investment_research/models/__init__.py`：exports
- `agent/tests/test_market_intelligence.py`（新，11 项）：分档/可用性/确定性/
  无交易指令/阈值冻结
- 契约/路由/强制测试同步（+13 项断言）

## 5. 已知边界（诚实记录）

- 历史路径仅 指数+宽度 两维度可用（覆盖 2/6）——引擎显式输出 coverage，
  不会冒充全维度判断。
- 波动率/ERP 为预留维度：Provider Schema 扩展后自动生效，引擎无需改。
- 阈值（-2.0% / -20% / 0.30 / 50 家 / 1.5σ）为市场恐慌经验值，非金融建议；
  调整必须走 MarketIntelligenceConfig 版本化（不得改常量裸值）。

停止，等待人工审核。
