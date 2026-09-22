# ⚡ QwenPaw 事件任务(Event Trigger)

[English](./README.en.md) | 中文

条件驱动的事件任务插件——**QwenPaw 定时任务(cron)的事件驱动孪生**。

> 定时任务回答"**什么时候**做";事件任务回答"**发生了什么**就做"。

QwenPaw 的自动化此前只有时间维度(cron / heartbeat)。"英伟达涨破 250 就分析行情""服务挂了立刻通知""日志出现 ERROR 就排查"——这类**条件触发**需求只能靠外部脚本 + 通知渠道拼凑。本插件把"轮询检查 → 条件判定 → 触发动作"做成与定时任务同级的正式能力。

- 官方 issue 讨论:[#338 建议添加 webhook 功能](https://github.com/agentscope-ai/QwenPaw/issues/338)(2026-03 提出至今)、[#7657 ntfy 频道提案](https://github.com/agentscope-ai/QwenPaw/issues/7657)
- 本插件同时提供 REST 管理接口与配套 agent 技能,人类与 agent 都能创建任务

## 特性

- 🔁 **双入口**:控制台 UI(侧边栏"事件任务")+ agent 对话创建(配套 `event-tasks` 技能,中英双语)
- 🗂 **per-agent 隔离(v0.3,对齐 cron)**:任务/脚本/运行记录存于各 agent 工作区(`workspace_dir/event_trigger/`),API 按 `/api/events/{agent_id}/` 分发——互不可见、互不干扰,重装/演化不再互相覆盖
- 🧩 **内置 agent 技能,开箱即用**:安装即注入 `event-tasks` 技能(中英双语)——它就是写给 agent 的说明书(协议/模板/参数演化/常见坑),agent 读完即可代写脚本、创建与管理任务,人类无需读文档
- 🛡 **启用即注册**:创建仅校验;**启用时**语法检查 → 试跑(真实执行一次,初始化状态)→ hash 锚定;禁用=注销;运行中改脚本会拒跑,禁用→启用即恢复
- ✍️ **脚本在线编辑(v0.3.2)**:路径模式退役,所有脚本统一托管于工作区 `event_trigger/scripts/`;任务列表一键查看/编辑(平台 file-content API,ETag 防并发),保存后引导重新校验(禁用→启用)完成重锚定;也支持"空脚本创建"与"上传 .py"
- ⚙️ **脚本内 CONFIG 参数化**:脚本顶部 `CONFIG = {...}` 声明参数(ast 安全解析,绝不执行),UI 自动生成参数表单;改参数=重新注册,配置与代码单文件自包含
- 🔢 **max_triggers**:触发 N 次自动禁用(0=无限),重新启用时计数清零——"触发一次即完成"的单发哨兵
- 🌊 **防抖**:规则级冷却 + 脚本级滞回(armed 状态由脚本维护,引擎只负责存取与重置),持续型条件不打风暴
- 🎯 **两种动作**:`notify`(纯通知,零 token)/ `agent`(**进程内注入推理**——与 cron 同走 `stream_query`,无 HTTP/SSE 开销)
- 📡 **分发模式**:`stream`(逐事件实时转发)/ `final`(仅完整结果);支持静默投递
- 🌍 **中英双语**:UI(跟随控制台语言)/ agent 技能 / 模板元信息
- 📦 **五个内置模板**:股价双边界监控(NVDA via Yahoo,上/下界滞回)/ HTTP 探测 / 文件变化 / 端口存活 / 日志关键字(增量扫描)
- 🔒 **安全设计**:注册制(不扫描文件夹)+ hash 完整性锁 + 资源护栏(超时 / 64KB 输出上限 / 间隔下限)+ 审计日志

## 安装

```bash
qwenpaw plugin install /path/to/qwenpaw-event-trigger
```

或从插件市场安装(待上架)。安装后:

- 控制台侧边栏出现"**⚡ 事件任务**"
- 工作区自动装入 `event-tasks` 技能(agent 双语)
- 数据目录:`~/.qwenpaw/event_trigger/`(卸载插件不删除数据)

## 快速开始

### 控制台

1. 侧边栏 → **事件任务** → **+ 创建任务**
2. 检查器 → 从模板 → "股价阈值监控(滞回)",改参数(默认 NVDA / 阈值 200)
3. 任务类型 → Agent 推理;目标频道/用户/会话从下拉选择(与定时任务同款)
4. 保存(自动校验)→ 打开启用开关

### Agent 对话创建

> "帮我盯着英伟达,涨破 250 就分析一下行情并提醒我"

agent 会凭 `event-tasks` 技能:设计滞回检查脚本 → `POST /api/events/` 注册 → `run` 验证一次 → `enable` 启用。

## 检查脚本协议

```text
IN : env EVENT_STATE(上次持久化状态 JSON,首次 "{}")、EVENT_RULE_ID、EVENT_RULE_NAME
OUT: stdout 一行 JSON:
     {"triggered": bool,            必填
      "title": str,                 可选,通知标题
      "event": str,                 可选,正文(notify 即通知内容;agent 任务填入 prompt)
      "cooldown": int,              可选,覆盖规则冷却
      "state": {...}}               可选,引擎持久化并在下次回传(滞回用)
退出码:0 = 正常;非 0 = 错误(记录、不触发)
限制:stdout ≤ 64KB;脚本超时默认 60s;间隔 ≥ 10s
```

滞回标准写法(直接抄):

```python
#!/usr/bin/env python3
import json, os
st = json.loads(os.environ.get("EVENT_STATE") or "{}")
armed = bool(st.get("armed", True))
# ... 检查逻辑 -> should_fire / reset_condition ...
if armed and should_fire:
    print(json.dumps({"triggered": True, "title": "...", "event": "...", "state": {"armed": False}}, ensure_ascii=False))
else:
    print(json.dumps({"triggered": False, "state": {"armed": armed or reset_condition}}, ensure_ascii=False))
```

完整协议:`GET /api/events/protocol`;现成模板:`GET /api/events/templates`。

## 触发-演化循环(核心模式)

条件会演化的监控(以行情为例):

```text
规则(UP=100, DOWN=90, max_triggers=1) → 涨破 100 → 🔥 触发 + 自动禁用(旧条件失效,防空转)
  → agent 推理:"进入观望期 105-120" → PUT 更新 CONFIG + enable(计数清零)
  → 新一轮:涨破 120 或跌破 105 → 再触发 → 再演化……
  → 人类随时可在 UI 参数表单改 CONFIG,与 agent 走同一接口
```

三层决策权分离:**脚本管"聪明"**(armed 滞回、复位规则,由脚本定义),**配置管"边界"**(max_triggers/超时/冷却),**引擎管"记账"**(state 存取、重置、调度)——引擎不解释脚本的状态语义,只负责存取与按轮次重置。

## 架构

```
skills/event-tasks → agent 对话创建 ─┐
控制台 UI(web/index.js)──────────┤→ REST /api/events/*
                                     ↓
   manager(注册关卡:语法→试跑→hash)→ engine(每规则 asyncio 循环)
                                     ↓
   checker.py(subprocess + EVENT_STATE → stdout JSON,hash 校验/资源护栏)
                                     ↓ 触发
   injector(进程内 stream_query + 记忆隔离语义,与 cron executor 同构)
                                     ↓
   channel_manager.send_event / send_text → console / ntfy / 钉钉 …
```

- **数据**:`~/.qwenpaw/event_trigger/`(`events.json` 注册表 + `runs.jsonl` 运行日志 + `audit.jsonl` 审计)
- **注入路径**:workspace_registry → workspace.stream_query(cron executor 同款,进程内直调)

## 与定时任务(cron)对照

| | cron | 事件任务 |
|---|---|---|
| 触发 | 时间表达式 / 日程 | 轮询检查脚本 → 条件 |
| 任务类型 | text / agent | notify / agent |
| 防抖 | — | 冷却 + 滞回 state |
| 投递 / 会话 / 收件箱 / 超时 / 静默 / 工具安全 | ✅ | ✅(同款语义同款默认值) |
| UI / CLI / 对话创建 | UI + CLI + 对话 | UI + 对话(REST) |

## 安全模型

- **威胁模型**:脚本是本机信任域内的代码(等同用户自己写 crontab),引擎不做沙箱表演;防的是"野脚本误运行"和"未走流程的变更"
- **注册制**:引擎只执行 `events.json` 注册表内的脚本,不扫描文件夹
- **hash 锁**:注册时记录 SHA256,每次执行前重验;脚本被改动 → 拒跑并标记,重新保存(重新校验)后恢复
- **资源护栏**:超时强杀、stdout 上限、间隔下限
- **审计**:注册/变更/启停/删除全部进 `audit.jsonl`,事后可追责
- **提示**:脚本以你的身份运行;从社区获取的模板请先读源码(上架市场的模板会经过平台扫描)

## FAQ

**Q:`armed` 状态是谁维护的?**
脚本定义语义(何时置 true/false),引擎只负责三件事:运行前通过 `EVENT_STATE` 传回、运行后持久化脚本输出的新值、重新注册(创建/保存/启用)时清空进入新轮次。

**Q:任务数据存在哪?**
v0.3 起按 agent 隔离:每个 agent 工作区的 `event_trigger/` 目录(events.json + scripts + runs/audit)。v0.2 的全局数据会在启动时自动迁移到各工作区(旧文件归档为 `events.json.pre-migrate`)。

**Q:删除任务,脚本文件会删吗?**
会。删除任务时同步删除引擎托管的脚本文件(确认窗有提示,不可恢复);启动时还会 GC 清理孤儿脚本。引用路径模式的外部脚本不受影响。

**Q:为什么修改脚本后任务报错不跑了?**
hash 完整性锁:内容变更后必须重新保存(走一遍注册关卡)。这是防止"注册后被静默替换"的核心机制。

**Q:一次性事件(只触发一次)怎么写?**
不要把一次性标志放脚本 `state` 里——注册试跑会真实执行一次把它消耗掉。把一次性判断放在事件源本身(如"目标文件是否已存在")。

**Q:目标用户ID 是 agent 吗?**
不是。它是**所选频道里的收件人标识**:console 频道是控制台用户(单用户部署恒为 `default`),ntfy 频道是 topic。agent 维度由任务的 `agent_id` 决定,两者正交。真正"发到哪"由频道的投递实现决定(如 ntfy 走插件的 push topics 配置)。

**Q:为什么技能装在工作区而不是技能池?**
技能池是内置技能包专属(平台版本管理);插件技能的官方形态是 `register_skill_provider` → workspace 级,随插件安装/卸载自动增删。

## Roadmap

- [ ] 上架官方插件市场
- [ ] CLI 客户端(`qwenpaw-event` 独立 pip 包,封装 REST——插件系统暂无 CLI 扩展点,cron 的 CLI 是内核内置子命令)
- [ ] 执行模型选择(cron 同款)
- [ ] webhook 型事件源(统一纳入管理)
- [ ] 收件箱集成(代码已就绪,待平台收件箱前端支持第三方来源后启用)
- [ ] 运行记录的持久化查询优化

## License

[Apache 2.0](./LICENSE)
