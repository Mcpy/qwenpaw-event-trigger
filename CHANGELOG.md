# Changelog

## v0.3.10 (2026-10-20)

Fixed per issue [#1](https://github.com/Mcpy/qwenpaw-event-trigger/issues/1) (reported by BeiMu-new):

### Fixed
- **非 ASCII 检查输出乱码**:子进程 stdio 强制 UTF-8(`PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1`)——修复中文/cp936 locale 宿主上脚本输出被按 UTF-8 硬解成替换字符的问题(`protocol.py`)。
- **notify 投递到伪造句柄**:空 `session_id` 不再合成 `event:<rule_id>`(QQ 等频道会把它当投递句柄导致 404),改为透传空值,由频道回退到 `user_id` 句柄(`engine.py`)。
- 回归测试 `tests/test_issue1_fixes.py`(7 用例:env 注入 / 中文 round-trip / session_id 透传)。

> 注:频道层 `send_text` 吞掉投递失败(返回值被忽略)导致任务误报成功——属 QwenPaw core 层问题,已列入官方反馈清单。

## v0.3.9 (2026-10-19)

### Fixed
- **编辑任务保存被"请粘贴脚本内容"拦截**:编辑模式的校验规则漏改——`web/index.js` 中 `submit()` 的脚本内容校验未排除编辑模式,导致编辑已有任务改参数保存时报错。编辑模式本就不需要脚本内容(文件已存在,改脚本走"编辑脚本"弹窗),已修复为仅创建模式校验。

## v0.3.8 (2026-10-19)

### Changed
- skill 文档去版本化:移除"从某版本起 / 已退役"等兼容性与版本史描述,改为纯当前行为描述(给 agent 的文档只描述现状)。

## v0.3.7 (2026-10-19)

### Changed
- skill 文档同步 `script_rel` 引用注册与 PUT 换绑语义(中英双语)。

## v0.3.6 (2026-10-19)

### Added
- **`script_rel` 引用注册**:`POST /api/events/{agent_id}/` 支持用 `script_rel`(已存在于 `event_trigger/scripts/` 的 `.py` 裸文件名,如平台文件页手写)代替内联 `script_content`;两者互斥。
- `PUT` 支持 `script_rel` 换绑任务到另一个脚本(内容不改写,hash 重锚);不带脚本字段的更新完全不动文件。
- 安全校验:`script_rel` 仅允许目录下已有的 `.py` 裸文件名(防路径穿越/子目录/非 .py)。
- 冒烟测试 `tests/test_script_rel.py`(12 用例)。

## v0.3.5 (2026-10-19)

### Fixed
- 编辑表单默认停在 disabled 的"从模板"tab 导致"编辑脚本"按钮不显示。
- zh/en L10N 词条补齐与去重。

## v0.3.4 (2026-10-19)

### Changed
- 脚本编辑收口:列表"脚本"按钮移除,编辑表单"从脚本"tab 下改为"编辑脚本"按钮(弹出独立编辑器);编辑模式永不传 `script_content`(防覆盖文件)。
- 编辑器弹窗保存后关闭表单并刷新(防止表单旧 CONFIG 覆盖文件新值)。

## v0.3.x 之前(概要)

- **v0.3**:per-agent 隔离(任务/脚本/运行记录存于各 agent 工作区,API 按 agent_id 分发;v0.2 全局数据自动迁移)
- **v0.3.2**:脚本统一引擎托管(`event_trigger/scripts/`)、hash 完整性锁、注册关卡(语法→试跑→锚定)、脚本内 CONFIG 参数化、max_triggers、防抖滞回、五模板、双语技能
