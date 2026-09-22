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
