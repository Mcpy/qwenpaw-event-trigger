---
name: event-tasks
description: 仅当需要"条件触发"时使用——外部事件发生(价格突破阈值、文件被修改、HTTP 服务异常、端口不可达、日志出现关键字等)时自动触发推理或通知。通过 /api/events/ REST 接口管理,检查脚本按间隔轮询。定时/周期需求请改用 cron skill。
metadata:
  builtin_skill_version: "1.0"
  qwenpaw:
    emoji: "⚡"
---

# 事件任务管理(条件触发)

## 什么时候用

事件任务 = **条件驱动**(事件发生才触发);定时任务 cron = **时间驱动**(到点就跑)。

### 应该使用事件任务
- 用户说"当/如果 X 发生时,提醒我 / 处理 Y":BTC 涨破某价、文件被改、服务挂了、日志出现 ERROR
- 触发条件无法用时间表达,只能靠轮询检查
- 需要"事件风暴防护"(冷却/滞回)

### 不应使用事件任务
- "每天 9 点 / 每小时"执行 → 用 **cron**
- 只是现在立即做一次 → 直接执行,不要建任务
- 用户说不清触发条件 → 先追问,再创建

### 与 cron 组合
- cron 定期巡检适合"低频全面体检";事件任务适合"异动即时响应"
- 同一主题可以两者并存: cron 每天早报 + 事件任务突破告警

---

## 管理 API(全部走 HTTP)

基础地址:`http://127.0.0.1:8088`(本机免认证);远程需 `Authorization: Bearer <token>`。

```
GET    /api/events/                 列出任务(含状态/计数/错误)
POST   /api/events/                 创建(自动走注册关卡)
PUT    /api/events/{id}             更新(脚本变更会重新校验)
DELETE /api/events/{id}             删除
POST   /api/events/{id}/enable      启用
POST   /api/events/{id}/disable     禁用
POST   /api/events/{id}/run         立即检查一次
GET    /api/events/{id}/runs        运行记录
GET    /api/events/protocol         检查脚本协议全文
```

## 创建任务

`POST /api/events/`,JSON 体:

```json
{
  "name": "任务名称",
  "agent_id": "<你的 agent_id,与系统提示中 Agent Identity 一致>",
  "interval_seconds": 60,
  "script_content": "<检查脚本全文(python)>",
  "action": "agent",
  "prompt_template": "Event fired: [{title}] {event}",
  "channel": "console",
  "user_id": "default",
  "session_id": null,
  "cooldown_seconds": 600,
  "enabled": false
}
```

- 也可以用 `"script_path": "/abs/path.py"` 代替 `script_content`(推荐 `script_content`,由引擎统一落盘管理)
- `action`:`notify`(只发通知不推理,不消耗 token)/ `agent`(触发推理)
- `interval_seconds` 最小 10
- `cooldown_seconds`:触发后冷却,防事件风暴;脚本输出里的 `cooldown` 字段可按次覆盖
- `session_id` 留空 = 独立累积会话(推荐)
- `enabled`:创建后默认 false(禁用),需要启用时再 `POST /{id}/enable`

## 检查脚本协议(核心)

**IN**:环境变量 `EVENT_STATE`(上次持久化状态的 JSON;首次为 `{}`)、`EVENT_RULE_ID`、`EVENT_RULE_NAME`。
**OUT**:stdout 输出一行 JSON:

```json
{"triggered": true, "title": "标题", "event": "给 agent/通知的正文", "state": {"armed": false}}
```

- `triggered` 必须是布尔;`state` 会被引擎持久化,并在下次运行时通过 `EVENT_STATE` 传回
- 退出码非 0 = 脚本错误(记录,不触发)
- stdout 超过 64KB 判为异常

### 滞回(防重复触发)标准写法

用 `state` 存"武装"标志:满足条件且 armed → 触发并 `armed:false`;回到复位条件 → 仅更新 state(不触发)置 `armed:true`。参考模板:

```python
#!/usr/bin/env python3
import json, os
st = json.loads(os.environ.get("EVENT_STATE") or "{}")
armed = bool(st.get("armed", True))
# ... 检查逻辑,得到 should_fire ...
if armed and should_fire:
    print(json.dumps({"triggered": True, "title": "...", "event": "...", "state": {"armed": False}}, ensure_ascii=False))
else:
    print(json.dumps({"triggered": False, "state": {"armed": armed or reset_condition}}, ensure_ascii=False))
```

## 脚本编写指南

