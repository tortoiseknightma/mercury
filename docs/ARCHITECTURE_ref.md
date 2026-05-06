# 架构

StockAgent 内部架构技术文档。

---

## 系统概览

```
                     CLI / Web / 守护进程
                            |
                      Agent (agent.py)
            ┌─────────┬─────┴─────┬──────────┐
         数据源    分析引擎     执行层     记忆系统
                       |           |
                LLM/多 Agent    风控引擎
                       |           |
                       └─── 经纪商抽象层 ───┘
                            |     |     |
                       模拟  IBKR  Alpaca
```

Agent 通过中央协调器（`agent.py` 的 `StockAgentAgent`）编排各子系统，每个子系统均可独立测试和替换。CLI（`cli.py`）、Web Dashboard（`web/server.py` 的 FastAPI 应用）、定时守护进程（`cli daemon`）三种入口共享同一个 Agent。

---

## 经纪商抽象层

所有市场交互均通过 `BaseBroker` 接口（`core/broker/base.py`，13 个抽象方法）进行，系统其他部分不直接接触具体经纪商实现。

```
BaseBroker (ABC)
  |
  +-- SimulatedBroker    本地模拟，GBM 价格模型，状态持久化
  +-- IBKRBroker         通过 ib_insync 连接真实 IBKR（paper 7497 / live 7496）
  +-- AlpacaBroker       通过 alpaca-py 连接 Alpaca paper（REST，无本地网关）
```

**工厂**：`create_broker(config)` 根据 `trading_mode` 返回对应实现。

支持两种 paper trading 提供方，可通过配置切换：
- `trading_mode: paper` → IBKR（需本地运行 TWS/Gateway）
- `trading_mode: alpaca_paper` → Alpaca（纯 REST，无需本地网关，开户更容易）
- `trading_mode: simulated` → 本地模拟（默认，零依赖）
- `trading_mode: live` → IBKR 真实账户（需显式确认，默认 readonly）

### 模拟经纪商

使用几何布朗运动（GBM）模拟价格：

```
dS = mu * S * dt + sigma * S * dW
```

- 可配置漂移率（默认：年化 5%）和各 ticker 的波动率
- 模拟真实的买卖价差（5 个基点）
- 手续费与滑点建模
- 状态持久化至 `data/sim_state.json`，跨会话保留

### IBKR 经纪商

通过 `ib_insync` 连接 TWS 或 IB Gateway，支持：
- 账户与持仓查询
- 实时行情数据
- 市价单、限价单和止损单
- 历史价格数据

### Alpaca 经纪商

通过 `alpaca-py` 连接 Alpaca paper trading（REST），支持：
- 账户 / 持仓 / 订单查询
- IEX（免费）或 SIP（付费）行情数据源
- 市价单、限价单、止损单和止损限价单
- 历史 OHLCV 行情

适用于无法运行本地 TWS/Gateway 或 IBKR 开户受阻的情况。该适配器**不暴露 live 模式** —— 真实交易请走 IBKR 通路。

---

## 分析引擎

四个分析器各自输出 -1（看空）到 +1（看多）的评分，`CompositeAnalyzer` 负责聚合。该层既被单 Agent 模式直接调用，也作为多 Agent 流水线的输入数据源。

### 技术分析器

| 指标 | 衡量内容 | 信号逻辑 |
|------|----------|----------|
| SMA/EMA 交叉 | 趋势方向 | 价格与均线的位置关系，金叉/死叉 |
| RSI | 超买/超卖 | >70 卖出，<30 买入 |
| MACD | 动量 | 信号线交叉，柱状图方向 |
| 布林带 | 波动率位置 | 价格在带内的相对位置（%B） |
| 成交量 | 信号确认 | 高成交量确认价格方向 |
| 线性回归 | 整体趋势 | 20 个周期的斜率方向 |

### 基本面分析器

对四个维度评分：

1. **估值** — P/E、PEG、P/B，与行业基准对比
2. **成长性** — 营收和盈利增长率
3. **盈利能力** — 净利率、ROE、营业利润率
4. **财务健康** — 负债权益比、流动比率

评分采用行业专项基准（例如科技公司的 P/E 预期高于公用事业公司）。

### 情绪分析器

