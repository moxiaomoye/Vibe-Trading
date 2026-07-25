# A股盘后恐慌初筛 MVP 计划

## MVP 范围

**严格限定：** A股盘后市场快照 → 恐慌分类 → 观察池（自选股+科技龙头）相对强弱初筛

**本轮不实现：**
- 新闻归因、公司独立利空判断、三情景估值、LLM 报告
- Notification Outbox 真实发送、飞书、邮件
- 调度器（手动触发）
- 前端、数据库迁移、全 A 基本面扫描
- 自动交易

---

## 1. 数据流程

```
用户手动触发  →  集中 AKShare Provider 适配器
                      │
                      ├── stock_zh_a_spot_em()      ← 全A行情
                      ├── stock_zt_pool_em(date)    ← 涨停股池
                      ├── stock_zt_pool_dtgc_em(date) ← 跌停股池
                      ├── stock_board_industry_name_em() ← 行业板块
                      └── stock_zh_index_spot_em()  ← 指数行情
                              │
                              ▼
                    市场快照 (MarketSnapshot)
                      │  date, advance, decline, limit_up, limit_down, 大涨/大跌数量, 上涨比例
                      │
                              ▼
                    恐慌分类器 (PanicClassifier)
                      │  NORMAL / CAUTION / PANIC / EXTREME_PANIC
                      │  触发原因, 规则版本
                      │
                              ▼
                    观察池加载 (WatchlistLoader)
                      │  config/research/a_share_watchlist.yaml
                      │
                              ▼
                    个股扫描 (CandidateScanner)
                      │  对每个候选: 当日涨跌, 相对大盘, 相对行业,
                      │  跌停判断, 大跌但未跌停, 数据缺失
                      │
                              ▼
                    dry-run 结果输出 (console/log)
                      │  市场快照 + 恐慌等级 + 候选列表
                      │  不发送通知
```

---

## 2. 使用现有文件和组件

| 现有组件 | 文件 | 用途 |
|---------|------|------|
| `AkshareProvider` | `agent/src/value_hunter/providers.py` | 复用 AKShare 调用模式 |
| `MarketObservation` | `agent/src/value_hunter/models.py` | 扩展或兼容市场快照 |
| `CandidateObservation` | `agent/src/value_hunter/models.py` | 复用候选结构字段 |
| `load_watchlist_csv()` | `agent/src/value_hunter/providers.py` | 备选观察池加载 |
| `_parse_bool` | `agent/src/config/accessor.py` | 配置解析 |
| `try_register_routes` | `agent/src/api/optional_routes.py` | 未来按需注册（本轮不注册路由） |

---

## 3. 新增模块边界

| 新增文件 | 内容 |
|---------|------|
| `agent/src/value_hunter/panic_scan.py` | MVP 编排入口：`run_panic_scan(config) → PanicScanResult` |
| `agent/src/value_hunter/market_snapshot.py` | 市场快照结构 + AKShare 集中适配器 |
| `agent/src/value_hunter/panic_classifier.py` | 恐慌等级分类器（纯函数） |
| `agent/src/value_hunter/trading_rules.py` | 涨跌停判断、交易日检测辅助 |
| `agent/src/value_hunter/relative_strength.py` | 相对强弱计算（纯函数） |
| `agent/src/value_hunter/watchlist_loader.py` | YAML 观察池加载器 |
| `config/research/a_share_watchlist.yaml` | 默认观察池配置文件 |

---

## 4. 数据模型

### MarketSnapshot
```python
@dataclass
class MarketSnapshot:
    trade_date: date
    data_time: datetime
    total_stocks: int
    advance: int       # 上涨数量
    decline: int       # 下跌数量
    flat: int          # 平盘数量
    large_rise: int    # 大涨(>=4%)
    large_decline: int # 大跌(<=-4%)
    limit_up: int      # 涨停
    limit_down: int    # 跌停
    advance_ratio: float  # 上涨比例
    decline_ratio: float  # 下跌比例
    source: str
    data_gap: DataGap
    rule_version: str
```

