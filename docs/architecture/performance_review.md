# Vibe-Trading 性能审查

## 1. 结论

项目当前适合本地研究、中小规模回测和少量标的的定时扫描；性能风险主要不是单一算法慢，而是多个子系统在同一 Python 进程内争用 CPU、线程、网络和文件 I/O。

最先出现的瓶颈预计是 **Value Hunter 逐股票远程请求**，随后是 **Pandas 因子/回测计算与文件型状态存储**。扩展到 5,000—10,000 只标的前，需要从“请求驱动、进程内任务、JSON/SQLite 零散存储”演进为“批量数据摄取、增量特征、持久任务队列和分离 worker”。

性能成熟度评级：**★★★☆☆（3.0 / 5）**

## 2. CPU 热点

### 2.1 因子与横截面运算

因子库约 461 个实现文件，大量使用 Pandas rolling、rank、correlation、neutralize 和 groupby。复杂度大致随 `因子数 × 股票数 × 时间长度` 增长，横截面相关矩阵还可能达到 `O(S² × T)`。

未来热点：

- Alpha101、GTJA 等滚动窗口重复计算相同中间量；
- 多因子同时计算时重复排序、收益率、行业分组；
- 逐因子 DataFrame 复制和 dtype 转换；
- 大规模相关性、IC 和组合对比。

优化方向：共享基础特征 DAG、按列批处理、Polars/NumPy/Numba 或 DuckDB 向量化、按日期增量计算、将相同窗口的 rolling 结果缓存一次。

### 2.2 回测与验证

`backtest/runner.py` 同时执行数据准备、策略运行、指标和报告。Walk-forward、bootstrap、Monte Carlo 和多策略比较会成倍放大 CPU 消耗。Alpha API 目前以进程内 job 和 semaphore 限制并发，适合少量任务，但高负载时所有任务共享 Web 进程资源。

### 2.3 Agent 与 AI 上下文

AgentLoop 会序列化历史消息和工具结果，必要时进行上下文压缩。长会话下 JSON 拼接、截断、tokenization 和压缩 LLM 调用都会增加 CPU 与延迟。工具结果上限约 80,000 字符，仍可能产生较大的临时对象。

### 2.4 Value Hunter 评分

当前十几只股票时本地评分不是主要热点；扩展到数千只后，历史分位、财务派生指标、公告关键词和候选排序会成为次级 CPU 热点。但相比逐股票网络请求，它仍较容易通过批处理解决。

## 3. I/O 热点

### 3.1 JSON/JSONL 文件

- Session 元数据为 JSON，消息为 JSONL；每条消息 append 后 `fsync`，可靠但高频对话时写放大明显。
- Session 列表需要扫描目录并解析多个 JSON 文件。
- Swarm event/task 使用文件存储，部分查询会读取整个 JSONL。
- `SwarmStore._last_event_timestamp` 为获得最后时间也读取全文件。
- ScheduledResearchStore 每次 CRUD 加载并重写完整 JSON。

当会话、任务和事件数量增长后，目录遍历、全文件解析及频繁 fsync 会成为稳定热点。

### 3.2 Parquet 与 DuckDB

Loader 对已结算日期范围使用 Parquet 缓存，并采用临时文件后替换，设计较好。但每次读写可能新建内存 DuckDB 连接；大量小分区和小查询时，连接与文件元数据成本会占比上升。

建议按交易日/市场分区，避免每股一个小文件；批量 compact 小文件，并复用查询连接或统一交给数据服务。

### 3.3 Value Hunter 缓存

日级 JSON 缓存能让相同日期的第二次扫描从数分钟降到亚秒级，但首次扫描仍慢；写入不是统一的原子缓存服务，缺少 schema version、完整性校验和细粒度 TTL。它解决了重复请求，不解决全市场摄取。

## 4. 数据库瓶颈

项目同时存在多个独立持久化机制：

- Session JSON/JSONL；
- SessionSearch SQLite FTS5；
- StrategyStore SQLite WAL；
- Value Hunter SQLite，结果以 JSON payload 为主；
- ScheduledResearch JSON；
- Swarm 文件状态；
- Loader Parquet。

### 4.1 SQLite

SQLite 对本地单进程很合适，StrategyStore 已使用 RLock、事务和 WAL，是较好的实现。但整体风险包括：

