# AGENT_ISOLATION — v0.3:向 cron 对齐的 per-agent 隔离

- [ ] Repo/Engine/Manager 路径参数化确认(构造已接受任意目录,补 engine 持有 agent_id 用于 task name)
- [ ] per-agent 引擎注册表(懒创建 + workspace_dir 数据目录 + 迁移钩子)
- [ ] 路由改造:/api/events/{agent_id}/... 路径段分发(get_agent_for_request 同款逻辑)
- [ ] 自动迁移:全局 events.json 按 rule.agent_id 分发到各工作区(旧文件备份 .pre-migrate,脚本文件随迁+path 更新)
- [ ] UI:index.js 按 getSelectedAgentId 调新路径
- [ ] SKILL.md:新 API 路径 + "只管理自己工作区的任务"
- [ ] 验证:default 建任务→新路径;小幺 BTC 任务迁移落位;触发走通;旧路径 404
- [ ] README v0.3 架构段 + push
