# AI Investment Researcher — Project Vision

## 项目定位

本项目基于 HKUDS/Vibe-Trading 的 Agent/回测/数据平台构建，但产品方向聚焦为：**证据驱动的投资研究系统**。目标是打造一个在股灾/市场恐慌时，能够自动筛选并推荐买入标的的交易框架。

> **核心原则：** 不优化交易频率或推荐数量，而是追求**时点正确、有证据支撑的研究候选**。

---

## 相对上游（HKUDS）的新增功能

### 1. AI Investment Researcher V2（核心自研）

一套完整的独立领域模块，位于 `agent/src/investment_research/`（约 70+ 文件）。

**工作流程：**

```
市场状态 → Thesis 论点 → Discovery 发现 → 归因/错价分析 → 研究候选 → 动作级别 → 日报/告警
```

**核心模块：**

| 模块 | 作用 |
|---|---|
| **Thesis 引擎** | 版本化的论点树；需人工 Evidence Set Review 才能初始化 |
| **Evidence Inbox / Associations** | 自动采集先入收件箱；证据是中性的，方向挂在上下文上 |
| **Evidence readiness** | 分类门禁（缺支撑/缺反证/未批准），不是打分推荐 |
| **Discovery / Mispricing** | 保守 triage，区分证据缺口 vs 归因所需 |
| **Market State** | 时点市场状态评估 |
| **Intelligence / Daily pipeline** | 幂等日更、SQLite WAL、通知 Outbox |
| **Issuer disclosures** | SEC EDGAR 时点数据摄入 → Inbox（人工审核后才进论点） |
| **Historical validation** | 过程质量 vs 收益，区分「运气赚」和「合理失败」 |

**对外接口：**
- API: `investment_research_routes.py`
- 前端: `/investment-research`
- CLI 脚本: 初始化、证据审查、日更、交付等 6 个脚本
- Windows 定时任务: `install_investment_research_task.ps1`

### 2. Value Hunter（A 股科技恐慌监控）

独立包 `agent/src/value_hunter/`，与投研模块桥接。

**逻辑：** 收盘后读指数 + 科技观察池 → 市场恐慌评分 + 公司研究评分 → 双阈值达标才推送飞书/邮件；**不下单、不猜底**。

**界面：** `/value-hunter` 页面

### 3. 架构与交付文档

- `docs/architecture/`：17 篇 V2 体系文档（领域模型、论文引擎、错价机会引擎、项目宪法等）
- `archives/`：多版本归档 ZIP

---

## 目的

我的核心目的是：**在股灾/市场恐慌时，系统能自动推荐可以买入的股票。**

这不是高频交易系统，也不是自动下单机器人。而是：

1. **市场恐慌时** — Value Hunter 监控 A 股恐慌指数，达到阈值触发研究流程
2. **证据驱动** — Investment Researcher 自动采集证据、评估论点、生成研究候选
3. **人工门禁** — 所有推荐需经过 Evidence Set Review 审核，确保不是噪音
4. **时点正确** — 强调 Point-in-Time 数据，防前视偏差，区分「运气赚」和「合理失败」

---

## 未来计划

### 近期（1-2 个月）

- **完善大盘危机触发逻辑** — 对接更多恐慌指标（VIX 等）
- **丰富观察池** — 从 A 股扩展到港股/美股
- **自动化日报** — 每天盘后推送可买入候选汇总

### 中期（3-6 个月）

- **回测框架集成** — 对每个推荐候选跑 Shadow Account 回测
- **多空信号** — 不只找买入机会，也识别卖出信号
- **组合建议** — 根据候选的错价程度和置信度生成投资组合权重建议

### 长期（6-12 个月）

- **构建完整的「危机-推荐」交易框架**：
  1. 市场阶段识别（正常/预警/恐慌/恢复）
  2. 恐慌时自动启动深度扫描
  3. 生成带证据链的买入候选清单
  4. 人工审核后输出买入建议（含仓位、止损、目标价）
  5. 后续持续跟踪和退出信号

---

## 与上游的同步策略

本项目 fork 自 HKUDS/Vibe-Trading，采用定期合并上游更新的策略：

- 当前同步至 HKUDS main 最新提交（2026-07-21）
- 保留了自研的 investment_research 和 value_hunter 模块
- 后续将继续合并上游的安全加固、回测优化、数据源扩展等改进
