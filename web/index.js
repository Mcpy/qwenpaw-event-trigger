/* QwenPaw Event Trigger — frontend plugin (no-build, host-shared React/antd)
   v2: controlled state only — no antd Form instance (crash fix: hooks-in-hook) */
(function () {
  "use strict";
  var H = window.QwenPaw.host;
  var React = H.React;
  var antd = H.antd;
  var e = React.createElement;
  var P = "event-trigger";

  var Table = antd.Table, Tag = antd.Tag, Button = antd.Button, Switch = antd.Switch,
      Modal = antd.Modal, Input = antd.Input, InputNumber = antd.InputNumber,
      Select = antd.Select, Drawer = antd.Drawer, Tabs = antd.Tabs, Space = antd.Space,
      Popconfirm = antd.Popconfirm, message = antd.message,
      Typography = antd.Typography, Radio = antd.Radio, Alert = antd.Alert,
      Badge = antd.Badge;
  var TextArea = Input.TextArea;
  var Text = Typography.Text;

  function api(p, opts) {
    // host.fetch applies getApiUrl internally — pass the BUSINESS path only.
    // (verified: getApiUrl("/events") fed into fetch produced /api/api/events)
    return H.fetch("/events" + p, opts).then(function (r) {
      return r.json().then(function (d) {
        if (!r.ok) throw new Error(d.detail || ("HTTP " + r.status));
        return d;
      });
    });
  }
  function ts(v) { return v ? new Date(v * 1000).toLocaleString() : "—"; }

  /* ================= demo templates ================= */
  var TEMPLATES = [
    {
      id: "btc", name: "BTC 阈值监控(滞回)",
      params: [
        { k: "__SYMBOL__", d: "BTCUSDT", label: "交易对" },
        { k: "__THRESHOLD__", d: "100000", label: "触发阈值" },
        { k: "__RELEASE_PCT__", d: "0.98", label: "重武装比例(0.98=回踩2%)" }
      ],
      script: '#!/usr/bin/env python3\nimport json, os, urllib.request\n\nSYMBOL = "__SYMBOL__"\nTHRESHOLD = float("__THRESHOLD__")\nRELEASE = THRESHOLD * float("__RELEASE_PCT__")\n\nstate = json.loads(os.environ.get("EVENT_STATE") or "{}")\narmed = bool(state.get("armed", True))\nwith urllib.request.urlopen("https://api.binance.com/api/v3/ticker/price?symbol=" + SYMBOL, timeout=10) as r:\n    price = float(json.load(r)["price"])\n\nif armed and price >= THRESHOLD:\n    print(json.dumps({"triggered": True, "title": SYMBOL + " 突破 " + str(THRESHOLD), "event": SYMBOL + " 现价 " + str(price) + ",已突破阈值。请分析行情并决定是否值得提醒我。", "state": {"armed": False, "last_price": price}}, ensure_ascii=False))\nelif (not armed) and price <= RELEASE:\n    print(json.dumps({"triggered": False, "state": {"armed": True, "last_price": price}}, ensure_ascii=False))\nelse:\n    print(json.dumps({"triggered": False, "state": {"armed": armed, "last_price": price}}, ensure_ascii=False))\n'
    },
    {
      id: "http", name: "HTTP 探测(非2xx/超时触发)",
      params: [
        { k: "__URL__", d: "https://example.com/health", label: "探测 URL" },
        { k: "__TIMEOUT__", d: "10", label: "超时秒数" }
      ],
      script: '#!/usr/bin/env python3\nimport json, urllib.request\n\nURL = "__URL__"\ntry:\n    with urllib.request.urlopen(URL, timeout=__TIMEOUT__) as r:\n        code = r.status\nexcept Exception as exc:\n    print(json.dumps({"triggered": True, "title": "HTTP 探测失败", "event": URL + " 不可达: " + repr(exc)}, ensure_ascii=False))\n    raise SystemExit(0)\nif code >= 400:\n    print(json.dumps({"triggered": True, "title": "HTTP 状态异常", "event": URL + " 返回 " + str(code)}, ensure_ascii=False))\nelse:\n    print(json.dumps({"triggered": False}, ensure_ascii=False))\n'
    },
    {
      id: "file", name: "文件变化监测",
      params: [{ k: "__PATH__", d: "/path/to/file", label: "文件路径" }],
      script: '#!/usr/bin/env python3\nimport json, os\n\nPATH = "__PATH__"\nst = json.loads(os.environ.get("EVENT_STATE") or "{}")\ntry:\n    s = os.stat(PATH)\n    fp = str(s.st_mtime_ns) + ":" + str(s.st_size)\nexcept OSError as exc:\n    print(json.dumps({"triggered": True, "title": "文件不可访问", "event": PATH + ": " + repr(exc)}, ensure_ascii=False))\n    raise SystemExit(0)\nprev = st.get("fingerprint")\nif prev is not None and prev != fp:\n    print(json.dumps({"triggered": True, "title": "文件发生变化", "event": PATH + " 已被修改(mtime/size 变化)。", "state": {"fingerprint": fp}}, ensure_ascii=False))\nelse:\n    print(json.dumps({"triggered": False, "state": {"fingerprint": fp}}, ensure_ascii=False))\n'
    },
    {
      id: "port", name: "端口存活(不可达触发)",
      params: [
        { k: "__HOST__", d: "127.0.0.1", label: "主机" },
        { k: "__PORT__", d: "8080", label: "端口" },
        { k: "__TIMEOUT__", d: "5", label: "超时秒数" }
      ],
      script: '#!/usr/bin/env python3\nimport json, socket\n\nHOST, PORT, TIMEOUT = "__HOST__", __PORT__, __TIMEOUT__\ntry:\n    with socket.create_connection((HOST, PORT), timeout=TIMEOUT):\n        print(json.dumps({"triggered": False}, ensure_ascii=False))\nexcept Exception as exc:\n    print(json.dumps({"triggered": True, "title": "端口不可达", "event": HOST + ":" + str(PORT) + " 连接失败: " + repr(exc)}, ensure_ascii=False))\n'
    },
    {
      id: "log", name: "日志关键字(增量扫描)",
      params: [
        { k: "__FILE__", d: "/var/log/app.log", label: "日志文件" },
        { k: "__KEYWORD__", d: "ERROR", label: "关键字" }
      ],
      script: '#!/usr/bin/env python3\nimport json, os\n\nFILE, KEY = "__FILE__", "__KEYWORD__"\nst = json.loads(os.environ.get("EVENT_STATE") or "{}")\noffset = int(st.get("offset", 0))\ntry:\n    size = os.path.getsize(FILE)\nexcept OSError as exc:\n    print(json.dumps({"triggered": True, "title": "日志文件不可读", "event": FILE + ": " + repr(exc)}, ensure_ascii=False))\n    raise SystemExit(0)\nif size < offset:\n    offset = 0\nhits = []\nwith open(FILE, "r", encoding="utf-8", errors="replace") as f:\n    f.seek(offset)\n    for line in f:\n        if KEY in line:\n            hits.append(line.strip()[:200])\n    offset = f.tell()\nif hits:\n    more = " (+" + str(len(hits) - 5) + " more)" if len(hits) > 5 else ""\n    print(json.dumps({"triggered": True, "title": "日志命中 " + KEY, "event": chr(10).join(hits[:5]) + more, "state": {"offset": offset}}, ensure_ascii=False))\nelse:\n    print(json.dumps({"triggered": False, "state": {"offset": offset}}, ensure_ascii=False))\n'
    }
  ];

  var KIND_META = {
    trigger: { color: "orange", text: "🔥 触发" },
    error:   { color: "red", text: "🔴 错误" },
    check:   { color: "default", text: "检查" },
    skipped: { color: "blue", text: "⏸ 冷却跳过" }
  };

  /* ---------- small controlled input helpers ---------- */
  function field(label, value, onChange, opts) {
    opts = opts || {};
    var input;
    if (opts.rows) {
      input = e(TextArea, { rows: opts.rows, value: value || "", placeholder: opts.ph || "",
        onChange: function (ev) { onChange(ev.target.value); } });
    } else if (opts.num) {
      input = e(InputNumber, { min: opts.min, value: value, style: { width: opts.w || 120 },
        onChange: function (v) { onChange(v); } });
    } else if (opts.sw) {
      input = e(Switch, { checked: !!value, onChange: function (v) { onChange(v); } });
    } else {
      input = e(Input, { value: value || "", placeholder: opts.ph || "",
        onChange: function (ev) { onChange(ev.target.value); } });
    }
    return e("div", { key: label, style: { marginBottom: 8 } },
      opts.inline ? input :
      e("div", null,
        e(Text, { type: "secondary", style: { fontSize: 12 } }, label),
        input));
  }

  /* ================= rule form modal ================= */
  function RuleFormModal(props) {
    var open = props.open, editing = props.editing, onClose = props.onClose, onSaved = props.onSaved;
    var st = React.useState({});
    var v = st[0], setV = st[1];
    var stSrc = React.useState("template");
    var source = stSrc[0], setSource = stSrc[1];
    var stTpl = React.useState("btc");
    var tplId = stTpl[0], setTplId = stTpl[1];
    var stP = React.useState({});
    var pv = stP[0], setPv = stP[1];
    var stS = React.useState(false);
    var setSaving = stS[1];
    var saving = stS[0];

    React.useEffect(function () {
      if (open) {
        setSource(editing ? "path" : "template");
        setPv({});
        setV(editing ? {
          name: editing.name, enabled: editing.enabled,
          interval: editing.interval_seconds, action: editing.action,
          channel: (editing.dispatch && editing.dispatch.channel) || "console",
          user_id: (editing.dispatch && editing.dispatch.user_id) || "default",
          session_id: (editing.dispatch && editing.dispatch.session_id) || "",
          cooldown: editing.cooldown_seconds,
          script_timeout: 60, timeout: 120,
          prompt_template: "Event fired: [{title}] {event}",
          notify_template: "Event: [{title}] {event}"
        } : {
          enabled: true, interval: 60, action: "agent",
          channel: "console", user_id: "default", cooldown: 600,
          script_timeout: 60, timeout: 120,
          prompt_template: "Event fired: [{title}] {event}",
          notify_template: "Event: [{title}] {event}"
        });
      }
    }, [open, editing]);

    function set(k) { return function (val) { var n = {}; n[k] = val; setV(Object.assign({}, v, n)); }; }

    function buildBody() {
      var body = {
        name: v.name, agent_id: "default",
        interval_seconds: v.interval || 60,
        action: v.action || "agent",
        prompt_template: v.prompt_template,
        notify_template: v.notify_template,
        channel: v.channel || "console", user_id: v.user_id || "default",
        session_id: v.session_id || null,
        cooldown_seconds: v.cooldown === undefined || v.cooldown === null ? 600 : v.cooldown,
        timeout_seconds: v.timeout || 120,
        script_timeout_seconds: v.script_timeout || 60,
        share_session: false, tool_safety: v.tool_safety !== false,
        dispatch_mode: "final", silent: false,
        enabled: v.enabled !== false
      };
      if (source === "template" && !editing) {
        var t = TEMPLATES.find(function (x) { return x.id === tplId; });
        var s = t.script;
        t.params.forEach(function (pr) {
          var val = (pv[pr.k] !== undefined && pv[pr.k] !== "") ? pv[pr.k] : pr.d;
          s = s.split(pr.k).join(val);
        });
        body.script_content = s;
      } else if (source === "paste") {
        body.script_content = v.script_content || "";
      } else if (source === "path") {
        body.script_path = v.script_path || (editing ? editing.script : "");
      }
      return body;
    }

    function submit(validateOnly) {
      if (!v.name) { message.error("名称必填"); return; }
      if (source === "paste" && !(v.script_content || "").trim()) { message.error("请粘贴脚本内容"); return; }
      if (source === "path" && !(v.script_path || "").trim()) { message.error("请填写脚本路径"); return; }
      setSaving(true);
      var body = buildBody();
      var url = editing ? ("/" + editing.id + "?validate_only=" + validateOnly) : ("/?validate_only=" + validateOnly);
      api(url, { method: editing ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
        .then(function (d) {
          var w = (d.warnings || []).filter(function (x) { return x.indexOf("validate-only") < 0; });
          message.success((validateOnly ? "校验通过" : "已保存") + (w.length ? ":" + w.join(";") : ""));
          if (!validateOnly) onSaved();
        })
        .catch(function (err) { message.error(String(err.message || err).slice(0, 300)); })
        .finally(function () { setSaving(false); });
    }

    if (!open) return null;

    var curTpl = TEMPLATES.find(function (t) { return t.id === tplId; }) || TEMPLATES[0];
    var checkerTabs = e(Tabs, {
      activeKey: source, onChange: setSource, size: "small",
      items: [
        { key: "template", label: "从模板", disabled: !!editing, children: e("div", null,
            e(Select, { style: { width: "100%", marginBottom: 8 }, value: tplId,
              onChange: function (x) { setTplId(x); },
              options: TEMPLATES.map(function (t) { return { value: t.id, label: t.name }; }) }),
            curTpl.params.map(function (pr) {
              return e("div", { key: pr.k, style: { marginBottom: 6 } },
                e(Text, { type: "secondary", style: { fontSize: 12 } }, pr.label),
                e(Input, { placeholder: pr.d, value: pv[pr.k] || "",
                  onChange: function (ev) { var n = {}; n[pr.k] = ev.target.value; setPv(Object.assign({}, pv, n)); } }));
            })
          ) },
        { key: "paste", label: "粘贴脚本", children: e(TextArea, { rows: 10,
            value: v.script_content || "",
            placeholder: "Python:读 EVENT_STATE,stdout 输出 {triggered:true, title, event, state}",
            onChange: function (ev) { set("script_content")(ev.target.value); } }) },
        { key: "path", label: "引用路径", children: e(Input, {
            value: v.script_path || (editing ? editing.script : ""),
            placeholder: "/abs/path/checker.py",
            onChange: function (ev) { set("script_path")(ev.target.value); } }) }
      ]
    });

    return e(Modal, {
      open: open, title: editing ? "编辑规则(热更新)" : "创建事件规则",
      width: 640, onCancel: onClose, footer: null, destroyOnClose: true,
    },
      e("div", { style: { maxHeight: "62vh", overflow: "auto", paddingRight: 4 } },
        e("div", { style: { fontWeight: 600, margin: "4px 0 8px" } }, "① 基本信息"),
        e("div", { style: { display: "flex", gap: 12, alignItems: "center" } },
          e("div", { style: { flex: 1 } }, field("名称", v.name, set("name"))),
          e(Space, { align: "center" }, e(Text, null, "启用"), e(Switch, { checked: v.enabled !== false, onChange: set("enabled") }))
        ),
        e("div", { style: { fontWeight: 600, margin: "10px 0 4px" } }, "② 检查器"),
        checkerTabs,
        e("div", { style: { display: "flex", gap: 12, alignItems: "center", marginTop: 6 } },
          e(Text, null, "检查间隔(秒,≥10)"),
          e(InputNumber, { min: 10, value: v.interval, style: { width: 110 }, onChange: set("interval") })
        ),
        e("div", { style: { fontWeight: 600, margin: "10px 0 4px" } }, "③ 动作"),
        e(Radio.Group, { value: v.action, onChange: function (ev) { set("action")(ev.target.value); } },
          e(Radio.Button, { value: "notify" }, "通知(不推理)"),
          e(Radio.Button, { value: "agent" }, "Agent 推理")),
        e("div", { style: { marginTop: 8 } },
          field("notify 模板({title} {event})", v.notify_template, set("notify_template"), { rows: 2, ph: "Event: [{title}] {event}" }),
          field("agent prompt 模板({title} {event})", v.prompt_template, set("prompt_template"), { rows: 2, ph: "Event fired: [{title}] {event}" }),
          e("div", { style: { display: "flex", gap: 8 } },
            e("div", { style: { flex: 1 } }, field("频道", v.channel, set("channel"))),
            e("div", { style: { flex: 1 } }, field("用户ID", v.user_id, set("user_id"))),
            e("div", { style: { flex: 1 } }, field("会话ID(空=独立)", v.session_id, set("session_id")))
          ),
          e("div", { style: { display: "flex", gap: 24 } },
            e(Space, { align: "center" }, e(Text, null, "静默(只跑不投)"), e(Switch, { checked: !!v.silent, onChange: set("silent") })),
            e(Space, { align: "center" }, e(Text, null, "工具自动审批"), e(Switch, { checked: v.tool_safety !== false, onChange: set("tool_safety") }))
          )
        ),
        e("div", { style: { fontWeight: 600, margin: "10px 0 4px" } }, "④ 高级"),
        e("div", { style: { display: "flex", gap: 16, flexWrap: "wrap" } },
          e(Space, { align: "center" }, e(Text, null, "冷却(秒)"), e(InputNumber, { min: 0, value: v.cooldown, style: { width: 100 }, onChange: set("cooldown") })),
          e(Space, { align: "center" }, e(Text, null, "脚本超时"), e(InputNumber, { min: 1, value: v.script_timeout, style: { width: 90 }, onChange: set("script_timeout") })),
          e(Space, { align: "center" }, e(Text, null, "推理超时"), e(InputNumber, { min: 1, value: v.timeout, style: { width: 90 }, onChange: set("timeout") }))
        ),
        e(Alert, { style: { marginTop: 10 }, type: "info", showIcon: false,
          message: "保存走注册关卡:语法检查 → 试跑(真实执行一次并初始化状态)→ 内容 hash 锚定;改脚本即重新校验。" })
      ),
      e("div", { style: { textAlign: "right", marginTop: 10 } },
        e(Space, null,
          e(Button, { onClick: onClose }, "取消"),
          e(Button, { onClick: function () { submit(true); }, loading: saving }, "仅校验"),
          e(Button, { type: "primary", onClick: function () { submit(false); }, loading: saving }, "保存")
        ))
    );
  }

  /* ================= runs drawer ================= */
  function RunsDrawer(props) {
    var rule = props.rule, onClose = props.onClose;
    var st = React.useState([]);
    var runs = st[0], setRuns = st[1];
    var st2 = React.useState(false);
    var showAll = st2[0], setShowAll = st2[1];

    React.useEffect(function () {
      if (rule) {
        api("/" + rule.id + "/runs?limit=200").then(function (d) { setRuns(d.runs || []); })
          .catch(function () { setRuns([]); });
      }
    }, [rule]);

    var shown = (runs || []).slice().reverse()
      .filter(function (r) { return showAll || r.kind === "trigger" || r.kind === "error"; });

    return e(Drawer, { open: !!rule, onClose: onClose, width: 480,
      title: rule ? "执行记录:" + rule.name : "" },
      e("div", { style: { marginBottom: 8 } },
        e(Space, { align: "center" },
          e(Text, null, "显示全部(含 检查/冷却跳过)"),
          e(Switch, { checked: showAll, onChange: setShowAll }))),
      shown.length === 0 ? e(Text, { type: "secondary" }, "暂无记录") : null,
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
        .then(function () { message.success("已执行一次检查"); load(); })
        .catch(function (err) { message.error(String(err.message || err)); });
    }
    function del(rule) {
      api("/" + rule.id, { method: "DELETE" }).then(load)
        .catch(function (err) { message.error(String(err.message || err)); });
    }

    var columns = [
      { title: "规则", dataIndex: "name",
        render: function (v, r) {
          return e(Space, { direction: "vertical", size: 0 },
            e(Space, { size: 6 },
              e(Badge, { status: !r.enabled ? "default" : (r.last_error ? "error" : "success") }),
              e("b", null, v),
              e(Tag, { color: r.action === "agent" ? "geekblue" : "green" }, r.action === "agent" ? "agent" : "notify")),
            r.last_error ? e(Text, { type: "danger", style: { fontSize: 12 } }, String(r.last_error).slice(0, 90)) : null);
        } },
      { title: "间隔", width: 70, render: function (_, r) { return e(Text, null, r.interval_seconds + "s"); } },
      { title: "运行/触发", width: 110, render: function (_, r) { return e(Text, null, "⟳" + r.run_count + " ▲" + r.trigger_count); } },
      { title: "上次运行", width: 150, render: function (_, r) { return e(Text, { type: "secondary" }, ts(r.last_run_at)); } },
      { title: "启用", width: 70, render: function (_, r) { return e(Switch, { checked: r.enabled, onChange: function (x) { toggle(r, x); } }); } },
      { title: "操作", width: 270, render: function (_, r) {
          return e(Space, { size: 2 },
            e(Button, { size: "small", onClick: function () { runNow(r); } }, "▶ 执行"),
            e(Button, { size: "small", onClick: function () { setRunsRule(r); } }, "记录"),
            e(Button, { size: "small", type: "link", onClick: function () { setEditing(r); setModalOpen(true); } }, "编辑"),
            e(Popconfirm, { title: "删除该规则?", onConfirm: function () { del(r); } },
              e(Button, { size: "small", type: "link", danger: true }, "删除")));
        } }
    ];

    return e("div", { style: { padding: 20 } },
      e("div", { style: { display: "flex", justifyContent: "space-between", marginBottom: 12 } },
        e("h2", { style: { margin: 0 } }, "⚡ 事件触发"),
        e(Button, { type: "primary", onClick: function () { setEditing(null); setModalOpen(true); } }, "+ 创建规则")),
      e(Table, {
        rowKey: "id", dataSource: rules, columns: columns, pagination: false,
        expandable: {
          expandedRowRender: function (r) {
            return e("div", { style: { fontSize: 12 } },
              e("div", null, "脚本: ", r.script, " (hash ", r.script_hash, ")"),
              e("div", null, "投递: ", JSON.stringify(r.dispatch), " · 冷却: ", r.cooldown_seconds, "s · state: ", JSON.stringify(r.state)));
          }
        }
      }),
      e(RuleFormModal, { open: modalOpen, editing: editing,
        onClose: function () { setModalOpen(false); },
        onSaved: function () { setModalOpen(false); load(); } }),
      e(RunsDrawer, { rule: runsRule, onClose: function () { setRunsRule(null); } })
    );
  }

  var BoltIcon = (H.antdIcons && H.antdIcons.BoltOutlined) ? H.antdIcons.BoltOutlined : "⚡";
  window.QwenPaw.menu.add(P, {
    id: "event-trigger.menu", label: "事件任务", route: "event-trigger.home",
    icon: BoltIcon, location: "primary.agentScoped", order: 60
  });
  window.QwenPaw.route.add(P, {
    id: "event-trigger.home", path: "/event-trigger", component: RulesPage
  });

  console.log("[event-trigger] frontend registered (v3 double-prefix-fixed)");
})();