### DataGap
```python
@dataclass
class DataGap:
    is_stale: bool
    last_trade_date: date | None
    gap_days: int
    description: str
```

### PanicLevel (Enum)
```python
class PanicLevel(Enum):
    NORMAL = "normal"
    CAUTION = "caution"
    PANIC = "panic"
    EXTREME_PANIC = "extreme_panic"
```

### PanicClassification
```python
@dataclass
class PanicClassification:
    level: PanicLevel
    reasons: list[str]
    rule_version: str
    components: dict[str, float]  # 各维度值
```

### WatchlistConfig
```python
@dataclass
class WatchlistConfig:
    version: str
    watchlist_name: str
    symbols: list[str]
    content_hash: str
```

### ScannedCandidate
```python
@dataclass
class ScannedCandidate:
    symbol: str
    name: str
    close: float
    change_pct: float
    relative_to_market: float | None   # 相对大盘
    relative_to_sector: float | None   # 相对行业
    is_limit_down: bool | None         # None=数据不足
    is_sharp_decline: bool             # 大跌但未跌停
    is_suspended: bool | None
    data_gap: DataGap
```

### PanicScanResult
```python
@dataclass
class PanicScanResult:
    scanned_at: datetime
    market_snapshot: MarketSnapshot
    panic: PanicClassification
    watchlist: list[ScannedCandidate]
    rule_version: str
    data_date: date
```

---

## 5. 配置结构

```yaml
# config/research/a_share_watchlist.yaml
version: "1.0.0"
watchlist:
  name: "default_watchlist"
  symbols:
    - "600522.SH"
    - "300308.SZ"
    - "688981.SH"
    - "002371.SZ"
    - "000977.SZ"
    - "300750.SZ"
    - "000858.SZ"
    - "600519.SH"
    - "002594.SZ"
    - "688041.SH"
    - "002230.SZ"
    - "300124.SZ"
    - "688111.SH"
    - "300274.SZ"
    - "688256.SH"
    - "600703.SH"
    - "688012.SH"
    - "603501.SH"
    - "300661.SZ"
    - "002475.SZ"
```

恐慌阈值配置（provisional，待确认）：
```python
# 在 PanicClassifier 内使用配置对象，阈值不散落在代码中
@dataclass
class PanicThresholds:
    # CAUTION: 下跌比例 > 70% 或 跌停 > 30
    caution_decline_ratio: float = 0.70
    caution_limit_down: int = 30
    # PANIC: 下跌比例 > 85% 或 跌停 > 80
    panic_decline_ratio: float = 0.85
    panic_limit_down: int = 80
    # EXTREME_PANIC: 下跌比例 > 95% 或 跌停 > 200
    extreme_decline_ratio: float = 0.95
    extreme_limit_down: int = 200
```

---

## 6. Provider 边界

AKShare 只通过 `market_snapshot.py` 中的集中适配器访问：

```python
# agent/src/value_hunter/market_snapshot.py
class AkshareSnapshotFetcher:
    """集中 AKShare 适配器，封装所有实时数据调用"""
    
    def fetch_all_a_spot(self) -> DataFrame: ...
    def fetch_limit_up_pool(self, date: str) -> list[str]: ...
    def fetch_limit_down_pool(self, date: str) -> list[str]: ...
    def fetch_industry_breadth(self) -> DataFrame: ...
    def fetch_index_spot(self) -> DataFrame: ...
```

所有其他模块（恐慌分类、相对强弱、涨跌停判断）都接收处理后的数据，不直接调用 AKShare。

---

## 7. 交易日和数据日期处理

- 使用 `datetime.date.today()` 作为预计交易日
- 检查数据中的实际日期，与预期比较
- 如果数据日期与预期不一致，标记为 `data_gap`
- 旧数据（gap_days > 1）标记为 stale，panic 分类降低置信度
- 不在非交易日运行（由触发方保证，代码不做自动跳过）

