# 免费 MCP 服务（keyless）

本目录放可直接由仓库顶层 `mcp_pipe.py` 启动的 MCP 工具源码。全部工具**不需要 API key、不需要注册账号、不连付费后端**，只依赖标准库与 `mcp` / `requests`。

先说清边界：**Gitee 只是代码托管的唯一真源**，服务实际运行在 Windows 服务器上，由 `scripts/windows/pull_update.bat` 拉取更新后生效；Gitee 不运行任何进程。仓库里不含、也不应含 `MCP_ENDPOINT`。

## 链路定位：不接小智音箱硬件

这里说的 `xiaozhi` 只指**服务端项目**（xiaozhi-esp32-server），本项目不使用、也不需要小智音箱或任何 ESP32 硬件。它在链路里承担两件事：给 `voice-bridge` 提供 LLM 会话（`xiaozhi_ws` 适配器以软件虚拟设备接入服务端 WebSocket），以及给本目录的工具提供 `MCP_ENDPOINT`。

语音的入口与出口始终是**小爱音箱**：小爱 ASR → `voice-bridge` → xiaozhi 服务端（LLM + MCP 工具）→ 回答文本 → 小爱 TTS。所以不需要 OTA、不需要配网、不需要给硬件烧固件；`xiaozhi_ws` 的虚拟设备和服务端后台白名单都是纯软件配置。

## 为什么重写，而不是直接装官方包

官方 [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) 维护 7 个 reference servers：Everything、Fetch、Filesystem、Git、Memory、Sequential Thinking、Time，均开源免费（Apache-2.0 / MIT）。但套到这台服务器上有几个绕不开的问题：

| 约束 | 说明 |
|---|---|
| 启动方式不匹配 | `mcp_pipe.py` 固定执行 `python <单个脚本>`，官方包走 `npx -y ...` 或 `uvx ...`，接不进现有链路 |
| 工具链 | 会额外引入 Node.js 或 uv，而服务器目前是裸 Python |
| 官方定位 | 官方 README 明确写这些是教学参考实现，不是生产就绪，安全边界要自己补 |
| 权限面 | Filesystem / Git 带写权限；官方 Fetch 不拦截内网地址 |

所以这里对标它们的**能力**重写为单文件 stdio 服务，不是复制官方代码，也不需要联网拉包。

## 文件

| 文件 | 作用 |
|---|---|
| `free_tools.py` | 主服务，14 个本地工具，一次启动全部可用 |
| `fetch_lite.py` | 可选的受控网页抓取服务，独立进程 |
| `selftest.py` | 离线冒烟自检，用 MCP 客户端实际调用工具 |
| `start_mcp.bat` | Windows 启动器，处理好 venv 与 PATH |

顶层 `requirements.txt` 复用，不另建第二份依赖清单。

## 对标关系与工具清单

| 官方 reference server | 本仓库对应工具 | 外部密钥 |
|---|---|---|
| Time | `get_current_time`、`convert_time` | 无 |
| Everything（计算器部分） | `calculate`、`echo`、`random_int`、`random_choice`、`new_uuid` | 无 |
| Sequential Thinking | `sequential_thinking` | 无 |
| Memory | `remember`、`recall`、`forget`、`list_memories` | 无 |
| Fetch | `fetch_url`、`check_url`（`fetch_lite.py`） | 无 |
| Filesystem / Git | **未纳入**，见安全边界 | — |

`free_tools.py` 用 AST 白名单求值，不用 `eval`；`sequential_thinking` 只记步号与长度，不留存推理正文；记忆默认只存进程内存，不落盘。

## 依赖

```bash
pip install -r requirements.txt
```

顶层清单做了两处必要修正：

1. `mcp>=1.0.0,<2`。`mcp` 2.x 移除了 `mcp.server.fastmcp.FastMCP`（改名 `MCPServer`），无上界安装会拿到 2.x，导致本目录以及原有 `music.py` / `ximalaya.py` 全部 `ModuleNotFoundError`。
2. `tzdata`（仅 Windows）。Windows 没有系统时区库，`zoneinfo` 取 `Asia/Shanghai` 需要这个包。

## 启动