### 格式规格

| 项 | 规格 |
| --- | --- |
| 语言 | Python 为主(平台 venv 的 python 执行,可 import 平台已有库);`interpreter` 字段可指定任意解释器 |
| 输入 | 环境变量 `EVENT_STATE`(上次 state 的 JSON,首次 `{}`)、`EVENT_RULE_ID`、`EVENT_RULE_NAME` |
| 输出 | stdout 一行 JSON:必须含布尔 `triggered`;可选 `title` / `event` / `cooldown`(秒,覆盖规则默认)/ `state`(持久化并回传) |
| 退出码 | 0 = 正常(读 JSON 判定);非 0 = 脚本错误(记日志、不触发) |
| 限制 | stdout ≤ 64KB;超时默认 60s(`script_timeout_seconds` 可调);间隔 ≥ 10s |
| 纯通知任务的 event | `event` 字段即通知正文;agent 任务的 `event` 会填进 prompt 模板的 `{event}` |

### 通用骨架(滞回模式,直接抄)

```python
#!/usr/bin/env python3
import json, os

st = json.loads(os.environ.get("EVENT_STATE") or "{}")
armed = bool(st.get("armed", True))

# --- 在这里写检查逻辑,得到两个布尔 ---
should_fire = False    # 满足触发条件?
reset_condition = False  # 满足复位(重新武装)条件?

out = {"triggered": False, "state": dict(st)}
if armed and should_fire:
    out.update({
        "triggered": True,
        "title": "简短标题",
        "event": "详细正文:发生了什么、关键数据。agent 任务会拿它作为推理输入。",
        "state": {"armed": False},
    })
elif reset_condition:
    out["state"] = {"armed": True}
print(json.dumps(out, ensure_ascii=False))
```

### 编写规则

1. **持续性条件必须滞回**:条件持续为真时,没有 armed 门会每个间隔触发一次(风暴)。触发即 `armed:false`,复位后才重新武装
2. **一次性事件不要用 state 做标志**:注册时的试跑会真实执行一次并保存 state,一次性 latch 会被消耗;把一次性判断放在**事件源本身**(如"目标文件是否存在")
3. **stdout 纪律**:调试信息别以 `{` 开头;引擎取最后一个可解析的 JSON 行
4. **不要读引擎内部文件**:脚本与引擎只通过 `EVENT_STATE`(进)和 stdout(出)交互
5. **外部请求设超时**:脚本有总超时,内部网络请求必须自带更短的 timeout

### 现成模板

`GET /api/events/templates` 返回 5 个内置模板(BTC 阈值滞回 / HTTP 探测 / 文件变化 / 端口存活 / 日志关键字),每个含 `params`(可调参数)和 `script` 全文。流程:取模板 → 替换 `__占位符__` → 作为 `script_content` POST 创建。控制台"从模板"tab 同源。

## 创建前的最少确认

缺以下任一项,先问用户再创建:
- 触发条件(写成什么检查逻辑)、检查间隔
- `action`(通知还是触发推理)
- 投递目标 channel / user_id
- 冷却时间(事件可能连续发生时必须设)

## 注册关卡(自动执行,agent 无需手动)

保存/更新时引擎自动:语法检查 → **试跑一次**(真实执行,输出 state 成为初始状态)→ 内容 hash 锚定。之后**任何脚本修改都会被拒跑**,必须重新 PUT 重新校验。

## 常见错误

1. **一次性标志放在 state 里**:注册试跑就会把它消耗掉 → 一次性标记应放在**事件源本身**(如文件是否已存在),不要放脚本 state
2. **stdout 混入非 JSON 调试输出**:引擎只取最后一个以 `{` 开头且能解析的行;调试信息避免以 `{` 开头
3. **没设 cooldown 且事件持续为真**:每间隔触发一次,形成风暴;持续型条件必须用滞回 state 或 cooldown
4. **修改脚本后不重新 PUT**:hash 校验拒跑,规则会显示 last_error
5. **agent_id 不传或传错**:任务会挂到别的 agent;必须与当前 Agent Identity 一致

## 最小工作流

```
1. 判断是条件触发(事件任务)还是时间触发(cron)
2. 和用户确认触发条件 → 设计检查脚本(含滞回)
3. POST /api/events/ 创建(script_content 内联,enabled 先 false)
4. POST /{id}/run 立即验证一次检查是否符合预期
5. POST /{id}/enable 启用
6. 排查用 GET /{id}/runs;修改用 PUT
```
