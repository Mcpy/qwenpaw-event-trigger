---
name: event-tasks
description: 仅当需要"条件触发"时使用——外部事件发生(价格突破阈值、文件被修改、HTTP 服务异常、端口不可达、日志出现关键字等)时自动触发推理或通知。/ Use ONLY for condition-triggered automation — when an external event occurs (price crosses a threshold, file modified, HTTP service down, port unreachable, keyword in logs) and you want to fire reasoning or a notification automatically. Managed via the /api/events/ REST API — also read this skill before updating a task's CONFIG params or enable/disable. For time-based schedules use the cron skill instead. / 通过 /api/events/ REST 管理;更新任务 CONFIG 参数或启停任务前也应阅读本技能。定时/周期需求请改用 cron skill。
metadata:
  builtin_skill_version: "1.0"
  qwenpaw:
    emoji: "⚡"
---

# 事件任务管理(条件触发) / Event Task Management (condition-triggered)

事件任务 = **条件驱动**(事件发生才触发);定时任务 cron = **时间驱动**(到点就跑)。
Event task = **condition-driven** (fires when something happens); cron = **time-driven** (fires on schedule).

## 什么时候用 / When to use

**应该使用 / Use when**
- 用户说"当/如果 X 发生时,做 Y":英伟达涨破某价、文件被改、服务挂了、日志出现 ERROR
- User says "when/if X happens, do Y": NVDA crosses a price, file modified, service down, ERROR in logs
- 需要事件风暴防护(冷却/滞回) / event-storm protection needed (cooldown/hysteresis)

**不应使用 / Do NOT use**
- "每天 9 点 / 每小时" → 用 **cron** / "daily at 9am" → use **cron**
- 只是现在立即做一次 → 直接执行 / one-off right now → just do it
- 触发条件说不清 → 先问用户 / condition unclear → ask first

**与 cron 组合 / With cron**: cron 定期巡检 + 事件任务异动响应,可并存。/ cron for periodic checkups + event tasks for breakout alerts; they coexist.

## 管理 API / Management API

基础地址 / Base: `http://127.0.0.1:8088`(本机免认证 / no auth on localhost);远程 / remote: `Authorization: Bearer <token>`。

```
GET    /api/events/                 列出任务 / list tasks
POST   /api/events/                 创建(自动走注册关卡)/ create (runs registration gate)
PUT    /api/events/{id}             更新(脚本变更重新校验)/ update (re-validates)
DELETE /api/events/{id}             删除 / delete
POST   /api/events/{id}/enable      启用 / enable
POST   /api/events/{id}/disable     禁用 / disable
POST   /api/events/{id}/run         立即检查一次 / one manual check now
GET    /api/events/{id}/runs        运行记录 / run history
GET    /api/events/protocol         脚本协议全文 / full checker protocol
GET    /api/events/templates        内置模板 / bundled templates
```

## 创建任务 / Create a task

`POST /api/events/`,JSON 体 / body:

```json
{
  "name": "任务名称 / task name",
  "agent_id": "<your agent_id, matching Agent Identity>",
  "interval_seconds": 60,
  "script_content": "<checker script (python)>",
  "action": "agent",
  "prompt_template": "Event fired: [{title}] {event}",
  "channel": "console",
  "user_id": "default",
  "session_id": null,
  "cooldown_seconds": 600,
  "enabled": false
}
```

- `script_path` 可代替 `script_content`(推荐内联,引擎统一落盘)/ `script_path` alternative (prefer inline)
- `action`:`notify`(只通知不推理,零 token)/ `agent`(触发推理)
- `interval_seconds` ≥ 10;`cooldown_seconds` 防事件风暴,脚本输出 `cooldown` 可按次覆盖
- `session_id` 留空 = 独立累积会话(推荐)/ empty = dedicated accumulating session (recommended)
- `enabled` 默认 false,创建后 `POST /{id}/enable` 启用 / created disabled, enable afterwards

## 检查脚本协议(核心)/ Checker-script protocol (core)

**IN**:env `EVENT_STATE`(上次状态 JSON,首次 `{}` / last persisted state)、`EVENT_RULE_ID`、`EVENT_RULE_NAME`。
**OUT**:stdout 一行 JSON / one JSON line:

```json
{"triggered": true, "title": "标题", "event": "正文(body)", "state": {"armed": false}}
```

- `triggered` 必须布尔 / boolean required;`state` 被引擎持久化并在下次通过 `EVENT_STATE` 回传 / persisted and fed back
- 退出码非 0 = 错误(记录不触发)/ non-zero = error (logged, never fires);stdout ≤ 64KB

### 参数声明(CONFIG)/ Parameters (CONFIG block)

脚本顶部声明一个字面量 dict 即为参数(引擎 ast 解析,不执行;UI 自动生成参数表单):

```python
CONFIG = {
    "ticker": "NVDA",
    "threshold_up": 120,     # 涨破触发
    "threshold_down": 105,   # 跌破触发
}
```

- 修改参数 = 修改脚本文件 → **禁用→启用(或保存)即重新注册**,新参数生效;直接改 CONFIG 以外的代码也一样
- CONFIG 内只能写字面量(数字/字符串/布尔/嵌套),不能写表达式;重写时注释不保留

### 滞回标准写法 / Hysteresis canonical pattern