- 基于规则的 NLP，对新闻标题进行正负向词匹配
- 按发布时间加权聚合（近期文章权重更高）
- 集成 VIX（市场恐慌指数）

### 综合信号

```
composite = w1 * 技术 + w2 * 基本面 + w3 * 情绪 + w4 * 动量
```

默认权重：技术 0.35，基本面 0.35，情绪 0.15，动量 0.15。

额外输出：
- 信号一致性检查（各分析器是否方向一致？）
- 置信度评分（0-1）
- 风险等级评估
- 可读性推荐描述

---

## LLM 分析模块

`analysis/llm/` 下的六个独立模块，可被单 Agent 流程或多 Agent 流水线按需调用。所有模块走统一的 OpenAI-Compat 客户端（`core/llm/openai_compat.py`），支持 Qwen / Ark / OpenAI 等任意兼容服务。

| 模块 | 文件 | 职责 |
|------|------|------|
| 牛熊辩论引擎 | `debate_engine.py` | 牛/熊各 5 轮对辩 + 裁判模型给出最终立场，输出 `BullishVerdict` / `BearishVerdict` / `Neutral` |
| 新闻深度分析 | `news_analyzer.py` | 对单 ticker 的近期新闻做 60/40 混合打分（事件影响 0.6 + 整体语调 0.4） |
| 财报解读 | `earnings_analyzer.py` | 解析 EPS / 营收 / 业绩指引，生成投资影响判断 |
| 投资论点生成 | `thesis_generator.py` | 同时产出多空两份投资逻辑，便于人工对比裁断 |
| 风险评估 | `risk_assessor.py` | 组合层面的风险打分（集中度、相关性、回撤暴露） |
| 反思引擎 | `reflection_engine.py` | 收盘后扫描当日卖出交易，提炼经验写入长期记忆 |

每模块都使用 reasoning model（默认 `qwen3.5-plus` 或对应 ark 模型）做关键判断，flash model（`qwen3.5-flash`）做轻量步骤以节省 token。

---

## 多 Agent 流水线

`agents/graph.py` 的 `TradingGraph` 编排 12 个 Agent，分四层串行执行。当 `agents.enabled: true` 且使用 `cli analyze --agents` 或所有定时 routine 时启用。

```
Layer 1  分析师层（并行）
   ├── TechnicalAnalyst    解读量价指标
   ├── FundamentalAnalyst  解读财务比率
   ├── SentimentAnalyst    解读新闻情绪
   └── MacroAnalyst        解读宏观面（VIX / 利率 / 商品 / 板块 ETF）

Layer 2  研究层（多轮辩论）
   ├── BullResearcher  ←┐
   ├── BearResearcher  ←┤  对辩 N 轮（默认 1）
   └── ResearchManager →┘  reasoning model 裁断，输出投资立场

Layer 3  执行层
   └── TraderAgent     基于研究立场起草具体订单（方向 / 仓位 / 止损止盈）

Layer 4  风控辩论层
   ├── AggressiveDebator    ←┐
   ├── ConservativeDebator  ←┤  三方辩论 N 轮（默认 1）
   ├── NeutralDebator       ←┤
   └── PortfolioManager     →┘  最终决策：执行 / 修改仓位 / 拒绝
```

**通信方式**：所有 Agent 不直接互相调用，统一读写 `AgentState`（共享状态对象），便于审计每一步的输入输出。完整说明见 `docs/MULTI_AGENT_ARCHITECTURE.md`。

**单次调用成本**：12 个 Agent 串行 + 多轮辩论，单 ticker 完整跑完通常 1–3 分钟，token 消耗显著高于单 Agent 模式 —— 因此 daemon 仅在 premarket / postmarket / deep_research 启用，intraday 走轻量规则不调 LLM。

---

## 风控引擎

交易前验证。任一 BLOCKER 规则触发，交易即中止。

| 规则 | 默认值 | 类型 |
|------|--------|------|
| 单股最大仓位集中度 | 组合的 20% | BLOCKER |
| 单笔最大交易规模 | 组合的 5% | BLOCKER |
| 每日亏损上限 | 组合的 3% | BLOCKER |
| 每日最大交易次数 | 10 次 | BLOCKER |
| 卖空限制 | 必须持有股票 | BLOCKER |
| 大额交易阈值 | $5,000 | 警告 |
| 止损线 | 成本价以下 8% | 自动卖出 |
| 止盈线 | 成本价以上 20% | 自动卖出 |
| 最大回撤 | 15% | 警告 |

