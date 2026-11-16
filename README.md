# 小爱全量监听 → 中转桥 → 小智调度

不用唤醒前缀、不用 ESP32、不开放任何入站端口：小爱说的每一句话都进大模型判断，
该小爱自己干的就让它自己干，该大模型答的就用 TTS 念出来。

这里的「小智」指的是**服务端项目**（xiaozhi-esp32-server），只用它的 LLM 会话与 MCP
工具编排能力，**不接入小智音箱或任何 ESP32 硬件**。语音入口与出口始终是小爱音箱；
`xiaozhi_ws` 是软件实现的虚拟设备，不是真实设备配网。

---

## 一、架构

```
        说话
用户 ──────────▶ 小爱音箱（原生 NLU 已经执行：开灯 / 放歌 / 闹钟）
                     │
                     │ ①小米云 ASR 文本 + 原生回答
                     ▼
            xiaoai_bot.py（常驻，1 秒轮询云端对话记录，被动旁听）
                     │ ②POST {"query","session_id"}
                     ▼
            xiao_bridge :8100（FastAPI 中转桥）
                     │
        ┌────────────┴─────────────┐
        │ ③规则快筛（0ms）          │ ④否则交给上游
        │ 明确是设备控制→native     │    xiaozhi_ws（虚拟设备，吃 MCP/记忆）
        │                          │    → 挂了就降级 newapi（保证有话可答）
        ▼                          ▼
   ⑤{"type":"native_cmd"}   {"type":"tts_reply","content":"..."}
        │                          │
        │ ⑥什么都不做               │ ⑦先让小爱闭嘴，再 text_to_speech 分段播报
        ▼                          ▼
   小爱原生结果保留            小爱念出大模型的回答
```

- **`bot/`**：只干"听"和"念"。不判断、不理解，纯转发 + 分发。
- **`bridge/`**：意图闸门 + 协议适配 + 降级 + 可观测。判定逻辑都在这，方便调。
- **xiaozhi / NewAPI**：大模型与工具能力，跑在原有位置，不动。

读云端对话是被动行为：`native_cmd` 分支唯一正确的动作就是什么都不做。

---

## 二、目录

```
voice-bridge/
├── docker-compose.yml          两个容器，host 网络，只监听本机回环
├── .env.example                → 复制成 .env
├── bridge/                     中转桥（FastAPI）
│   ├── app/main.py             路由、降级链、判定元数据日志
│   ├── app/intent.py           契约解析 + 规则快筛 + 疑问句护栏 + TTS 清洗
│   ├── app/adapters/           xiaozhi_ws（虚拟设备）/ xiaozhi_http / newapi
│   └── tests/                  35 个用例，含一个假 xiaozhi 服务器
├── bot/
│   ├── xiaoai_bot.py           小爱侧常驻进程（miservice 直连）
│   └── tests/                  9 个用例，不需要真音箱
├── prompts/
│   ├── xiaozhi_system_prompt.txt  贴到 xiaozhi 的 system prompt
│   └── native_keywords.txt        规则快筛白名单（正则）
├── config/xiaogpt.yaml.example    小爱账号 + 桥参数
└── scripts/
    ├── sync_gitee.sh          服务器唯一入口：常驻轮询 Gitee（自带定时，不用 cron）
    └── demo.py                灌一批句子验证判定，不发声
```

---

## 三、部署

### 1. 代码进 Gitee

```bash
cd <部署目录> && git clone <你的仓库地址> && cd voice-bridge
cp .env.example .env && cp config/xiaogpt.yaml.example config/xiaogpt.yaml
vim .env                 # 填 NEWAPI_KEY、XIAOZHI_WS_URL
vim config/xiaogpt.yaml  # 填小米账号密码、hardware 型号
```

`.env` 和 `config/xiaogpt.yaml` 都在 `.gitignore` 里，别提交。

### 2. 登录小米云

```bash
docker compose run --rm xiaoai python xiaoai_bot.py --check
```

看到 `设备型号: ... ｜连接正常` 就对了。提示要验证码就去小米账号安全中心过一下，
token 落在 `xiaogpt_root` 卷，之后重启不用再登。

> `hardware` 型号在音箱底部标签上（LX06/L05B/LX01…）；填错时报错会列出账号下所有设备型号。

### 3. 起服务

```bash
docker compose up -d --build
docker compose ps
curl -s http://<服务地址>:8100/healthz
```

### 4. 把提示词贴进 xiaozhi

