# Value Hunter：A股科技价值提醒

Value Hunter 是 Vibe Trading 内置的收盘后研究筛选器。它不下单，也不预测最低点；只有市场恐慌评分和公司研究评分同时达到阈值时，才把候选发送到飞书或邮箱。

## 运行逻辑

1. 每个交易日 18:10（Asia/Shanghai）读取沪深300、中证500、中证1000、创业板指和上证指数。
2. 用趋势破位、指数回撤、市场宽度和恐慌程度计算 0–100 分市场评分。
3. 从科技观察池读取估值、盈利、现金流和一年回撤数据。
4. 将公司分为价值错杀、优质成长、情绪龙头、普通观察，并执行风险否决和数据完整性检查。
5. 市场分不低于 70、公司分不低于 75 时才推送；同一天相同候选只推送一次。

数据缺失不会被补造。关键字段不完整的公司会标记为 `C - 数据不足`，不会进入提醒名单。

## 页面与接口

- 网页：`http://localhost:8000/value-hunter`
- 状态：`GET /value-hunter/status`
- 历史：`GET /value-hunter/history`
- 手动扫描：`POST /value-hunter/run?notify=false`

网页上的“立即扫描”固定使用 `notify=false`，用于查看结果，不会发送测试消息。定时任务按配置执行真实提醒。

## 通知配置

在 `agent/.env` 中填写：

```dotenv
VALUE_HUNTER_FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/你的Webhook

VALUE_HUNTER_SMTP_HOST=smtp.example.com
VALUE_HUNTER_SMTP_PORT=465
VALUE_HUNTER_SMTP_USERNAME=你的发件账号
VALUE_HUNTER_SMTP_PASSWORD=你的SMTP授权码
VALUE_HUNTER_SMTP_FROM=你的发件账号
VALUE_HUNTER_EMAIL_TO=你的收件邮箱
```

重启后在状态页确认 `notification_channels` 包含 `feishu` 和 `email`。程序会分别尝试两个通道，一个通道失败不会阻止另一个通道，错误会写入当次扫描记录。

## 自定义科技观察池

复制 `agent/value_hunter_watchlist.example.csv`，填写自己的时点数据，然后配置：

```dotenv
VALUE_HUNTER_WATCHLIST_PATH=/app/agent/value_hunter_watchlist.csv
```

默认观察池包含半导体、算力、光模块、PCB、国产软件、工业 AI 与自动驾驶方向的代表公司。CSV 中的财务和估值数据必须来自当时已经公开的资料，避免前视偏差。

## 启动与验证

```powershell
docker compose up -d --no-build --force-recreate vibe-trading
docker compose ps
```

浏览器打开 `http://localhost:8000/value-hunter`。若当前市场未达到 70 分，页面显示“正常”且没有候选提醒属于预期行为。

## 研究边界

评分用于缩小研究范围，不构成买入建议。公司即使进入 A/B 名单，也必须人工检查最新公告、审计意见、行业周期、估值口径和首要否决项。强周期行业不应只凭低 PE 判断便宜。
