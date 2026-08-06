# Phase 5 — Fear Memory System（Historical Crisis Library）

Date: 2026-08-06
Status: DONE（版本化策展案例库，PIT 安全查询，已接入冻结链路）

## 目的

帮助人在恐慌时理解环境：不是预测工具，而是**历史事实**库 —— 真实 A 股危机
案例（日期、已知指数变动、有据可查的成因），供研究者在极端行情中对照当下
环境。绝不输出交易指令。

## 契约

- `agent/src/investment_research/models/fear_memory.py`（新）：
  - `CrisisEpisode`（typed）：crisis_id / label / start-end / severity
    （SYSTEMIC/LOCALIZED/SHOCK）/ narrative（事实叙述，禁预测词）/ key_stats /
    sources。
  - `FearMemoryConfig.curated()`：冻结、版本化的策展案例库（v1，5 起）：
    2015 杠杆股灾、2016 熔断、2018 去杠杆熊市、2020 疫情冲击、2024 微盘股
    流动性危机。
  - `query_fear_memory(as_of)`：纯函数、确定性；PIT 规则 = `start_date <=
    as_of` 才可见；未来案例进入 `hidden_episodes_count`（透明计数），绝不
    泄漏进过去。
- 接线：`ResearchContext.fear_memory`；`attach_contract_metadata` 写报告顶层
  键 `fear_memory`（`_fear_memory_block` 确定性兜底）。
- 契约冻结变更记录：phase0_8_contract_freeze.md。

## 测试

- `agent/tests/test_fear_memory.py`（新，14 项）：PIT 可见性边界（2017 只见
  两起、2024-01-28 隐藏微盘股案例、as_of 当日可见）、案例库事实性（无预测
  词、id 唯一、日期合法）、契约形状（确定性、版本、无交易指令、summary）。
- 冻结键断言更新：enforcement + routes（+`fear_memory`）。
- 相关套件回归：157 passed。

## 边界

- 案例库是**策展知识**，非行情数据：新增/修改案例必须走版本化
  FearMemoryConfig，且只允许历史事实（禁止预测性表述）。
- 历史统计（key_stats）为公开记录近似值（如 5178 高点），字段名带 approx
  标注，禁止伪装为精确行情。