`prompts/xiaozhi_system_prompt.txt` 整段复制，放到 xiaozhi 的 system prompt
（`config.yaml` 的 prompt 段，或管理后台的智能体设定）：

- 严格输出 `{"type":"native_cmd"|"tts_reply","content":"..."}`
- 拿不准就选 `tts_reply`
- `tts_reply` 的内容要能直接朗读（无 markdown/URL，120 字内）

不贴也能跑，桥会把纯文本一律当 `tts_reply`，代价是开灯这类指令也会被念一遍。

### 5. 放行虚拟设备

桥以"设备"身份连 xiaozhi（`XIAOZHI_DEVICE_ID=voice-bridge-01`）。
xiaozhi 开了设备鉴权就把这个 device-id 加进白名单；只监听本机回环时关鉴权也可以。

### 6. 验证判定（不发声）

```bash
python3 scripts/demo.py
```

| 句子 | 期望 | 耗时 | reason |
|---|---|---|---|
| 开灯 | native_cmd | 0ms | fastpath |
| 滨湖这边有哪些新楼盘 | tts_reply | 2140ms | llm:json |

### 7. 真机试三句话

| 你说 | 应该有 |
|---|---|
| 小爱同学，开灯 | 灯亮，没有任何多余播报 |
| 小爱同学，播放晴天 | 原生播放，VIP 音质正常，没有"正在问…" |
| 小爱同学，滨湖这边有哪些新楼盘 | 小爱先回一句原生话术，紧接着念出大模型答案 |

第三句的原生话术改不掉（它先于本链路执行）。嫌吵就把 `mute_before_tts` 保持 true、
`pre_tts_delay` 调到 0.4~0.8 之间。

### 8. 定时同步（服务器上只放一个脚本）

`scripts/sync_gitee.sh` 自带轮询，不用 crontab，也不用第二个脚本：

```bash
chmod +x scripts/sync_gitee.sh
sudo ./scripts/sync_gitee.sh --install     # 生成 systemd 单元并 enable --now
systemctl status voice-bridge-sync
```

`--install` 幂等，重复执行同名覆盖单元文件，不产生副本。没有 systemd 或不想用 root 时，
用一行开机自启代替：`@reboot <部署目录>/scripts/sync_gitee.sh`（写进 `crontab -e`）。

| 命令 | 用途 |
|---|---|
| `./sync_gitee.sh` | 常驻轮询，默认每 300 秒一轮，启动即先跑一轮 |
| `./sync_gitee.sh --once` | 只跑一轮，退出码即本轮结果（排障/手动触发） |
| `./sync_gitee.sh --install` | 生成并启用 systemd 单元，崩溃自动重启 |
| `DRY_RUN=1 ./sync_gitee.sh --once` | 只验证 git 拉取与更新检测，不碰容器 |

每轮动作：`flock` 防重叠 → `fetch + reset --hard` → 无更新跳过重建 → 有更新才
`build + up -d` → 轮询 `/healthz` 20 秒。服务意外停了但代码没变时也会把容器拉起。
任一轮失败只记日志并等下一轮重试，**不会拖死守护进程**；`--once` 模式仍返回非 0 退出码。

可调环境变量：`SYNC_INTERVAL`（默认 300）、`BRANCH`（默认自动探测当前分支）、
`HEALTH_URL`（默认 `http://127.0.0.1:8100/healthz`）、`REPO_DIR`、`LOG_FILE`。
日志在 `logs/sync.log`，超过 5 MB 自动截断；只记结论与提交短哈希，
不记远端地址、凭据、本机路径与用户数据。

改完代码 `git push`，5 分钟内服务器自己更新；`tail -f logs/sync.log` 看结果。

---

## 四、判定逻辑

判定一律偏向 `tts_reply`：该答不答是事故，多念一段只是啰嗦。

1. **规则快筛**（`native_keywords.txt`）：只放"没有第二种解释"的句式——开灯关灯、
   音量、暂停/下一首、闹钟、空调开关。命中就直接 native，0 毫秒、0 token。
   带歌名的播放句不进快筛（"播放晴天这首歌是谁唱的"会误伤），交给模型判。
2. **疑问句护栏**：出现 什么/哪些/怎么/多少/谁/介绍/推荐/写/设计/查询…
   即使模型返回 native_cmd 也强制改判 tts_reply，并换支持强制作答的适配器二次判定；
   仍拿不到答案才用兜底话术。