风控引擎还会计算风险调整后的仓位规模 —— 若请求的交易量超出限制，返回最大允许数量而非直接拒绝。所有被拦截的交易都会写入 trade journal，便于事后审计 Agent "想做什么"和"为什么没做"。

---

## 交易执行流程

```
分析引擎信号
     |
  风控引擎校验
  /           \
通过          拒绝
 |              |
创建订单     记录决策（已拦截）
 |              |
经纪商提交   日志条目
 |
成交/拒单
 |
日志 + 通知
```

每个步骤均记录至交易日志，包括被拦截的交易，便于事后分析 Agent 的意图及拦截原因。`TradeExecutor`（`execution/executor.py`）是该流程的协调者，被单 Agent 模式、多 Agent 模式、daemon routine、Web Dashboard 共用。

---

## 调度器 / 守护进程

`cli.py:643-776` 的 `cmd_daemon` + `agent.py` 各 `run_*` 方法。守护进程是"自动运行"的入口 —— 生产部署中由 `docker compose` 拉起的 `stockagent-daemon` 容器跑此命令。

### 运行机制

- 单线程 `while True` 循环，每 30 秒醒来一次（`time.sleep(30)`）
- 每次 wake-up 取当前美东时间（按 `scheduler.timezone` 配置，默认 `US/Eastern`），逐条匹配触发条件
- `_fired` 字典做幂等键（`{routine_name → date}`），防止同一分钟多次 wake-up 导致重复触发
- `weekday >= 5 and not weekend_enabled` → 周末整循环休眠 1 小时不触发任何 routine
- Ctrl+C 时优雅 disconnect 退出，不会留下脏连接

**故障语义**：进程崩溃后 `_fired` 内存丢失，重启后若处于触发分钟可能重跑（一次以内）—— 但因为 `_fired` 用 date 作 value 跨日自动失效，无需手动清理。

### 五类定时任务

| 任务 | 默认触发时刻（ET / 北京）| 函数 | 工作内容 |
|------|------|------|------|
| **premarket** | 工作日 09:00 ET / 21:00 北京，每天一次 | `run_premarket` | ① broker 连接 → ② 加载持仓 ticker 列表 → ③ 对每只跑 12-Agent 完整分析 → ④ `risk.check_portfolio_health()` → ⑤ Notifier 发日报 |
| **intraday** | 工作日 09:30–16:00 ET 每 30 分钟 / 21:30–次日 04:00 北京，每天约 13 次 | `run_intraday` | ① `executor.check_stop_losses()` 命中即下卖单 + Telegram 警报 → ② `executor.check_take_profits()` 同上 → ③ 风控告警。**不调 LLM**，秒回 |
| **postmarket** | 工作日 16:30 ET / 次日 04:30 北京，每天一次 | `run_postmarket` | ① 再跑一遍 12-Agent 分析 → ② 当日交易复盘 + 7 日决策准确率 → ③ Notifier 收盘报告 → ④ 当日分析存入 research corpus → ⑤ `reflection_engine.reflect_batch(days=1)` 提炼经验写入长期记忆 |
| **screening** | 周日 20:00 ET / 周一 08:00 北京，每周一次（`cache_ttl_hours: 72` 二次门槛） | `run_screening_cycle` | sp500 全量两阶段筛选（基本面 + 评分），最多 50 个候选写入 `data/screening.db`，6 worker 并发 |
| **deep_research** | 周一 20:00 ET / 周二 08:00 北京，每周一次（`research_interval_hours: 168`） | `run_deep_research` | 对最多 5 只 ticker（未研究过的优先 + 持仓）跑完整 12-Agent TradingGraph，结果写入 research corpus；若 `auto_execute: true` 且 conviction ≥ 0.7 自动下单 |

### 关键开关

- `auto_execute: false`（默认）：所有 routine 哪怕给出 strong_buy/strong_sell 也**不会自动下单**，需要人工 `cli buy/sell` 或 Web Dashboard 操作
- `trade_cooldown_hours: 24` / `analysis_cooldown_min: 5`：throttle 控制，避免同一 ticker 短期内反复分析消耗 token
- `enable_auto_research` / `screening.enabled`：可独立关闭单个长任务，互不影响主交易回路