```python
#!/usr/bin/env python3
import json, os

CONFIG = {"threshold_up": 120, "threshold_down": 105}
st = json.loads(os.environ.get("EVENT_STATE") or "{}")
armed = bool(st.get("armed", True))
# ... check logic -> should_fire / reset_condition ...
if armed and should_fire:
    print(json.dumps({"triggered": True, "title": "...", "event": "...", "state": {"armed": False}}, ensure_ascii=False))
else:
    print(json.dumps({"triggered": False, "state": {"armed": armed or reset_condition}}, ensure_ascii=False))
```

## 脚本编写指南 / Script authoring guide

**格式 / Format**:Python 为主(平台 venv,可用平台库);`interpreter` 字段可换解释器。外部请求自带超时(脚本总超时默认 60s)。/ Python first (platform venv); `interpreter` field for others. Inner network calls need shorter timeouts (script timeout default 60s).

**字段 / Output fields**:`title` 简短标题;`event` 详细正文(notify 即通知正文,agent 任务填入 prompt 的 `{event}`);`cooldown` 按次覆盖冷却;`state` 持久化回传。

> ⚠️ 模板(notify_template / prompt_template)经 Python `str.format` 渲染,占位符 `{title}` `{event}`;文案中的**字面花括号需双写转义**——`{{"symbol": "NVDA"}}` 渲染为 `{"symbol": "NVDA"}`,单写会 KeyError。/ Templates render via `str.format` with `{title}` `{event}` placeholders; **double literal braces** (`{{...}}`) or they raise KeyError.

**规则 / Rules**
1. 持续性条件必须滞回(否则每个间隔触发 = 风暴)/ Persistent conditions need hysteresis (else fires every interval = storm)
2. 一次性标志不要放 state——注册试跑会真实执行一次并保存 state,会把 latch 消耗掉;一次性判断放事件源本身 / One-shot flags must NOT live in state — the registration dry-run executes once for real and consumes the latch; detect one-shot-ness from the event source
3. stdout 纪律:调试信息别以 `{` 开头(引擎取最后一个可解析 JSON 行)/ stdout discipline: debug lines must not start with `{`
4. 不要读引擎内部文件,只通过 EVENT_STATE(进)和 stdout(出)/ interact only via EVENT_STATE (in) and stdout (out)

## 现成模板 / Bundled templates

`GET /api/events/templates` 返回 5 个模板(股价阈值滞回 / HTTP 探测 / 文件变化 / 端口存活 / 日志关键字),每个含 `params` 与 `script` 全文。流程:取模板 → 替换 `__占位符__` → 作为 `script_content` POST。
`GET /api/events/templates` returns 5 templates (stock-threshold hysteresis / HTTP probe / file change / port alive / log keyword) with `params` + full `script`. Flow: fetch → substitute `__PLACEHOLDERS__` → POST as `script_content`.

## 创建前最少确认 / Minimum info before creating

缺任一项先问用户 / Ask first if missing:触发条件与间隔 / trigger condition + interval;`action`(notify/agent);投递目标 channel / user_id;冷却时间(事件可能连续发生时必设)/ cooldown (mandatory for repeatable events)。

## 常见错误 / Common mistakes

1. 一次性标志放 state(试跑消耗)/ One-shot flag in state (consumed by dry-run)
2. stdout 混入 `{` 开头的调试输出 / Non-JSON debug output starting with `{`
3. 持续为真的条件没设滞回或冷却 → 风暴 / Persistent condition without hysteresis/cooldown → storm
4. 改脚本不重新 PUT → hash 拒跑 / Script edited without re-PUT → hash check refuses
5. `agent_id` 缺失或错 → 挂错 agent / wrong/missing `agent_id` → lands on wrong agent
6. **删除任务会同步删除引擎托管的脚本文件**(scripts 目录内;agent 自己写的脚本通常只有这一份)——删除前确认是否需要保留,引用路径模式的外部脚本不受影响 / Deleting a task also deletes its engine-managed script file (often the only copy of an agent-authored script) — confirm before deleting; scripts referenced by path are untouched

## 最小工作流 / Minimal workflow

```
1. 条件触发(事件任务)还是时间触发(cron)? / condition or time?
2. 与用户确认触发条件 → 设计检查脚本(CONFIG 参数 + 滞回)/ design checker (CONFIG + hysteresis)
3. POST /api/events/ 创建(script_content 内联,enabled=false)
4. POST /{id}/run 验证一次检查 / verify one check
5. POST /{id}/enable 启用(= 注册:校验+试跑+hash 锚定)/ enable = register
6. 排查 GET /{id}/runs;修改 PUT / inspect runs; modify via PUT
```

### 触发-演化循环 / Fire-evolve loop(行情类监控的核心模式)

条件会演化的监控(如"涨破 100 或跌破 90 → 观望期改为 105-120"):

1. 创建:CONFIG 双边界(up=100, down=90)+ `max_triggers: 1` + enabled
2. 触发后引擎**自动禁用**(旧条件已失效,防空转;审计留痕)
3. agent 推理后判断新监控范围 → `PUT /api/events/{id}` 带**新 CONFIG**(up=120, down=105)→ 重新校验
4. `POST /{id}/enable` 启用(本轮触发计数清零)→ 新一轮监控
5. 人类随时可在 UI 参数表单改 CONFIG,与 agent 走同一接口

`max_triggers` 语义:累计触发 N 次后自动禁用(0=不限);**启用时计数清零**。

