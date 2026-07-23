# BoB

HackChat 多功能聊天机器人。AI 对话、小游戏、经济系统、代码生成——所有功能集成于一个 Python 进程，零外部数据库依赖。

## 功能概览

| 分类 | 命令 | 说明 |
|------|------|------|
| 经济 | `coins` `checkin` `rank` `transfer` `shop` `buy` `bag` `welcome` | 金币、签到、排行、转账、商店、背包、自定义欢迎词 |
| 信息 | `stats` `chatrank` `history` `search` `profile` `today` | 统计、排行、历史、搜索、AI 画像、每日总结 |
| 娱乐 | `fortune` `ad` `ads` `dig` `star` `quote` | 运势、广告、考古、金句收藏 |
| 游戏 | `wordle` `guess` `number` `idiom` `dice` `zjh` `uno` `crypto` | 8 款小游戏 |
| AI | `ai` `clearai` `code` | 对话、代码生成 |
| 其他 | `afk` `ping` `feedback` `help` `friend` `msg` | 暂离、测试、反馈、帮助、友链、留言 |
| 管理 | `addcoins` `resetgame` `say` `admin` | 发币、重置、代发、系统管理 |

> 命令前缀由 `BOT_PREFIX` 控制，默认无前缀。`help` 查看全部命令。

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env   # 填入密钥、房间、管理员
python main.py
```

## 架构

```
用户消息
  → Bot._on_message → _handle_chat
  → Context 构造 → Router.dispatch
  → 中间件链（统计记录 → AFK 检测 → 限流）
  → 命令处理器（commands/*.py）
  → 服务层（services/*.py）
  → 存储层（storage/db.py + kv.py → SQLite）
```

**核心设计：**

- **统一存储** — 所有数据存入一个 SQLite 库（WAL 模式 + 线程安全），不依赖外部数据库
- **依赖注入** — `App` 容器统一装配所有服务，杜绝循环引用
- **统一返回值** — 所有服务返回 `Result(success, message, data)`
- **游戏与金币解耦** — 游戏只返回逻辑结果，金币收支由命令层统一处理
- **多 Provider fallback** — AI 请求自动切换 Provider，失败不影响其他功能

## 目录结构

```
aibob/
├── main.py                # 入口
├── config.py              # 环境变量 → 配置对象
├── constants.py           # 常量、物品定义
├── core/                  # 框架层
│   ├── bot.py             # HackChat 协议处理
│   ├── connection.py      # WebSocket（自动重连 + 心跳）
│   ├── context.py         # 命令上下文
│   ├── router.py          # 命令路由 + 中间件
│   ├── health_monitor.py  # 健康监控
│   └── result.py          # 统一返回值
├── storage/               # 存储层
│   ├── db.py              # SQLite（WAL / 索引 / 线程安全）
│   └── kv.py              # KV 存储
├── services/              # 业务层
│   ├── app.py             # 依赖注入容器
│   ├── ai.py              # AI 对话（多 Provider + 并发控制）
│   ├── codeagent.py       # AI 代码生成
│   ├── economy.py         # 金币 / 签到 / 商店 / 背包
│   ├── history.py         # 聊天历史
│   ├── stats.py           # 统计
│   ├── quotes.py          # 金句
│   ├── digest.py          # 每日总结
│   ├── profile.py         # 用户画像
│   ├── fortune.py         # 运势
│   ├── ads.py             # 广告
│   ├── friends.py         # 友情链接
│   ├── messages.py        # 留言
│   ├── afk.py             # 暂离
│   └── api_server.py      # 内嵌 HTTP API Server
├── games/                 # 游戏层（纯逻辑）
├── commands/              # 命令层
├── utils/                 # 工具
└── data/                  # 数据文件
```

## 配置

所有配置通过环境变量（`.env` 文件）设置，参考 `.env.example`：

<details>
<summary>主要配置项</summary>

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BOT_NAME` | `BoB` | 机器人名称 |
| `BOT_ROOM` | `lounge` | 聊天室频道 |
| `BOT_PREFIX` | （空） | 命令前缀 |
| `BOT_ADMINS` | （空） | 管理员列表，格式 `nick:trip,nick:trip` |
| `DATABASE_PATH` | `data/aibob.db` | SQLite 路径 |
| `AI_PROVIDERS` | （空） | Provider 列表，如 `kilo,nvidia` |
| `API_ENABLED` | `0` | 启用 HTTP API Server |
| `API_PORT` | `8300` | API Server 端口 |
| `API_KEY` | （空） | API 鉴权密钥 |

</details>

## AI 能力

- **多 Provider fallback** — Kilo AI 主力 + NVIDIA NIM 保底，自动切换
- **函数调用** — AI 可查询金币、排行、统计、背包、运势、联网搜索等
- **代码生成** — `code <需求>` 通过 tool-calling 在 Supabase Storage 上创建项目
- **用户画像** — `profile` 基于聊天记录生成性格侧写
- **每日总结** — 每天 23:00 自动生成聊天日报

## 部署

### 本地运行

```bash
python main.py
```

### 服务器部署

设置环境变量 `API_ENABLED=1` 启用内嵌 HTTP API Server，绑定 `::` 和端口 `8300~8499`，随 Bot 进程启动。

### 前端

Web 前端为独立仓库，部署在 Vercel，通过 `/api/*` 代理调用 Bot API Server。

## 技术栈

- **Python 3.11+** — WebSocket + SQLite + 线程
- **websocket-client** — HackChat WebSocket 连接
- **openai** — AI 对话（兼容接口）
- **Pillow** — Wordle 图片渲染
- **psutil**（可选）— 性能监控

## License

MIT
