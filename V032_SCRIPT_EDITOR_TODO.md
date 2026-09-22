# V032_SCRIPT_EDITOR — 统一脚本托管 + UI 脚本编辑器

- [x] 方案确认:script_path 模式退役(零使用者),一切脚本托管于 workspace event_trigger/scripts/
- [x] 后端:script_path 移除;describe 增 script_rel(相对 workspace_dir)+ managed
- [x] 前端:创建表单重构(模板/粘贴+上传);path tab 移除
- [x] 前端:ScriptModal(平台 file-content API,X-Agent-Id 头,If-Match,409 处理,预览/编辑切换)
- [x] 前端:保存后前端 sha256 前 12 位对比 script_hash → 引导 enable 闭环(实测吻合 48f7dff49c11)
- [x] SKILL.md / README:script_path 退役说明
- [x] 验证:describe/script_rel ✓;平台 API 读/写/409 全通过;hash 对比吻合;ScriptModal 浏览器交互待用户验收;commit+push+zip