### 设计取舍

- **不是 cron**：是裸 while + sleep(30)，零外部依赖，能感知 throttle/cooldown；代价是分钟级精度（00:00–00:30 之间 wake 才会触发）
- **intraday 不调 LLM**：所以无论持仓多少都很快；只有止损/止盈阈值命中时才会真正下单
- **reflection 是异步学习闭环**：postmarket 提炼的经验写到 `data/memory.db`，下次 LLM 推理时被注入（每次约 2KB cap），形成"越用越懂你"的反馈回路

---

## 数据来源

| 来源 | 提供方 | 是否免费 | 数据内容 |
|------|--------|----------|----------|
| 行情数据 | yfinance | 是 | OHLCV、报价、公司信息 |
| 新闻 | Yahoo Finance RSS | 是 | 标题、基本元数据 |
| 基本面 | yfinance | 是 | 利润表、资产负债表、现金流量表 |
| 宏观指标 | yfinance | 是 | 指数、VIX、国债收益率、DXY、商品、板块 ETF |
| SEC 文件 | EDGAR API | 是 | 10-K、10-Q、8-K、Form 4 |
| 增强新闻 | Finnhub | 可选（需 API Key） | 公司新闻含正文 |
| 增强新闻 | NewsAPI | 可选（需 API Key） | 聚合新闻文章 |

宏观数据被 `MacroAnalyst` 在多 Agent 流水线中独立解读，并喂给后续辩论层作为系统性风险输入。

---

## 记忆系统

三层结构，各层用途不同。所有层均使用 SQLite，路径在 `config.yaml` 的 `memory:` 段配置（默认 `data/`）。

### 第一层：长期记忆（LongTermMemory）

**用途**：避免用户重复告知同样的偏好。

**存储**：`data/memory.db`。

**注入方式**：每次推理时，将全部记忆内容（上限约 2KB）注入上下文。

**分类**：
| 分类 | 示例 | 优先级 |
|------|------|--------|
| `user_preference` | "用户偏好分红股" | 7-8 |
| `correction` | "不要在 NVDA 下跌时卖出" | 9 |
| `strategy` | "始终用金融股对冲科技股" | 7 |
| `lesson` | "财报超预期后会在 3 天内回调" | 6 |
| `environment` | "IBKR 7497 端口是模拟盘" | 8 |

`reflection_engine` 在 postmarket 自动产出 `lesson` 类条目。

### 第二层：研究语料库（ResearchCorpus）

**用途**：提供按需查询的深度背景，避免信息过载。

**存储**：`data/research_corpus/`，SQLite FTS5 + 内容文件。

**使用方式**：Agent 分析特定 ticker 时查询语料库，结果以补充上下文形式提供，**不注入长期记忆**。`postmarket` / `deep_research` routine 会主动写入。

**文档类型**：研究报告、财报电话会议记录、SEC 文件、新闻文章、Agent 自动生成的分析。

### 第三层：交易日志（TradeJournal）

**用途**：机构记忆 —— 记录决策内容、原因及结果。

**存储**：`data/trade_journal.db`。

**核心设计**：每笔决策均附带完整的决策时快照（分析评分、技术指标、组合状态），支持事后分析：

```python
journal.get_decision_accuracy(days=30)
# → {"correct": 18, "total_evaluated": 25, "accuracy": 0.72}
```

被风控拦截的交易也会进 journal（标记为 blocked），便于复盘 Agent 的意图。

---

## 股票筛选系统

`screening/`（被 `agent.run_screening_cycle()` 调用）。两阶段管线：

1. **初筛**：从配置的 universe（默认 sp500）按基本面阈值过滤 —— 市值 ≥ $2B、PE ≤ 35、ROE ≥ 8%、负债权益比 ≤ 200%、营收增长 ≥ -10% 等
2. **打分**：通过初筛的标的按 `screening_score` 综合排序，返回前 N 名（默认 50）

并发：默认 6 worker 并行拉取基本面。结果缓存 72 小时（`cache_ttl_hours`），避免周内重跑。输出写 `data/screening.db`，可被 `deep_research` 作为候选池来源。

---

## 回测引擎

`backtest/` 提供历史回放与策略验证：