`MCP_ENDPOINT` 从 xiaozhi **服务端管理后台**取得（不是音箱配网页面），形如 `wss://.../mcp/?token=...`。它等同于一把钥匙，**不得写入仓库**；可放在环境变量、仓库根 `.env`（已被 `.gitignore` 忽略），或 nssm 的 `AppEnvironmentExtra`。

Linux / macOS：

```bash
export MCP_ENDPOINT='wss://你的xiaozhi服务端/mcp/?token=后台给出的token'
python mcp_pipe.py mcp_servers/free_tools.py
```

Windows：

```bat
set "MCP_ENDPOINT=wss://你的xiaozhi服务端/mcp/?token=后台给出的token"
mcp_servers\start_mcp.bat
mcp_servers\start_mcp.bat fetch_lite.py
```

**PATH 陷阱**：`mcp_pipe.py` 用字面量 `python` 启动子进程，而不是 `sys.executable`。如果系统 PATH 上的 `python` 不是装了 `mcp` 的那个解释器，子进程会直接导入失败。`start_mcp.bat` 已把 `.venv\Scripts` 放到 PATH 最前来解决；手动启动时也要先激活 venv。脚本还会 `pushd` 到仓库根，保证 `mcp_pipe.py` 里的 `load_dotenv()` 能读到 `.env`。

一个 `mcp_pipe.py` 进程对应 xiaozhi 服务端的一个 MCP endpoint。要同时用 `free_tools.py` 和 `fetch_lite.py`，需要两个进程 + 两个 endpoint，或者把工具合并进同一个脚本。语音场景一般只挂 `free_tools.py` 就够。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `MCP_ENDPOINT` | 无，必填 | xiaozhi 服务端提供的 WebSocket 地址，不入库 |
| `MCP_DISABLE_TOOLS` | 空 | 逗号分隔的工具名，注册时跳过，减少工具描述占用的上下文 |
| `MCP_MEMORY_FILE` | 空 | 设置后记忆才落盘到该路径；默认纯内存 |
| `MCP_FETCH_UA` | `FreeMCP-FetchLite/1.0` | `fetch_lite.py` 的 User-Agent |

14 个工具的描述会占用模型上下文。语音场景建议裁剪，例如：

```bat
set MCP_DISABLE_TOOLS=convert_time,text_stats,text_transform,random_int,random_choice,new_uuid
```

## 自检

```bash
python mcp_servers/selftest.py
```

不需要 `MCP_ENDPOINT`、不需要外网。它会以 stdio 启动两个服务，`tools/list` 列出全部工具，再逐个实际调用，并验证 `fetch_lite.py` 的内网拦截是否生效。全部通过打印 `=== PASS ===` 并返回 0。

联调时先看 xiaozhi 服务端 `tools/list` 是否出现 `get_current_time` 等工具，再对**小爱音箱**说「现在几点」，确认回答经 TTS 播回来；`echo` 可用于验证链路本身。整条链路上没有小智硬件参与。

## 安全边界

- **`fetch_lite.py` 拦什么**：仅 http/https、仅 80/443、拒绝 URL 内嵌凭据、解析 DNS 后逐个拒绝私有/回环/链路本地/保留/组播地址、不跟随重定向、响应体上限 1MB、返回上限 20000 字符、超时可控。
- **残留风险**：校验与真正发起请求之间存在 DNS rebinding 窗口；本实现不做出口防火墙。若服务器能访问敏感内网，应在网络层限制出口，而不是只依赖脚本校验。
- 不自动检查 `robots.txt`，使用前自行遵守目标站点条款。
- **未纳入 Filesystem / Git**：它们带写权限，白名单配错就能改服务器文件；需要时单独评估后再加。
- **未纳入「免费额度但需 key」的第三方服务**（天气、地图、搜索等）：那类服务要申请密钥并常驻配置，和 keyless 目标不符。真要用，密钥放 `.env`，不要写进本仓库。
- **stdout 不能被污染**：`mcp_pipe.py` 把子进程 stdout 当作 JSON-RPC 帧转发，任何 `print` 都会让 xiaozhi 服务端解析失败。两个服务端脚本的日志一律走 stderr，改代码时保持这条。
- 记忆工具不要写账号、口令、设备 ID 或对话原文；默认不落盘，`mcp_servers/data/` 已加入 `.gitignore` 作为防御。