---

## 8. 防未来数据穿越

- 所有分析使用数据中的 `trade_date` 字段，不使用 `datetime.now()`
- 数据新鲜度检查确认数据日期 ≤ 当前日期
- 如果数据日期 > 当前日期，标记为 `data_gap` 并拒绝分析

---

## 9. 涨跌停判断

```python
# agent/src/value_hunter/trading_rules.py
def classify_limit_rule(symbol: str) -> LimitRule:
    """
    根据股票代码前缀判断涨跌停限制：
    - 600/601/603/605 → 主板 10%
    - 000/001/002 → 主板 10%
    - 300/301 → 创业板 20%
    - 688 → 科创板 20%
    - 4xx/8xx → 北交所 30%
    - ST 股票在上述基础上减半（由调用方标记）
    """

def is_limit_down(close: float, prev_close: float, rule: LimitRule, is_st: bool) -> bool:
    """
    判断是否跌停。
    考虑：停牌、无成交、数据不足等边界情况。
    当数据不足时返回 None 而不是 False。
    """
```

---

## 10. 规则版本

- `rule_version` 为 `"1.0.0"`
- 每次修改阈值或规则逻辑时手动更新
- 恐慌分类结果始终记录使用的规则版本
- 观察池配置包含 `version` 字段和内容哈希

---

## 11. 测试策略

| 测试场景 | 输入 | 断言 |
|---------|------|------|
| 正常市场 | 上涨>70%, 跌停<10 | PanicLevel.NORMAL |
| 下跌明显 | 下跌>70%, 跌停>30 | PanicLevel.CAUTION |
| 大面积下跌 | 下跌>85%, 跌停>80 | PanicLevel.PANIC |
| 极端恐慌 | 下跌>95%, 跌停>200 | PanicLevel.EXTREME_PANIC |
| 数据缺失 | NaN/None 数据 | data_gap 非空 |
| 数据日期不一致 | 数据日期 < 当前日期 | data_gap.is_stale=True |
| 主板跌停 | 600xxx, -10.05% | is_limit_down=True |
| 创业板跌停 | 300xxx, -20.01% | is_limit_down=True |
| ST 跌停 | 600xxx ST, -5.02% | is_limit_down=True |
| 大跌但未跌停 | -8.5%, 非跌停 | is_sharp_decline=True |
| 个股相对抗跌 | 个股-2%, 大盘-5% | relative_to_market > 0 |
| 行业数据缺失 | 行业数据不可用 | relative_to_sector=None |
| 停牌 | 当日无成交 | is_suspended=True |
| 观察池版本变化 | 修改 YAML | content_hash 不同 |
| 默认关闭测试 | 不设 env var | 模块不导入 |

---

## 12. 回滚方式

- 所有新增文件均在 `agent/src/value_hunter/` 和 `config/research/` 内
- 不修改 `api_server.py`、`optional_routes.py`、核心路由
- 删除新增文件和 `docs/architecture/` 即可完全回滚
- Git 命令：`git checkout feat/optional-research-loader` 并删除分支

---

## 13. 后续接入 Notification Outbox 的设计

本轮不实现。设计预留：

1. `PanicScanResult` 结构可直接序列化为 Notification Outbox payload
2. 恐慌分类结果中的 `level` 可作为通知优先级
3. `ScannedCandidate` 列表可作为通知附件
4. 接入点：在 `panic_scan.py` 中增加一个可选的 `notifier` 参数

---

## 14. 不属于当前 MVP 的内容

- LLM 市场解读
- 公司独立利空自动判断
- 三情景估值模型
- 全 A 基本面扫描
- 新闻舆情分析
- 飞书/邮件通知
- 调度器自动执行
- 前端界面
- 数据库持久化
- 自动交易
