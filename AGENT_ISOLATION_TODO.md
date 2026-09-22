# AGENT_ISOLATION — v0.3:向 cron 对齐的 per-agent 隔离

- [x] Repo/Engine/Manager 路径参数化(Engine 加 agent_id,task name = event-trigger:{agent}:{rule})
- [x] per-agent 引擎注册表(plugin._bundles 懒创建;单例守卫退役)
- [x] 路由改造:/api/events/{agent_id}/... 13 端点;全局资源(templates/protocol)保持 unscoped
- [x] 自动迁移:eager(启动时 loaded agents)+ lazy(bundle 首访);归档判定移至 startup;旧文件已归档 .pre-migrate
- [x] UI:index.js api() 按 agentId() 分流(templates/protocol 除外)
- [x] SKILL.md:新 API 路径 + agent-scoped 说明
- [x] 验证:BTC 任务迁入小幺工作区(脚本 path 已更新);run_now 765ms 走通;300s 循环 ok;旧 events.json 归档
- [x] README v0.3 段 + push(v0.3.0,zip 已发)
- [ ] 遗留:run_now 765ms 那次 fire 完整性(推理推送)待小幺侧确认;市场 zip 更新
- [x] 9/22 UI 对齐:agent 切换自动刷新(平台无插件页 agent-changed 事件,轮询 getSelectedAgentId 800ms 权宜;切 agent 时关弹窗+重拉)
- [ ] **官方机制记录(供反馈/未来对齐)**:平台内置页面(cron/inbox)刷新靠 zustand 全局 store(`selectedAgent`,`setSelectedAgent` 内调 `_e.refresh()` 重求值菜单;store 未挂 window,插件不可订阅;全局 CustomEvent 仅 qwenpaw:sidebar-new-chat / sidebar-select-session)。**正解诉求**:插件页面需要 agent 生命周期事件(window 事件或 route component props 传 agentId/key)——与 task_tracker、URL 上传、workspace-service 注册一起构成 #7939 后续反馈包