3. **契约解析**：xiaozhi 会把答案按句切段，`{` `}` `"` 可能被 TTS 预处理吃掉，
   `parse_contract()` 走三级降级：严格 JSON → `raw_decode` 抠对象 → 宽松正则。

---

## 五、调参与排障

| 现象 | 先看哪里 | 怎么办 |
|---|---|---|
| 开灯也被念了一遍 | `logs/bridge.jsonl` 的 `reason` | 是 `llm:json` 就往 system prompt 的 native 列表补这句话的说法 |
| 提问没反应 | 同上 | 是 `fastpath` 就收窄 `native_keywords.txt` 里那条正则 |
| 每次都很慢（>6s） | `meta.ms` | 换 `NEWAPI_MODEL`；或调小 `XIAOZHI_WS_TIMEOUT` 早点降级 |
| 播报被截断 | 回答字数与 `tts_chunk` | 调小 `tts_chunk`（默认 80 字） |
| 桥日志报 `xiaozhi_ws 调用失败` | `docker logs voice-bridge` + xiaozhi 日志 | 检查 device-id 白名单，及 `XIAOZHI_WS_URL` 是否以 `/xiaozhi/v1/` 结尾 |
| 一直"桥不可用" | `docker compose ps` | bot 会保持不干预，小爱原样可用 |

日志默认只落判定元数据（`type` / `reason` / `ms` / `adapter` / 文本长度），
不落用户语音原文与回答正文。逐句排障时把 `.env` 的 `LOG_TEXT` 设为 true，
用完改回 false 并清空 `logs/bridge.jsonl`。

```bash
tail -200 logs/bridge.jsonl | jq -r '.type' | sort | uniq -c
tail -200 logs/bridge.jsonl | jq -r 'select(.reason | startswith("guard")) | .q_len'
```

---

## 六、边界

1. 每条对话多 1 秒轮询 + 1~3 秒模型；native 指令不受影响，那时小爱已执行完。
2. 小爱会先说一句原生话术，这个重叠去不掉。
3. `xiaozhi_ws` 的文本注入帧按 v1 协议写，不同版本对 `listen` 帧的 `text` 支持不同；
   改 `.env` 的 `XIAOZHI_TEXT_FRAME` 即可适配。起不来时打开 `LOG_TEXT` 看 `meta.raw_head`。
4. 只能 mi TTS；`edge/openai` 需要 tetos 链路，没接。
5. 多轮上下文默认关（`HISTORY_TURNS=0`）；要接追问设成 2~3，代价是 token 和串味。
6. MCP 的注册与工具描述在 xiaozhi 服务端配，这里只送文本、捞答案。

---

## 七、本地自测

```bash
cd bridge && pip install -r requirements.txt && pytest -q      # 35 passed
cd bot && pip install -r requirements.txt && pytest -q         # 9 passed
```

`bridge/tests/mock_xiaozhi.py` 是会说 v1 协议的假服务器，单独跑起来可联调：
`python -m tests.mock_xiaozhi`，然后
`ADAPTER_CHAIN=xiaozhi_ws XIAOZHI_WS_URL=ws://<服务地址>:8765/xiaozhi/v1/ uvicorn app.main:app --port 8100`。

---

## 八、Windows 部署（无 Docker，服务器跑 NewAPI 的同一台机器）

服务器上不需要 Docker、不需要 ESP32、不开放任何入站端口。三个前提：**Git for Windows**、**Python 3.10+**、**nssm**（注册系统服务，避免黑窗口）。

### 1. 拉代码

```powershell
git config --global core.autocrlf input
git clone -b main https://<Gitee用户名>:<私人令牌>@gitee.com/ninxu/xiaozhidu.git D:\ai-mcp\xiaozhidu
cd D:\ai-mcp\xiaozhidu
```

私有仓的 HTTPS 免密格式必须是 `用户名:令牌`，只写令牌不行。`.env` 与 `config\xiaogpt.yaml` 在 `.gitignore` 里，**永远不提交**。

> 本仓库由 `xiaozhidu` 改造而来：顶层原有的 `mcp_pipe.py`、`music.py`、`ximalaya.py`、`requirements.txt` 与 `.github/workflows/` 全部保留，原说明归档为 `README_xiaozhidu.md`。新链路代码在 `bridge/`、`bot/`、`scripts/`。
>
> 注意：`.github/workflows/` 只在 GitHub Actions 侧执行，本仓库托管在 Gitee 时这些定时任务不会运行；`music.py` / `ximalaya.py` 需要手动启动或另行配置调度。