- 多 worker 或多进程下单写者竞争；
- Value Hunter 扫描历史不断增长，JSON payload 难以索引和聚合；
- SessionSearch 使用 `check_same_thread=False` 的共享连接，操作级锁策略不清晰；
- 各 store 独立建表、迁移和备份，没有统一 schema/version 管理。

### 4.2 未来数据库瓶颈

在 1,000 只股票日频下，SQLite 仍可承载元数据和扫描结果；在 5,000—10,000 标的、多用户、多 worker、AI 分析和历史回测并行时，单写者和本地文件锁会限制吞吐。届时应把任务、元数据、通知状态和查询索引迁入 PostgreSQL；大行情和特征留在分区 Parquet/Object Storage，通过 DuckDB/Polars/Spark 类计算层读取。

## 5. 缓存审查

### 已有优点

- Loader 对稳定历史数据缓存，并避免对未结算日期盲目持久化。
- Value Hunter 有按日 provider 缓存。
- SSE 为每个 session 保留最近事件，支持重连补发。

### 缺口

- 无统一 cache key、版本、TTL、命中率和失效策略。
- 财务、估值、公告、行情采用不同更新频率，却共享粗粒度日缓存思路。
- 无跨任务共享的基础特征缓存，因子和回测可能重复计算。
- 无失败缓存/熔断，供应商故障时可能重复击打接口。
- 无集中式缓存容量上限和清理策略。

建议建立数据分层：raw → normalized → point-in-time feature → screen result。每层 key 包含 provider、schema version、as-of time 和参数 hash。

## 6. 网络请求

### 6.1 Value Hunter

当前实现对每个股票分别请求估值与财务数据，使用最多 4 个线程；公告还可能按 7 个日期拉取全市场报告。已观察到约 14 个标的首次扫描耗时约 **457 秒**，同日缓存后约 0.1 秒。

线性外推没有精确意义，但足以证明逐股公网请求在 1,000 只以上不可用。5,000 只股票如果仍按此模式，延迟、限流、失败率和数据不一致都会成为系统主导问题。

应优先使用批量 EOD 数据、交易所/供应商增量文件或数据库快照；网络 provider 只作为补缺和人工复核，不作为全市场主路径。

### 6.2 LLM 与 MCP

LLM、MCP server、搜索和外部工具均属于高延迟网络依赖。若对每个候选逐一调用 AI，成本和吞吐会随候选数线性增长。应先用确定性规则将全市场缩到几十个候选，再将结构化证据打包成有限批次进行 AI 分析。

### 6.3 渠道通知

邮件、飞书等通知当前同步调用，慢响应会延长整个扫描任务。缺少 per-channel outbox、指数退避、熔断和死信队列。某一渠道失败时的重试状态还与总体 fingerprint 耦合。

## 7. 并发

项目内存在多个独立并发机制：

- Agent 只读工具线程并行，上限约 8；
- Swarm 每层创建 ThreadPoolExecutor；
- Value Hunter provider 线程池约 4；
- Alpha job 使用 asyncio semaphore；
- API 使用 `asyncio.to_thread` 运行阻塞任务；
- 渠道各自持有网络循环或后台任务。

问题不在于某个并发数过大，而在于没有全局资源预算。多个扫描、回测、Swarm 和 Agent 同时运行时，线程数、网络连接和内存会叠加。

建议：

1. 将 CPU、网络、LLM 和通知分别放入有界队列。
2. 全局 worker pool，而不是每层/每任务新建线程池。
3. API 只提交任务，不直接承载长计算。
4. 对 provider 设置每域名 QPS、并发和熔断。
5. 为每种 workload 设置配额和优先级。

## 8. 线程安全

### 风险点

- Agent 工具超时后，daemon worker 线程仍可能继续运行；连续挂起会积累后台资源。
- Swarm 超时后采用 `wait=False`，已运行线程不会被强制终止。
- SessionSearch 共享 SQLite connection 设置 `check_same_thread=False`，但操作级串行化不明显。
- Value Hunter 扫描锁是进程内锁，多 worker 部署时不能避免重复扫描。
- 多个文件 store 对同一路径的跨进程写没有统一锁。
- SSE 订阅者队列和 session buffer 依赖进程内内存，多 worker 时事件视图分裂。

