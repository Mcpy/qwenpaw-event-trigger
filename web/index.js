/* QwenPaw Event Trigger (事件任务 / Event Tasks) — frontend plugin
   no-build, host-shared React/antd. v5: full zh/en i18n via useLocale,
   templates fetched from backend (single source of truth). */
(function () {
  "use strict";
  var H = window.QwenPaw.host;
  var React = H.React;
  var antd = H.antd;
  var e = React.createElement;
  var P = "event-trigger";
  var NAV_LANG = (navigator.language || "zh").toLowerCase().indexOf("zh") === 0 ? "zh" : "en";

  var Table = antd.Table, Tag = antd.Tag, Button = antd.Button, Switch = antd.Switch,
      Modal = antd.Modal, Input = antd.Input, InputNumber = antd.InputNumber,
      Select = antd.Select, Drawer = antd.Drawer, Tabs = antd.Tabs, Space = antd.Space,
      Popconfirm = antd.Popconfirm, message = antd.message, Tooltip = antd.Tooltip,
      Typography = antd.Typography, Radio = antd.Radio, Alert = antd.Alert,
      Badge = antd.Badge;
  var TextArea = Input.TextArea;
  var Text = Typography.Text;

  function api(p, opts) {
    // tolerant of non-JSON error bodies (e.g. plain-text 500s)
    return H.fetch("/events" + p, opts).then(function (r) {
      return r.text().then(function (txt) {
        var d;
        try { d = JSON.parse(txt); }
        catch (e) { throw new Error("HTTP " + r.status + ": " + txt.slice(0, 120)); }
        if (!r.ok) throw new Error(d.detail || ("HTTP " + r.status));
        return d;
      });
    });
  }
  function ts(v) { return v ? new Date(v * 1000).toLocaleString() : "—"; }
  function coerceConfig(cfg) {
    // numbers/bools stay typed; everything else as string
    var out = {};
    Object.keys(cfg || {}).forEach(function (k) {
      var x = cfg[k];
      if (x === "true") out[k] = true;
      else if (x === "false") out[k] = false;
      else if (x !== "" && !isNaN(Number(x))) out[k] = Number(x);
      else out[k] = x;
    });
    return out;
  }

  /* ================= i18n ================= */
  var L10N = {
    zh: {
      menu: "事件任务", crumb: "控制 / ", create: "+ 创建任务",
      colTask: "任务", colInterval: "间隔", colCounters: "运行/触发", colLastRun: "上次运行",
      colEnabled: "启用", colActions: "操作",
      btnRun: "▶ 执行", btnRuns: "记录", btnEdit: "编辑", btnDelete: "删除",
      runNowOk: "已执行一次检查", deleteConfirm: "删除该任务?将同步删除其脚本文件(不可恢复)",
      modalCreate: "创建事件任务", modalEdit: "编辑事件任务(热更新)",
      fId: "任务ID", fName: "任务名称", fEnabled: "启用状态", fInbox: "运行结果存进收件箱",
      fChecker: "检查器", fInterval: "检查间隔(秒,≥10)", fTaskType: "任务类型",
      fRequest: "请求内容", fNotify: "通知内容", fChannel: "目标频道",
      fUser: "目标用户ID", fSession: "目标会话ID", fMode: "分发模式",
      fSilent: "静默投递", fToolSafety: "工具安全审批",
      fCooldown: "冷却(秒)", fScriptTimeout: "脚本超时(秒)", fTimeout: "推理超时(秒)",
      fMaxTriggers: "最大触发次数(0=无限)", fConfig: "参数(CONFIG)",
      cfgAdd: "+ 参数", cfgRemove: "✕", cfgTip: "脚本内 CONFIG 声明的参数;修改后保存会回写脚本并重新校验,启用时以新参数试跑初始化状态。注释不会保留。",
      actionNotify: "通知(不推理)", actionAgent: "Agent 推理",
      srcTemplate: "从模板", srcPaste: "粘贴脚本", srcPath: "引用路径",
      phName: "例如:英伟达突破监控", phPaste: "Python:读 EVENT_STATE,stdout 输出 {triggered:true, title, event, state}",
      phPath: "/abs/path/checker.py", phSession: "留空=独立会话;选择=共用该会话",
      btnCancel: "取 消", btnValidate: "仅校验", btnSave: "保 存",
      alertGate: "保存走注册关卡:语法检查 → 试跑(真实执行一次并初始化状态)→ 内容 hash 锚定;改脚本即重新校验。",
      drawerTitle: "执行记录:", showAll: "显示全部(含 检查/冷却跳过)", noRuns: "暂无记录",
      saved: "已保存", validated: "校验通过", targetsFail: "投递目标加载失败: ",
      nameRequired: "请输入任务名称", pasteRequired: "请粘贴脚本内容", pathRequired: "请填写脚本路径",
      notify: "notify", agent: "agent",
      expandedScript: "脚本: ", expandedDeliver: "投递: ", expandedCooldown: " · 冷却: ",
      kindTrigger: "🔥 触发", kindError: "🔴 错误", kindCheck: "检查", kindSkipped: "⏸ 冷却跳过"
    },
    en: {
      menu: "Event Tasks", crumb: "Control / ", create: "+ Create Task",
      colTask: "Task", colInterval: "Interval", colCounters: "Runs/Fires", colLastRun: "Last run",
      colEnabled: "Enabled", colActions: "Actions",
      btnRun: "▶ Run", btnRuns: "History", btnEdit: "Edit", btnDelete: "Delete",
      runNowOk: "One check executed", deleteConfirm: "Delete this task? Its engine-managed script file will also be deleted (irreversible)",
      modalCreate: "Create Event Task", modalEdit: "Edit Event Task (hot update)",
      fId: "Task ID", fName: "Task name", fEnabled: "Enabled", fInbox: "Save results to inbox",
      fChecker: "Checker", fInterval: "Check interval (s, ≥10)", fTaskType: "Task type",
      fRequest: "Request content", fNotify: "Notification content", fChannel: "Target channel",
      fUser: "Target user ID", fSession: "Target session ID", fMode: "Dispatch mode",
      fSilent: "Silent delivery", fToolSafety: "Tool safety approval",
      fCooldown: "Cooldown (s)", fScriptTimeout: "Script timeout (s)", fTimeout: "Reasoning timeout (s)",
      fMaxTriggers: "Max triggers (0 = unlimited)", fConfig: "Parameters (CONFIG)",
      cfgAdd: "+ Param", cfgRemove: "✕", cfgTip: "Parameters declared in the script's CONFIG block; saving writes them back into the script and re-validates. Enable re-seeds state with the new params. Comments inside CONFIG are not preserved.",
      actionNotify: "Notify (no reasoning)", actionAgent: "Agent reasoning",
      srcTemplate: "From template", srcPaste: "Paste script", srcPath: "Script path",
      phName: "e.g. NVDA breakout watch", phPaste: "Python: read EVENT_STATE, print {triggered:true, title, event, state} to stdout",
      phPath: "/abs/path/checker.py", phSession: "Empty = dedicated session; pick to share",
      btnCancel: "Cancel", btnValidate: "Validate only", btnSave: "Save",
      alertGate: "Saving runs the registration gate: syntax check → dry-run (executes once for real and seeds state) → content-hash pinning; any script change re-validates.",
      drawerTitle: "Run history: ", showAll: "Show all (incl. check/cooldown-skipped)", noRuns: "No records yet",
      saved: "Saved", validated: "Validation passed", targetsFail: "Failed to load dispatch targets: ",
      nameRequired: "Task name is required", pasteRequired: "Paste the script content", pathRequired: "Script path is required",
      notify: "notify", agent: "agent",
      expandedScript: "Script: ", expandedDeliver: "Dispatch: ", expandedCooldown: " · Cooldown: ",
      kindTrigger: "🔥 Fired", kindError: "🔴 Error", kindCheck: "Check", kindSkipped: "⏸ Cooldown-skipped"
    }
  };
  var TOOLTIPS = {
    zh: {
      id: "任务的唯一标识符,由系统在创建时自动分配,不可修改。",
      name: "任务的友好名称,便于识别。",
      enabled: "关闭后停止检查,但保留任务配置。",
      inbox: "开启后,任务执行成功且投递成功时,会将结果写入收件箱;若投递失败,系统会自动兜底写入收件箱。",
      checker: "检查脚本按间隔轮询执行:读环境变量 EVENT_STATE(上次持久化状态),stdout 输出 JSON(必须含布尔 triggered,可带 title/event/cooldown/state)。保存时走注册关卡:语法检查 → 试跑(真实执行一次并初始化状态)→ 内容 hash 锚定;之后修改脚本会被拒跑,需重新注册。",
      interval: "最小 10 秒。",
      taskType: "选择 'notify' 用于纯通知告警(不推理),选择 'agent' 触发智能体推理。",
      requestInput: "填写希望智能体执行的任务,占位符 {title} {event} 会被脚本输出替换。",
      notifyTpl: "固定消息模板,占位符 {title} {event} 会被脚本输出替换。",
      dispatchChannel: "响应将发送到的目标频道(例如:'console'、'ntfy')。",
      dispatchTargetUserId: "在目标频道中接收响应的用户ID。",
      dispatchTargetSessionId: "选择会话 = 本任务在该会话的上下文中执行,结果也投递到该会话(共用)。留空 = 使用独立的累积会话(每次运行共享同一上下文,与其他会话隔离)。",
      dispatchMode: "选择 'stream' 获取实时响应,或选择 'final' 仅获取完整响应。",
      silentDelivery: "完整执行智能体任务并保留会话和追踪记录,但不向渠道发送结果。",
      shareSession: "开启时,与目标用户共用会话。关闭时,本任务在独立会话中运行,互不影响。适用于不需要记忆历史的独立任务。默认:关闭",
      toolSafety: "开启时,高风险工具调用需要用户审批(可能阻塞无人值守的事件任务)。关闭时,工具调用不再请求审批;文件防护规则仍然生效。默认:关闭",
      cooldown: "触发后在此时间内不再重复触发,防止事件风暴。脚本也可通过输出 cooldown 字段覆盖。",
      maxTriggers: "累计触发该次数后任务自动禁用(0=不限)。重新启用时计数清零,开始新一轮监控。适用于'触发即完成'的一次性监控。"
    },
    en: {
      id: "Unique task ID, assigned automatically at creation, immutable.",
      name: "A friendly name to identify the task.",
      enabled: "When off, checking stops but the task configuration is kept.",
      inbox: "When on, successful runs with successful delivery are written to the inbox; failed deliveries fall back to the inbox automatically.",
      checker: "The checker script is polled at a fixed interval: reads env EVENT_STATE (last persisted state) and prints a JSON to stdout (boolean 'triggered' required; optional title/event/cooldown/state). Saving runs the registration gate: syntax check → dry-run (executes once for real and seeds state) → content-hash pinning; later script changes are refused until re-registered.",
      interval: "Minimum 10 seconds.",
      taskType: "'notify' delivers a plain notification (no reasoning); 'agent' fires agent reasoning.",
      requestInput: "The task you want the agent to perform; {title} {event} placeholders are replaced by the script output.",
      notifyTpl: "Fixed message template; {title} {event} placeholders are replaced by the script output.",
      dispatchChannel: "The channel the response is delivered to (e.g. 'console', 'ntfy').",
      dispatchTargetUserId: "The user ID receiving the response in the target channel.",
      dispatchTargetSessionId: "Pick a session = this task runs in that session context and delivers there (shared). Leave empty for a dedicated accumulating session (runs share one context, isolated from others).",
      dispatchMode: "'stream' for live responses, 'final' for the completed response only.",
      silentDelivery: "Run the agent task fully and keep session/trace records, but deliver nothing to channels.",
      shareSession: "When on, shares the session with the target user. When off, this task runs in its own session, isolated from others. For stateless tasks. Default: off",
      toolSafety: "When on, high-risk tool calls require user approval (may block unattended event tasks). When off, tool calls run without approval; file-protection rules still apply. Default: off",
      cooldown: "After a fire, no re-fire within this window (event-storm protection). The script's cooldown output field can override per-fire.",
      maxTriggers: "Auto-disable the task after this many fires (0 = unlimited). The per-round counter resets on enable. Ideal for fire-once watch jobs."
    }
  };
  function mkT(locale) {
    return function (k) { return (L10N[locale] && L10N[locale][k]) || L10N.zh[k] || k; };
  }
  function tt(T, locale, k) { return (TOOLTIPS[locale] && TOOLTIPS[locale][k]) || TOOLTIPS.zh[k]; }
  function loc(v, locale) {
    if (v === null || v === undefined) return "";
    if (typeof v === "string") return v;
    return v[locale] || v.zh || "";
  }

  /* ================= rule form modal ================= */
  function RuleFormModal(props) {
    var open = props.open, editing = props.editing, onClose = props.onClose, onSaved = props.onSaved;
    var locale = H.useLocale ? H.useLocale() : NAV_LANG;
    var T = mkT(locale);
    var st = React.useState({});
    var v = st[0], setV = st[1];
    var stSrc = React.useState("template");
    var source = stSrc[0], setSource = stSrc[1];
    var stTpl = React.useState("stock");
    var tplId = stTpl[0], setTplId = stTpl[1];
    var stP = React.useState({});
    var pv = stP[0], setPv = stP[1];
    var stS = React.useState(false);
    var saving = stS[0], setSaving = stS[1];
    var stT = React.useState({ channels: ["console"], items: [], templates: [] });
    var targets = stT[0], setTargets = stT[1];

    React.useEffect(function () {
      if (open) {
        setSource(editing ? "path" : "template");
        setPv({});
        api("/dispatch-targets").then(function (d) {
          // merge, never overwrite — /templates may have arrived first
          setTargets(function (prev) { return Object.assign({}, prev, { channels: d.channels || ["console"], items: d.items || [] }); });
        })
          .catch(function (err) { message.error(T("targetsFail") + String(err.message || err).slice(0, 150)); });
        api("/templates").then(function (d) { setTargets(function (prev) { return Object.assign({}, prev, { templates: d.templates || [] }); }); })
          .catch(function () {});
        var rt = (editing && editing.runtime) || {};
        setV(editing ? {
          name: editing.name, enabled: editing.enabled,
          interval: editing.interval_seconds, action: editing.action,
          script_path: editing.script || "",
          channel: (editing.dispatch && editing.dispatch.channel) || "console",
          user_id: (editing.dispatch && editing.dispatch.user_id) || "default",
          session_id: (editing.dispatch && editing.dispatch.session_id) || null,
          cooldown: editing.cooldown_seconds,
          max_triggers: rt.max_triggers || 0,
          config: editing.config || {},
          script_timeout: rt.script_timeout_seconds || 60,
          timeout: rt.timeout_seconds || 120,
          tool_safety: !!rt.tool_safety,
          dispatch_mode: rt.dispatch_mode || "stream",
          silent: !!rt.silent,
          inbox: rt.save_result_to_inbox === true,
          prompt_template: "Event fired: [{title}] {event}\n(处理本事件前,请先通过 Skill 工具阅读 event-tasks 技能 / read the event-tasks skill first)",
          notify_template: "Event: [{title}] {event}"
        } : {
          enabled: false, interval: 60, action: "agent",
          channel: "console", user_id: "default", session_id: null,
          cooldown: 600, script_timeout: 60, timeout: 120, max_triggers: 0, config: {},
          tool_safety: false,
          dispatch_mode: "stream", silent: false, inbox: false,
          prompt_template: "Event fired: [{title}] {event}\n(处理本事件前,请先通过 Skill 工具阅读 event-tasks 技能 / read the event-tasks skill first)",
          notify_template: "Event: [{title}] {event}"
        });
      }
    }, [open, editing]);

    function set(k) { return function (val) { var n = {}; n[k] = val; setV(Object.assign({}, v, n)); }; }

    function buildBody() {
      var body = {
        name: v.name, agent_id: (H.getSelectedAgentId && H.getSelectedAgentId()) || "default",
        interval_seconds: v.interval || 60,
        action: v.action || "agent",
        prompt_template: v.prompt_template || "Event fired: [{title}] {event}",
        notify_template: v.notify_template || "Event: [{title}] {event}",
        channel: v.channel || "console", user_id: v.user_id || "default",
        session_id: v.session_id || null,
        cooldown_seconds: v.cooldown === undefined || v.cooldown === null ? 600 : v.cooldown,
        max_triggers: v.max_triggers || 0,
        config: editing ? coerceConfig(v.config) : undefined,
        timeout_seconds: v.timeout || 120,
        script_timeout_seconds: v.script_timeout || 60,
        tool_safety: !!v.tool_safety,
        dispatch_mode: v.dispatch_mode || "stream", silent: !!v.silent,
        save_result_to_inbox: v.inbox === true,
        enabled: v.enabled !== false
      };
      if (source === "template" && !editing) {
        var t = (targets.templates || []).find(function (x) { return x.id === tplId; });
        if (t) {
          var s = t.script;
          t.params.forEach(function (pr) {
            var val = (pv[pr.k] !== undefined && pv[pr.k] !== "") ? pv[pr.k] : pr.d;
            s = s.split(pr.k).join(val);
          });
          body.script_content = s;
        }
      } else if (source === "paste") {
        body.script_content = v.script_content || "";
      } else if (source === "path") {
        body.script_path = v.script_path || (editing ? editing.script : "");
      }
      return body;
    }

    function submit(validateOnly) {
      if (!v.name) { message.error(T("nameRequired")); return; }
      if (source === "paste" && !(v.script_content || "").trim()) { message.error(T("pasteRequired")); return; }
      if (source === "path" && !(v.script_path || "").trim()) { message.error(T("pathRequired")); return; }
      setSaving(true);
      var body = buildBody();
      var url = editing ? ("/" + editing.id + "?validate_only=" + validateOnly) : ("/?validate_only=" + validateOnly);
      api(url, { method: editing ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
        .then(function (d) {
          var w = (d.warnings || []).filter(function (x) { return x.indexOf("validate-only") < 0; });
          message.success((validateOnly ? T("validated") : T("saved")) + (w.length ? ":" + w.join(";") : ""));
          if (!validateOnly) onSaved();
        })
        .catch(function (err) { message.error(String(err.message || err).slice(0, 300)); })
        .finally(function () { setSaving(false); });
    }

    if (!open) return null;

    var tplList = targets.templates || [];
    var curTpl = tplList.find(function (t) { return t.id === tplId; }) || tplList[0];
    var isAgent = v.action === "agent";

    function lab(text, tip, required) {
      return e("span", null,
        text, " ",
        required ? e("span", { style: { color: "#ff4d4f" }, title: "必填 / required" }, "*") : null,
        tip ? e(Tooltip, { title: tip },
          e("span", { style: { cursor: "help", marginLeft: 4, opacity: 0.55, fontSize: 13 } }, "ⓘ")) : null);
    }
    function fi(label, tip, required, control) {
      return e("div", { style: { marginBottom: 14 } },
        e("div", { style: { marginBottom: 6 } }, lab(label, tip, required)),
        control);
    }

    var checkerTabs = e(Tabs, {
      activeKey: source, onChange: setSource, size: "small",
      items: [
        { key: "template", label: T("srcTemplate"), disabled: !!editing, children: e("div", null,
            e(Select, { style: { width: "100%", marginBottom: 8 }, value: tplId,
              onChange: function (x) {
                setTplId(x);
                var t = tplList.find(function (y) { return y.id === x; });
                if (t && t.prompt) set("prompt_template")(loc(t.prompt, locale));
              },
              options: tplList.map(function (t) { return { value: t.id, label: loc(t.name, locale) + " (" + t.id + ")" }; }) }),
            curTpl && curTpl.params.map(function (pr) {
              return e("div", { key: pr.k, style: { marginBottom: 6 } },
                e(Text, { type: "secondary", style: { fontSize: 12 } }, loc(pr.label, locale)),
                e(Input, { placeholder: pr.d, value: pv[pr.k] || "",
                  onChange: function (ev) { var n = {}; n[pr.k] = ev.target.value; setPv(Object.assign({}, pv, n)); } }));
            })
          ) },
        { key: "paste", label: T("srcPaste"), children: e(TextArea, { rows: 10,
            value: v.script_content || "",
            placeholder: T("phPaste"),
            onChange: function (ev) { set("script_content")(ev.target.value); } }) },
        { key: "path", label: T("srcPath"), children: e(Input, {
            value: v.script_path || (editing ? editing.script : ""),
            placeholder: T("phPath"),
            onChange: function (ev) { set("script_path")(ev.target.value); } }) }
      ]
    });

    return e(Modal, {
      open: open, title: editing ? T("modalEdit") : T("modalCreate"),
      width: 640, onCancel: onClose, footer: null, destroyOnClose: true,
    },
      e("div", { style: { maxHeight: "62vh", overflow: "auto", paddingRight: 4 } },

        editing ? fi(T("fId"), tt(T, locale, "id"), false,
          e(Input, { value: editing.id, disabled: true })) : null,

        fi(T("fName"), tt(T, locale, "name"), true,
          e(Input, { value: v.name || "", placeholder: T("phName"), onChange: function (ev) { set("name")(ev.target.value); } })),

        fi(T("fEnabled"), tt(T, locale, "enabled"), false,
          e(Switch, { checked: v.enabled !== false, onChange: set("enabled") })),

        fi(T("fChecker"), tt(T, locale, "checker"), true, checkerTabs),
        editing ? fi(T("fConfig"), T("cfgTip"), false,
          e("div", null,
            Object.keys(v.config || {}).map(function (k) {
              return e("div", { key: k, style: { display: "flex", gap: 6, marginBottom: 4 } },
                e(Input, { value: k, disabled: true, style: { width: "38%" } }),
                e(Input, { value: String(v.config[k]), style: { flex: 1 },
                  onChange: function (ev) { var n = Object.assign({}, v.config); n[k] = ev.target.value; set("config")(n); } }),
                e(Button, { size: "small", type: "text", danger: true,
                  onClick: function () { var n = Object.assign({}, v.config); delete n[k]; set("config")(n); } }, "✕"));
            }),
            e(Button, { size: "small", onClick: function () {
              var n = Object.assign({}, v.config); n["param_" + Object.keys(n).length] = ""; set("config")(n);
            } }, T("cfgAdd"))
          )) : null,
        e("div", { style: { marginBottom: 14 } },
          e("div", { style: { marginBottom: 6 } }, lab(T("fInterval"), tt(T, locale, "interval"), true)),
          e(InputNumber, { min: 10, value: v.interval, style: { width: 140 }, onChange: set("interval") })),

        fi(T("fTaskType"), tt(T, locale, "taskType"), true,
          e(Radio.Group, { value: v.action, onChange: function (ev) { set("action")(ev.target.value); } },
            e(Radio.Button, { value: "notify" }, T("actionNotify")),
            e(Radio.Button, { value: "agent" }, T("actionAgent")))),

        isAgent
          ? fi(T("fRequest"), tt(T, locale, "requestInput"), true,
              e(TextArea, { rows: 2, value: v.prompt_template || "", onChange: function (ev) { set("prompt_template")(ev.target.value); } }))
          : fi(T("fNotify"), tt(T, locale, "notifyTpl"), true,
              e(TextArea, { rows: 2, value: v.notify_template || "", onChange: function (ev) { set("notify_template")(ev.target.value); } })),

        fi(T("fChannel"), tt(T, locale, "dispatchChannel"), true,
          e(Select, { style: { width: "100%" }, value: v.channel || "console", showSearch: true,
            options: (targets.channels || ["console"]).map(function (c) { return { value: c, label: c }; }),
            onChange: set("channel") })),

        fi(T("fUser"), tt(T, locale, "dispatchTargetUserId"), true,
          e(Select, { style: { width: "100%" }, value: v.user_id || "default", showSearch: true,
            options: (function () {
              var src = targets.items || [];
              if (v.channel) src = src.filter(function (i) { return i.channel === v.channel; });
              var seen = {}, out = [];
              src.forEach(function (i) { if (!seen[i.user_id]) { seen[i.user_id] = 1; out.push({ value: i.user_id, label: i.user_id }); } });
              return out;
            })(),
            onChange: set("user_id") })),

        fi(T("fSession"), tt(T, locale, "dispatchTargetSessionId"), false,
          e(Select, { style: { width: "100%" }, value: v.session_id || undefined,
            showSearch: true, allowClear: true,
            placeholder: T("phSession"),
            filterOption: function (input, option) {
              if (!input) return true;
              return String(option.value || "").toLowerCase().indexOf(input.toLowerCase()) >= 0;
            },
            options: (function () {
              var src = targets.items || [];
              if (v.channel) src = src.filter(function (i) { return i.channel === v.channel; });
              return src.map(function (i) { return { value: i.session_id, label: i.session_id }; });
            })(),
            onChange: function (val) { set("session_id")(val || null); } })),

        isAgent ? fi(T("fMode"), tt(T, locale, "dispatchMode"), false,
          e(Select, { style: { width: 200 }, value: v.dispatch_mode || "stream",
            options: [{ value: "final", label: "final" }, { value: "stream", label: "stream" }],
            onChange: set("dispatch_mode") })) : null,

        fi(T("fSilent"), tt(T, locale, "silentDelivery"), false,
          e(Switch, { checked: !!v.silent, disabled: !isAgent, onChange: set("silent") })),

        fi(T("fToolSafety"), tt(T, locale, "toolSafety"), false,
          e(Switch, { checked: !!v.tool_safety, onChange: set("tool_safety") })),

        e("div", { style: { display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 14 } },
          e(Space, { align: "center" }, lab(T("fCooldown"), tt(T, locale, "cooldown"), false), e(InputNumber, { min: 0, value: v.cooldown, style: { width: 100 }, onChange: set("cooldown") })),
          e(Space, { align: "center" }, lab(T("fMaxTriggers"), tt(T, locale, "maxTriggers"), false), e(InputNumber, { min: 0, value: v.max_triggers, style: { width: 100 }, onChange: set("max_triggers") })),
          e(Space, { align: "center" }, e(Text, null, T("fScriptTimeout")), e(InputNumber, { min: 1, value: v.script_timeout, style: { width: 90 }, onChange: set("script_timeout") })),
          e(Space, { align: "center" }, e(Text, null, T("fTimeout")), e(InputNumber, { min: 1, value: v.timeout, style: { width: 90 }, onChange: set("timeout") }))
        ),

        e(Alert, { style: { marginTop: 2 }, type: "info", showIcon: false, message: T("alertGate") })
      ),
      e("div", { style: { textAlign: "right", marginTop: 10 } },
        e(Space, null,
          e(Button, { onClick: onClose }, T("btnCancel")),
          e(Button, { onClick: function () { submit(true); }, loading: saving }, T("btnValidate")),
          e(Button, { type: "primary", onClick: function () { submit(false); }, loading: saving }, T("btnSave"))
        ))
    );
  }

  /* ================= runs drawer ================= */
  function RunsDrawer(props) {
    var rule = props.rule, onClose = props.onClose;
    var locale = H.useLocale ? H.useLocale() : NAV_LANG;
    var T = mkT(locale);
    var st = React.useState([]);
    var runs = st[0], setRuns = st[1];
    var st2 = React.useState(false);
    var showAll = st2[0], setShowAll = st2[1];
    var KIND_META = {
      trigger: { color: "orange", text: T("kindTrigger") },
      error:   { color: "red", text: T("kindError") },
      check:   { color: "default", text: T("kindCheck") },
      skipped: { color: "blue", text: T("kindSkipped") }
    };

    React.useEffect(function () {
      if (rule) {
        api("/" + rule.id + "/runs?limit=200").then(function (d) { setRuns(d.runs || []); })
          .catch(function () { setRuns([]); });
      }
    }, [rule]);

    var shown = (runs || []).slice().reverse()
      .filter(function (r) { return showAll || r.kind === "trigger" || r.kind === "error"; });

    return e(Drawer, { open: !!rule, onClose: onClose, width: 480,
      title: rule ? T("drawerTitle") + rule.name : "" },
      e("div", { style: { marginBottom: 8 } },
        e(Space, { align: "center" },
          e(Text, null, T("showAll")),
          e(Switch, { checked: showAll, onChange: setShowAll }))),
      shown.length === 0 ? e(Text, { type: "secondary" }, T("noRuns")) : null,
      shown.map(function (r, i) {
        var m = KIND_META[r.kind] || { color: "default", text: r.kind };
        return e("div", { key: i, style: { borderBottom: "1px solid rgba(128,128,128,.15)", padding: "6px 0" } },
          e(Space, { size: 8 },
            e(Tag, { color: m.color }, m.text),
            e(Text, { type: "secondary", style: { fontSize: 12 } }, ts(r.ts), " · ", r.duration_ms, "ms")),
          e("div", { style: { fontSize: 12, whiteSpace: "pre-wrap" } }, r.detail || "—"));
      })
    );
  }

  /* ================= main page ================= */
  function RulesPage() {
    var locale = H.useLocale ? H.useLocale() : NAV_LANG;
    var T = mkT(locale);
    var s1 = React.useState([]);
    var rules = s1[0], setRules = s1[1];
    var s2 = React.useState(false);
    var modalOpen = s2[0], setModalOpen = s2[1];
    var s3 = React.useState(null);
    var editing = s3[0], setEditing = s3[1];
    var s4 = React.useState(null);
    var runsRule = s4[0], setRunsRule = s4[1];

    function load() {
      api("/").then(function (d) { setRules(d.rules || []); })
        .catch(function (err) { message.error(String(err.message || err).slice(0, 200)); });
    }
    React.useEffect(function () {
      load();
      var t = setInterval(load, 15000);
      return function () { clearInterval(t); };
    }, []);

    function toggle(rule, on) {
      api("/" + rule.id + (on ? "/enable" : "/disable"), { method: "POST" })
        .then(load).catch(function (err) { message.error(String(err.message || err)); });
    }
    function runNow(rule) {
      api("/" + rule.id + "/run", { method: "POST" })
        .then(function () { message.success(T("runNowOk")); load(); })
        .catch(function (err) { message.error(String(err.message || err)); });
    }
    function del(rule) {
      api("/" + rule.id, { method: "DELETE" }).then(load)
        .catch(function (err) { message.error(String(err.message || err)); });
    }

    var columns = [
      { title: T("colTask"), dataIndex: "name",
        render: function (v, r) {
          return e(Space, { direction: "vertical", size: 0 },
            e(Space, { size: 6 },
              e(Badge, { status: !r.enabled ? "default" : (r.last_error ? "error" : "success") }),
              e("b", null, v),
              e(Tag, { color: r.action === "agent" ? "geekblue" : "green" }, r.action === "agent" ? T("agent") : T("notify"))),
            r.last_error ? e(Text, { type: "danger", style: { fontSize: 12 } }, String(r.last_error).slice(0, 90)) : null);
        } },
      { title: T("colInterval"), width: 70, render: function (_, r) { return e(Text, null, r.interval_seconds + "s"); } },
      { title: T("colCounters"), width: 110, render: function (_, r) { return e(Text, null, "⟳" + r.run_count + " ▲" + r.trigger_count); } },
      { title: T("colLastRun"), width: 150, render: function (_, r) { return e(Text, { type: "secondary" }, ts(r.last_run_at)); } },
      { title: T("colEnabled"), width: 70, render: function (_, r) { return e(Switch, { checked: r.enabled, onChange: function (x) { toggle(r, x); } }); } },
      { title: T("colActions"), width: 270, render: function (_, r) {
          return e(Space, { size: 2 },
            e(Button, { size: "small", onClick: function () { runNow(r); } }, T("btnRun")),
            e(Button, { size: "small", onClick: function () { setRunsRule(r); } }, T("btnRuns")),
            e(Button, { size: "small", type: "link", onClick: function () { setEditing(r); setModalOpen(true); } }, T("btnEdit")),
            e(Popconfirm, { title: T("deleteConfirm"), onConfirm: function () { del(r); } },
              e(Button, { size: "small", type: "link", danger: true }, T("btnDelete"))));
        } }
    ];

    return e("div", { style: { padding: "16px 24px" } },
      e("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 } },
        e("div", { style: { fontSize: 18, fontWeight: 600 } },
          e(Text, { type: "secondary", style: { fontSize: 18, fontWeight: 600 } }, T("crumb")),
          e("span", null, T("menu"))),
        e(Button, { type: "primary", onClick: function () { setEditing(null); setModalOpen(true); } }, T("create"))),
      e(Table, {
        rowKey: "id", dataSource: rules, columns: columns, pagination: false,
        expandable: {
          expandedRowRender: function (r) {
            return e("div", { style: { fontSize: 12 } },
              e("div", null, T("expandedScript"), r.script, " (hash ", r.script_hash, ")"),
              e("div", null, T("expandedDeliver"), JSON.stringify(r.dispatch), T("expandedCooldown"), r.cooldown_seconds, "s · state: ", JSON.stringify(r.state)));
          }
        }
      }),
      e(RuleFormModal, { open: modalOpen, editing: editing,
        onClose: function () { setModalOpen(false); },
        onSaved: function () { setModalOpen(false); load(); } }),
      e(RunsDrawer, { rule: runsRule, onClose: function () { setRunsRule(null); } })
    );
  }

  var BoltIcon = e("svg", {
    viewBox: "64 64 896 896", width: "1em", height: "1em",
    fill: "currentColor", "aria-hidden": "true", focusable: "false"
  }, e("path", { d: "M848 359.3H627.7L825.8 109c4.1-5.3.4-13-6.3-13H436c-2.8 0-5.5 1.5-6.9 4L170 547.5c-3.1 5.3.7 12 6.9 12h174.4l-198 249.5c-4.1 5.3-.4 13 6.3 13h382.9c2.8 0 5.5-1.5 6.9-4l259.4-434.5c3.2-5.2-.6-12.2-6.8-12.2z" }));

  window.QwenPaw.menu.add(P, {
    id: "event-trigger.menu", label: NAV_LANG === "zh" ? "事件任务" : "Event Tasks",
    route: "event-trigger.home", icon: BoltIcon,
    location: "primary.agentScoped", order: 60
  });
  window.QwenPaw.route.add(P, {
    id: "event-trigger.home", path: "/event-trigger", component: RulesPage
  });

  console.log("[event-trigger] frontend registered (v5 i18n zh/en)");
})();