### 2. 一次性初始化（管理员 PowerShell）

```powershell
cd D:\ai-mcp\xiaozhidu
.\scripts\windows\install_services.bat
```

脚本做四件事：建 `.venv` 并装三套依赖（`bridge/`、`bot/` 与顶层 `requirements.txt`，后者含 `mcp` 与 Windows 的 `tzdata`）→ 从 example 复制 `.env` 与 `config/xiaogpt.yaml` → 用 nssm 注册 `VbBridge`（桥）与 `VbXiaoai`（小爱旁听，依赖前者）→ 打印后续步骤。**它不会替你填任何密钥。** 免费 MCP 工具的启动与自检见 `mcp_servers/README.md`。

### 3. 填三处配置

| 文件 | 填什么 |
|---|---|
| `.env` | `NEWAPI_KEY`；`XIAOZHI_WS_URL=ws://127.0.0.1:8000/xiaozhi/v1/`（**必须自己带 `/xiaozhi/v1/`**） |
| `config/xiaogpt.yaml` | 小米账号、密码、`hardware`（音箱底部标签，如 LX06） |
| xiaozhi 后台 | 贴 `prompts/xiaozhi_system_prompt.txt` 进 system prompt；开了设备鉴权就把 `voice-bridge-01` 加白名单 |

路径不用手填：`config.py` 按自身位置自动定位 `prompts/` 与 `logs/`，Docker 模式才由 `BRIDGE_ROOT=/app` 覆盖。

### 4. 验登录并启动

```powershell
.\.venv\Scripts\python.exe .\bot\xiaoai_bot.py --check --config .\config\xiaogpt.yaml
nssm start VbBridge
nssm start VbXiaoai
curl.exe http://127.0.0.1:8100/healthz
python .\scripts\demo.py
```

`--check` 出现「设备型号 … 连接正常」即可；要验证码就去小米账号安全中心过一下，token 落在用户目录的 `.mi.token`，重启不用再登。健康检查**只能本机跑**（服务只绑 `127.0.0.1`）。

### 5. 定时拉 Gitee（拉模式，不开 SSH 入站）

任务计划程序新建任务：触发器每 30 或 60 分钟；操作为启动程序 `D:\ai-mcp\xiaozhidu\scripts\windows\pull_update.bat`，可带参数 `main`；**勾选「使用最高权限」**（`net stop/start` 需要管理员）。

`pull_update.bat` 每轮：`git fetch` → 比对 `HEAD` 与 `origin/main` → 无更新跳过重启 → 有更新才 `reset --hard` 并重启两个服务。用 `fetch + reset` 而不是 `git pull`，避免服务器本地改动卡死；git 的 stderr 全部丢弃，带令牌的远端地址不会进 `logs\pull.log`；日志只记结论与提交短哈希。

改完代码 `git push`，到点服务器自己更新。手动验一轮：右键「运行」，看 `logs\pull.log`。

### 6. 与旧方案的映射

| 旧方案文件 | 这里的落点 |
|---|---|
| `callback.py`（xiaogpt 回调） | `bot/xiaoai_bot.py` + `bridge/`（不依赖 xiaogpt，`miservice` 直连轮询） |
| `mcp_server/` | 仓库顶层原有的 `mcp_pipe.py` / `music.py` / `ximalaya.py` |
| `config/xiaogpt.toml` | `config/xiaogpt.yaml.example` |
| `pull_update.bat` | `scripts/windows/pull_update.bat` |

**MCP 不是丢目录自动加载**：xiaozhi 服务端要配 MCP endpoint 与工具描述，`mcp_pipe.py` 是连 endpoint 的管道。原有脚本保持原路径不动，workflows 里的引用不会断。

### 7. Windows 与 Linux 的差异

| 项 | Windows | Linux |
|---|---|---|
| 常驻 | nssm → `VbBridge` / `VbXiaoai` | `scripts/sync_gitee.sh --install`（systemd） |
| 定时 | 任务计划程序 + `pull_update.bat` | 同一脚本常驻轮询 |
| 路径 | `D:\...`，代码自动定位 | `/opt/...`，代码自动定位 |
| 换行 | `core.autocrlf input` | 默认 LF |

`scripts/sync_gitee.sh` 仍保留，供有 Docker 的 Linux 服务器使用；Windows 不用它。