### 建议

- 不可取消的阻塞工具进入独立进程，超时可终止进程。
- 使用数据库 advisory lock/lease 保证单次调度唯一性。
- SQLite 每线程/请求连接，或通过 repository 串行写入。
- 文件存储只保留单进程本地模式；服务化部署迁到共享持久层。

## 9. 内存占用

主要增长点：

- 大股票池 × 长历史 × 多字段的 Pandas DataFrame；
- 因子矩阵和相关矩阵的多份拷贝；
- Alpha job 结果保存在进程内；
- SSE 每 session 500 条事件、每 subscriber 200 条队列，缺乏自动淘汰；
- 前端 Agent 页面持续保留消息和事件；
- Session/Swarm 查询读取整个 JSONL；
- LLM 工具结果和上下文序列化产生大字符串临时副本。

建议按日期/股票块流式读取，优先列式类型；结果分页；事件 buffer 使用 TTL/LRU；大型任务结果落盘而不是留在 job dict；限制单工具结果的结构和列数，而不仅是字符截断。

## 10. 哪些地方以后一定会成为瓶颈

按出现顺序判断：

1. **逐股票远程数据请求**：股票池一扩展就先失效。
2. **数据标准化与时点一致性**：不同 provider 返回时间、复权和财报可得日期不一致，会先影响正确性，再影响性能。
3. **Pandas 重复特征计算**：因子、筛选和回测重复读取、重复 rolling。
4. **Web 进程内长任务**：扫描、回测、AI 分析互相争用。
5. **JSON/JSONL 状态存储**：会话和任务量增长后全文件扫描与写放大。
6. **SQLite 单写者**：多 worker 和多用户时明显。
7. **AI 调用吞吐与成本**：对每股调用将不可控。
8. **通知可靠性与扇出**：渠道增多后同步发送、统一去重不够用。
9. **SSE/进程内 job 状态**：多实例部署后状态不一致。
10. **相关矩阵和大规模回测**：10,000 标的与大量因子时内存和 CPU 二次增长。

## 11. 分阶段优化建议

### P0：正确性和可观测性

- 为每次 provider 请求记录耗时、状态、重试、缓存命中和数据量。
- 通知改为按渠道 outbox，失败独立重试。
- 给所有内存队列、缓存和任务结果设置上限、TTL 和清理。
- 明确共享 SQLite connection 的线程模型。

### P1：1,000 只股票

- 停止逐股票公网请求，建立批量 EOD 摄取。
- Parquet 按市场/日期分区，DuckDB/Polars 批量计算。
- 特征增量化，只计算新增交易日。
- 扫描任务移出 API event loop，使用持久 worker。

### P2：5,000 只股票

- PostgreSQL 管理任务、结果索引、通知和配置版本。
- Object Storage/本地数据湖保存 raw 与 feature 数据。
- Redis 或数据库队列提供租约、限流与幂等。
- CPU 任务进程池或独立计算 worker，网络任务异步化。

### P3：10,000 只股票及多市场

- 数据和研究平面解耦；分市场分区与并行。
- 预计算市场宽度、行业聚合和共享基础因子。
- AI 仅处理规则筛选后的证据包。
- 回测、实时 Agent 与日终扫描使用独立资源池。
- 建立容量压测：数据到达延迟、扫描完成 SLA、峰值内存、失败恢复时间。

## 12. 五星评级

| 维度 | 评级 | 说明 |
|---|---|---|
| CPU 效率 | ★★★☆☆ | 向量化基础存在，但共享特征和任务隔离不足 |
| I/O 设计 | ★★★☆☆ | Parquet 缓存较好，JSON/JSONL 全量读写较多 |
| 数据库 | ★★★☆☆ | 本地模式适配良好，多进程扩展受限 |
| 缓存 | ★★★☆☆ | 有效但碎片化、粒度较粗 |
| 网络效率 | ★★☆☆☆ | Value Hunter 逐股请求是明确瓶颈 |
| 并发与线程安全 | ★★★☆☆ | 有界并发意识存在，缺少全局预算和可取消性 |
| 可观测性 | ★★☆☆☆ | 尚不足以持续定位吞吐和延迟问题 |
| 综合 | **★★★☆☆** | **3.0 / 5** |

