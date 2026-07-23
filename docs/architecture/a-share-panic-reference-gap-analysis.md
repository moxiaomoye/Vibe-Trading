# A股盘后恐慌初筛 — 参考差距分析

## 调研来源

| 项目 | 路径 | License |
|------|------|---------|
| xang1234/stock-screener | `D:\AIStock\references\stock-screener` | Apache 2.0 |
| ZhuLinsen/daily_stock_analysis | `D:\AIStock\references\daily_stock_analysis` | MIT |
| akfamily/akshare | `D:\AIStock\references\akshare` | MIT（仅参考 API 接口） |

---

## 1. Vibe-Trading 当前已有能力

### agent/src/value_hunter/ 模块

| 组件 | 文件 | 状态 |
|------|------|------|
| `ValueHunterProvider` (ABC) | `providers.py:22` | 抽象基类，定义 `load_market()` / `load_candidates()` |
| `DemoProvider` | `providers.py:32` | 硬编码测试数据，无网络 |
| `AkshareProvider` | `providers.py:73` | 真实 AKShare 集成，含缓存 |
| `MarketObservation` | `models.py` | 市场快照结构（指数、宽度、涨跌比等） |
| `CandidateObservation` | `models.py` | 候选股结构（估值、财务、动量、风险标签） |
| `IndexObservation` | `models.py` | 指数观测结构 |
| `ScoreBreakdown` / `CandidateResult` / `ScanResult` | `models.py` | 评分与扫描结果结构 |
| `ValueHunterConfig` | `config.py` | 环境变量配置 |
| `load_watchlist_csv()` | `providers.py` | CSV 自选股加载 |
| 缓存机制 | `providers.py` | JSON 文件缓存，按日期 |

### agent/src/config/ 模块

| 组件 | 文件 | 状态 |
|------|------|------|
| `EnvConfig` | `env_schema.py` | 结构化环境配置 |
| `_parse_bool` | `accessor.py:89` | 布尔值解析器 |
| `paths.get_runtime_root()` | `paths.py` | 运行时根目录 |

### agent/api_server.py

可选路由加载器已支持 Value Hunter 和 Investment Research 的按需注册。

### agent/backtest/loaders/

已包含 `akshare_loader.py`，使用 `@register` 装饰器注册为回测数据加载器。

---

## 2. 可直接复用能力

| 能力 | 来源 | 复用方式 |
|------|------|---------|
| AKShare 集成 | `value_hunter/providers.py` | `AkshareProvider` 已实现 `stock_zh_a_spot_em()` 调用，可直接复用市场广度逻辑 |
| 市场快照结构 | `value_hunter/models.py` | `MarketObservation` 已有 `advancer_ratio`、`limit_down_count` 等字段 |
| 候选股结构 | `value_hunter/models.py` | `CandidateObservation` 已有估值/财务/动量字段 |
| CSV 自选股加载 | `value_hunter/providers.py` | `load_watchlist_csv()` 可直接使用 |
| 缓存机制 | `value_hunter/providers.py` | 按日期 JSON 缓存模式可复用 |
| 可选路由加载器 | `optional_routes.py` | 新 MVP 功能可用相同模式保持默认关闭 |

---

## 3. 需要增强能力

| 能力 | 当前状态 | 需要增强 |
|------|---------|---------|
| 市场广度详细指标 | 仅有 `advancer_ratio` + `limit_down_count` | 需增加上涨/下跌/平盘数量、大涨/大跌数量（如 ±4%）、涨停/跌停数量 |
| 涨跌停判断 | 无独立实现 | 需区分主板(10%)、创业板(20%)、科创板(20%)、ST(5%)，需交易日参数 |
| 恐慌等级 | 无独立实现 | 需从市场宽度数据计算恐慌等级，规则可配置 |
| 相对强弱计算 | `CandidateObservation.relative_to_sector_pct` 存在但仅相对行业 | 需增加相对大盘强度（相对沪深300/上证指数） |
| 观察池配置 | 仅 CSV 或硬编码 | 需支持 YAML 配置文件，含配置版本/内容哈希 |
| 交易日历 | 无 | 需确认交易日，防止非交易日数据被当作当日数据处理 |
| 数据新鲜度检查 | `MarketObservation.warnings` 存在但不完整 | 需独立 `data_gap` 语义 |
| 涨跌停池直接 API | 未使用 | 需调用 `stock_zt_pool_em()` / `stock_zt_pool_dtgc_em()` |
| 行业板块数据 | 未使用 | 需调用 `stock_board_industry_name_em()` 获取行业上涨/下跌家数 |
| pe_history_percentile | `CandidateObservation` 有字段但依赖 `stock_value_em()` | 需要更稳健的计算 |