| 组件 | 文件 | 职责 |
|------|------|------|
| `BacktestEngine` | `engine.py` | 单 ticker 日级回放，主循环驱动 |
| `MultiTickerBacktestEngine` | `engine.py` | 多 ticker 共享资金的组合回测 |
| `BacktestBroker` | `broker.py` | 实现 `BaseBroker`，按历史价逐日成交 |
| `HistoricalDataManager` | `data_manager.py` | yfinance + CSV 缓存 |
| `PerformanceMetrics` | `metrics.py` | 14+ 指标：Sharpe / Sortino / 最大回撤 / 胜率 / Calmar / alpha / beta / 信息比率 / 跟踪误差 等 |
| `GridOptimizer` | `optimizer.py` | 笛卡尔参数网格搜索 |
| `WalkForwardOptimizer` | `optimizer.py` | 滚动训练/测试窗口，避免过拟合 |
| `MarketRegimeDetector` | `analysis/regime/` | 市场状态分类（牛/熊 × 高/低波动 + 震荡），动态调整信号权重和阈值 |

入口：`cli backtest --ticker AAPL --start 2023-01-01 --end 2024-01-01`，支持 `--benchmark`、`--regime`、`--walk-forward`、多 ticker 等。

---

## Web Dashboard

`web/server.py` 创建 FastAPI 应用 + Uvicorn 启动。前端为独立 React 项目（`web-frontend/`），构建产物输出到 `web/static/` 由 Nginx 反代。路由分组：

| 路由组 | 文件 | 功能 |
|--------|------|------|
| `/api/portfolio/*` | `routes/portfolio.py` | 账户、持仓、订单 |
| `/api/analysis/*` | `routes/analysis.py` | 触发分析、查询信号 |
| `/api/trading/*` | `routes/trading.py` | 下单、撤单 |
| `/api/journal/*` | `routes/journal.py` | 决策与交易历史 |
| `/api/screening/*` | `routes/screening.py` | 筛选结果与触发 |
| `/api/system/*` | `routes/system.py` | 系统状态、配置 |
| `/ws` | `routes/ws.py` | WebSocket 实时推送 |

Dashboard 共享 daemon 同一份 `agent` 实例 —— 在 Web 上点 "Analyze AAPL" 与 daemon premarket 跑同一条 12-Agent 流水线。

---

## 通知系统

`push/notifier.py` 的 `Notifier` 统一发送，配置 `push.channels` 决定下发渠道：

| 渠道 | 配置 | 用途 |
|------|------|------|
| `cli` | 无需额外配置 | 标准输出（容器日志） |
| `feishu` | `feishu_webhook` | 飞书/Lark webhook |
| `telegram` | `telegram_bot_token` + `telegram_chat_id`（生产建议从环境变量注入） | Telegram bot |

通知类型：`send_daily_report`（pre/postmarket 触发）、`send_trade_alert`（成交、止损、止盈）、`send_risk_alert`（风控告警）。多渠道并存时同一消息广播到所有启用渠道。

---

## 配置

层级结构：YAML 文件 → 环境变量 → 运行时默认值。

```python
config = AppConfig.from_yaml("config.yaml")
# 以 STOCKAGENT_ 为前缀的环境变量会覆盖 YAML 中的值
```

所有配置项均为带默认值的类型化数据类，零配置即可运行。生产部署提供三套预设：
- `config.yaml` — 模拟模式（默认）
- `config.production.yaml` — IBKR paper（搭配 `docker-compose.prod.yml`）
- `config.alpaca.production.yaml` — Alpaca paper（搭配 `docker-compose.alpaca.yml`）

---

## 依赖

| 包 | 用途 |
|----|------|
| `yfinance` | 行情数据、基本面、宏观指标 |
| `pandas` | 数据处理 |
| `pyyaml` | 配置解析 |
| `requests` | 新闻、SEC、Webhook 的 HTTP 请求 |
| `ta` | 技术分析指标 |
| `ib_insync` / `ib_async` | IBKR 集成（可选） |
| `alpaca-py` | Alpaca paper trading（可选） |
| `fastapi` / `uvicorn` | Web Dashboard（可选） |
| `openai` | LLM 客户端（OpenAI-Compat 协议，对接 Qwen / Ark / OpenAI） |
| `sqlite3` | 记忆系统（标准库） |
