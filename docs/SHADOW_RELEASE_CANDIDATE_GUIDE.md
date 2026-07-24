# Trial Release：可信盘后报告试用指南

## 定位

这是只读的盘后研究流程，不是荐股、自动交易或自动调度系统。它可以：

- 通过盘后 Provider 获取当日 A 股数据，生成影子研究报告；
- 通过浏览器导入当日 JSON 数据，生成同一格式的报告；
- 将成功报告保存到 Docker 的 `vibe-home` 命名卷；
- 在浏览器中重新打开最近一份报告。

报告仍需人工复核。调度、通知投递、渠道自动启动和交易在试用启动方式中保持关闭。

## 前置条件

1. Docker Desktop 已启动；
2. 当前代码已经构建过 Compose 镜像：

   ```powershell
   docker compose build vibe-trading
   ```

3. 本地 `agent/.env` 和浏览器设置中已有项目原本使用的 API 认证配置；
4. 浏览器的 **Settings → Server API key** 已保存同一个本地密钥。

启动脚本不会安装 Python 包、不会修改 `agent/.env`、不会构建镜像。

## 一条命令启动

在项目根目录执行：

```powershell
.\scripts\start_market_shadow.ps1
```

脚本会：

1. 校验 Compose 配置和现有镜像；
2. 使用临时 Compose override 开启：
   - `INVESTMENT_RESEARCH_ROUTES_ENABLED=true`
   - `PANIC_SHADOW_REPORT_API_ENABLED=true`
3. 强制保持：
   - `VALUE_HUNTER_ROUTES_ENABLED=false`
   - `VALUE_HUNTER_ENABLED=false`
   - `VIBE_INVESTMENT_RESEARCH_ENABLED=false`
   - `VIBE_TRADING_ENABLE_SCHEDULER=false`
   - `VIBE_TRADING_CHANNELS_AUTO_START=false`
   - `VIBE_RESEARCH_DELIVERY_MODE=disabled`
4. 使用已有镜像启动 `vibe-trading`；
5. 等待容器变为 `healthy` 并检查 `/live`；
6. 打开真正的前端页面：
   `http://127.0.0.1:8899/investment-research`。

只启动、不打开浏览器：

```powershell
.\scripts\start_market_shadow.ps1 -NoBrowser
```

## 浏览器试用

打开：

```text
http://127.0.0.1:8899/investment-research
```

页面提供三个盘后操作：

- **Generate current report**：调用 Provider 获取当日盘后数据；
- **Import manual JSON**：导入明确的当日数据；
- **Load latest report**：重新打开最近一次成功保存的报告。

API 认证失败时，先到 Settings 保存 Server API key，不要把密钥写进导入文件或日志。

## Provider 模式

`POST /investment-research/panic-shadow/run-current`

当前盘后 Provider 采用组件级来源与降级：

- Spot：东方财富优先，新浪备用；
- 沪深 300 基准：东方财富优先，新浪备用；
- 涨跌停：官方池优先；不可用时仅在输入足够时复用项目交易规则从 Spot 推算，并明确标记；
- 行业收益：来源不可用时保留 data gap，不伪造成功。

Provider 依赖真实上游网络。全部 Spot 来源不可用时返回结构化 `data_unavailable`，不会生成空成功报告。

## Manual Import 模式

`POST /investment-research/panic-shadow/run-manual`

浏览器导入示例：

```json
{
  "schema_version": "1.0",
  "source": "manual_import",
  "source_date": "2026-07-25",
  "availability_time": "2026-07-25T18:30:00+08:00",
  "rows": [
    {
      "symbol": "000001",
      "name": "示例公司",
      "close": 12.5,
      "previous_close": 12.3,
      "change_percent": 1.63,
      "volume": 12345,
      "benchmark": -0.8
    }
  ]
}
```

规则：

- `source_date` 必须是当前上海日期；
- `availability_time` 必须带时区，且不得来自未来；
- `symbol`、`name`、`close`、`previous_close`、`change_percent` 为必填字段；
- 价格必须为有限正数；
- 文件和行数有上限；
- 市场宽度只代表导入的样本范围，报告会明确记录该 data gap；
- 手工数据始终标记为 `manual_import`，不会伪装为官方数据。

## API

所有下列接口沿用现有 Bearer API 认证：

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/investment-research/panic-shadow/status` | 查看只读功能状态 |
| POST | `/investment-research/panic-shadow/run-current` | 使用当日 Provider 数据生成并保存报告 |
| POST | `/investment-research/panic-shadow/run-manual` | 使用当日手工 JSON 生成并保存报告 |
| GET | `/investment-research/panic-shadow/latest` | 读取最近一份成功报告 |
| POST | `/investment-research/panic-shadow/run` | 使用明确的底层 fixture/契约输入执行 dry-run |

路由关闭时，这些路径返回 JSON 关闭态或结构化错误，不会落入 SPA HTML。

## 报告保存

容器内保存位置：

```text
/home/vibe/.vibe-trading/panic-shadow-reports
```

该目录位于 Compose 的 `vibe-home` 命名卷中。重建容器后报告仍可读取；停止脚本不会删除容器、镜像、命名卷或报告。

报告文件包括：

- `<source-date>/<fingerprint>.json`
- `<source-date>/<fingerprint>.md`
- `latest.json`

## 停止、验证和诊断

停止服务但保留全部数据：

```powershell
.\scripts\stop_market_shadow.ps1
```

验证 `/live` 和路由状态：

```powershell
.\scripts\verify_market_shadow.ps1
```

采集不含凭据、且不改变运行状态的诊断：

```powershell
.\scripts\collect_shadow_diagnostics.ps1
```

## 当前限制

1. 仅接受当前上海日期的浏览器 Manual Import，不提供历史日期伪装；
2. Provider 可受第三方接口、DNS、限流和交易日数据发布时间影响；
3. 财务、公告和行业证据缺失时会保留 data gap，研究结论不会假装证据完整；
4. 报告是 Research Candidate 研究材料，不是买卖建议；
5. 本试用环境没有自动调度、真实通知或交易执行；
6. 前端由 Docker 镜像内已构建的静态资源提供，不需要单独运行 Node 开发服务器；
7. `8898` 仅用于隔离验收；日常一键试用使用 `127.0.0.1:8899`。