---

## 4. 完全缺失能力

| 能力 | 参考来源 | 说明 |
|------|---------|------|
| 按阈值分类的市场宽度 | stock-screener `breadth_calculator_service.py` | 按 ±4% 等阈值统计大涨/大跌股票数量 |
| 复合 RS 评分 | stock-screener `domain/relative_strength/calculator.py` | 多时间框架加权百分位排名 |
| 筛选条件表达式模型 | stock-screener `domain/scanning/filter_expression_model.py` | `FilterExpression` + `FilterGroup` 组合筛选 |
| 数据新鲜度策略 | stock-screener `market_data_freshness.py` | `ScanFreshnessPolicy` 严格/宽松模式 |
| 告警冷却/去重 | daily_stock_analysis `notification_noise.py` | 进程内去重 TTL + 冷却期 |
| 交易日历 | daily_stock_analysis `trading_calendar.py` | 基于 zoneinfo 的交易日检测 |
| 涨停跌停直接 API | AKShare `stock_zt_pool_em()` / `stock_zt_pool_dtgc_em()` | 专门的涨停/跌停股票池函数 |
| 行业板块数据 | AKShare `stock_board_industry_name_em()` | 行业上涨/下跌家数、领涨股票 |

---

## 5. 外部功能对应的准确来源文件

### stock-screener（Apache 2.0）

| 功能 | 文件 | 关键类/函数 |
|------|------|-------------|
| 市场宽度计算 | `backend/app/services/breadth_calculator_service.py` | `BreadthCalculatorService.calculate_daily_breadth()` |
| 市场宽度数据模型 | `backend/app/schemas/breadth.py` | `BreadthResponse` |
| 相对强弱(新) | `backend/app/domain/relative_strength/calculator.py` | `calculate_balanced_rs()`, `StockRsScore` |
| 相对强弱(旧) | `backend/app/scanners/criteria/relative_strength.py` | `RelativeStrengthCalculator` |
| 筛选条件表达式 | `backend/app/domain/scanning/filter_expression_model.py` | `FilterExpression`, `FilterGroup` |
| 数据新鲜度 | `backend/app/services/market_data_freshness.py` | `evaluate_symbol_freshness()`, `ScanFreshnessPolicy` |
| Provider 路由 | `backend/app/domain/providers/data_plan.py` | `ProviderDataPlanRegistry` |
| 市场状态判断 | `backend/app/services/watchlist_stewardship_service.py` | `_compute_regime_label()` |

### daily_stock_analysis（MIT）

| 功能 | 文件 | 关键类/函数 |
|------|------|-------------|
| 调度器 | `src/scheduler.py` | `Scheduler`, `GracefulShutdown` |
| 告警规则 | `src/agent/events.py` | `AlertRule`, `PriceAlert`, `EventMonitor` |
| 告警工作器 | `src/services/alert_worker.py` | `AlertWorker.run_once()` |
| 通知去重/冷却 | `src/notification_noise.py` | `NotificationNoiseDecision`, `evaluate_notification_noise()` |
| 交易日历 | `src/core/trading_calendar.py` | `is_market_open()`, `get_effective_trading_date()`, `MarketPhase` |
| 飞书发送 | `src/notification_sender/feishu_sender.py` | `FeishuSender` |
| 邮件发送 | `src/notification_sender/email_sender.py` | `EmailSender` |
| 告警持久化 | `src/storage.py` | `AlertRuleRecord`, `AlertNotificationRecord`, `AlertCooldownRecord` |

### AKShare（MIT，API 参考）

| 功能 | 文件 | 函数 |
|------|------|------|
| 全 A 实时行情 | `akshare/stock_feature/stock_hist_em.py:15` | `stock_zh_a_spot_em()` |
| 涨停股池 | `akshare/stock_feature/stock_ztb_em.py:24` | `stock_zt_pool_em(date)` |
| 跌停股池 | `akshare/stock_feature/stock_ztb_em.py:439` | `stock_zt_pool_dtgc_em(date)` |
| 行业板块 | `akshare/stock/stock_board_industry_em.py:115` | `stock_board_industry_name_em()` |
| 指数实时行情 | `akshare/index/index_stock_zh.py:208` | `stock_zh_index_spot_em()` |
| 指数历史行情 | `akshare/index/index_stock_zh.py:428` | `stock_zh_index_daily_em()` |
| 个股历史行情 | `akshare/stock_feature/stock_hist_em.py:952` | `stock_zh_a_hist()` |
| 估值数据 | `akshare/stock_fundamental/stock_finance_sina.py:181` | `stock_financial_analysis_indicator_em()` |
| 公司公告 | `akshare/stock_fundamental/stock_notice.py:133` | `stock_notice_report()` |
| 创新高新低 | `akshare/stock_feature/stock_a_high_low.py:15` | `stock_a_high_low_statistics()` |

---

## 6. 可借鉴设计

### stock-screener 可借鉴

1. **BreadthCalculatorService** — 纯函数式市场宽度计算，输入价格 DataFrame 输出按阈值分类的计数
2. **calculate_balanced_rs()** — 多时间框架加权百分位排名，与数据源解耦
3. **ProviderDataPlanRegistry** — (market, dataset) → [ordered providers] 的显式路由，含 fallback 链
4. **ScanFreshnessPolicy** — 严格/宽松模式 + 允许少量陈旧数据的 "stale tail omission" 模式
5. **FilterExpression** + **FilterGroup** — 可组合的筛选表达式模型

### daily_stock_analysis 可借鉴

1. **notification_noise.py** — 仅 91 行，纯标准库的进程内去重和冷却
2. **trading_calendar.py** — 仅依赖 zoneinfo，无外部依赖的交易日检测
3. **AlertRule** 子类体系 — 可扩展的规则类型（价格、涨跌幅、成交量等）
4. **ChannelAttemptResult** — 通知发送尝试的结构化记录

---

## 7. 必须重新实现的部分

1. **恐慌等级分类器** — 基于市场宽度的恐慌判定，Vibe-Trading 独有的业务逻辑
2. **观察池扫描器** — 对配置中的自选股/科技龙头执行扫描，使用 Vibe-Trading 的 Provider
3. **相对强弱计算（简化版）** — MVP 不需要完整百分位排名，只需要个股 vs 大盘 vs 行业的当日/短期比较
4. **涨跌停判断器** — 需考虑主板/创业板/科创板/ST 的不同限制
5. **data_gap 语义** — Vibe-Trading 特有的数据新鲜度标记
6. **dry-run 结果结构** — 输出到控制台/日志，不发送通知

---

## 8. 不应复制的部分

1. stock-screener 的 PostgreSQL + Redis + Celery + nginx 全栈架构
2. stock-screener 的完整用户认证和 watchlist CRUD API
3. daily_stock_analysis 的完整 SQLAlchemy 数据模型和 Web 后台
4. daily_stock_analysis 的 14 种通知渠道（仅需飞书参考）
5. AKShare 源码（仅参考 API 签名）
6. 任何项目的金融阈值（MVP 使用 provisional 示例值）

---

## 9. 不应引入的架构

1. PostgreSQL / Redis / Celery — 引入新依赖
2. SQLAlchemy — Vibe-Trading 已有自己的持久化模式
3. 完整 WebSocket 实时推送 — MVP 仅盘后运行
4. 分钟级监控 — MVP 每个交易日最多一次
5. LLM 全市场扫描 — MVP 使用确定性规则

---

## 10. 建议集成位置

| 新组件 | 建议位置 | 理由 |
|--------|---------|------|
| 市场快照模块 | `agent/src/value_hunter/market_snapshot.py` | 复用 `MarketObservation` 模型 |
| 恐慌分类器 | `agent/src/value_hunter/panic_classifier.py` | 作为 Value Hunter 评分的一部分 |
| 观察池配置 | `config/research/a_share_watchlist.yaml` | 复用项目 YAML 依赖 |
| 相对强弱工具 | `agent/src/value_hunter/relative_strength.py` | 独立可测试的纯函数 |
| 涨跌停判断 | `agent/src/value_hunter/trading_rules.py` | 独立可测试的纯函数 |
| Provider 适配器扩展 | `agent/src/value_hunter/providers.py` | 在 `build_provider()` 中增加新分支 |
| dry-run 结果 | `agent/src/value_hunter/panic_scan.py` | 编排整个 MVP 流程 |

---

## 11. 数据缺口和技术风险

| 风险 | 等级 | 说明 |
|------|------|------|
| AKShare 东方财富源可能封 IP | 中 | 已有新浪备用，但 MVP 需控制调用频率 |
| 股票代码前缀不一致 | 低 | `stock_zh_a_spot_em()` 返回 `代码` 列格式为 `"000001"`，需要与 `".SH"` / `".SZ"` 后缀统一 |
| 创业板/科创板/ST 实时识别 | 中 | 需从代码前缀（`300`/`301`/`688`）和额外 API 判断 ST 状态 |
| 非交易日数据误判 | 低 | 需交易日历判断，防止非交易日缓存被当作当日数据 |
| 节假日数据延迟 | 低 | 长假后首日数据可能延迟更新 |
| 行业板块名称变更 | 低 | 行业分类可能调整，但属于低频变化 |
