# 验证记录

## 版本与范围

- 插件版本：0.2.1，内部测试预览。
- 实现分支：feature/personality-v0.1。
- 官方参考：AstrBot v4.29.4，固定提交 `61335414433db721b3f7ecc93f90deafe0a59d78`。
- 单元测试解释器：Python 3.12.14；E 盘宿主测试使用独立 Python 3.12.10。
- 本地宿主：官方 PyPI AstrBot 4.29.4，NapCat 4.18.42 便携 Node 包，Windows AMD64。
- 前端：Vue 3.5 + Vite 6，构建为 AstrBot `views/settings`。
- 静态工具：Ruff 0.14.10。

## 官方源码核对

以下为静态接口核对，不是完整 AstrBot 实例中的运行测试：

- [Python 约束](https://github.com/AstrBotDevs/AstrBot/blob/61335414433db721b3f7ecc93f90deafe0a59d78/pyproject.toml)：要求 Python >=3.12。
- [Star 基类](https://github.com/AstrBotDevs/AstrBot/blob/61335414433db721b3f7ecc93f90deafe0a59d78/astrbot/core/star/base.py)：配置构造签名与子类注册。
- [消息事件](https://github.com/AstrBotDevs/AstrBot/blob/61335414433db721b3f7ecc93f90deafe0a59d78/astrbot/core/platform/astr_message_event.py)：平台、机器人、私聊、管理员、停止事件及默认 LLM 禁用接口。
- [会话标识](https://github.com/AstrBotDevs/AstrBot/blob/61335414433db721b3f7ecc93f90deafe0a59d78/astrbot/core/platform/message_session.py)：UMO 不包含机器人 self_id，需额外约束。
- [请求结构](https://github.com/AstrBotDevs/AstrBot/blob/61335414433db721b3f7ecc93f90deafe0a59d78/astrbot/core/provider/entities.py)：只修改 system_prompt，保留其他请求字段。
- [插件可视化视图](https://docs.astrbot.app/dev/star/guides/plugin-pages.html)：`views/<name>/index.html` 与 `context.register_web_api()`。

## 本地检查

使用合成配置和 API 替身，不连接 QQ、不调用模型。

| 检查 | 结果 |
| --- | --- |
| unittest | 72 项通过：旧配置兼容、适配与 Schema、结构化提示、身份主控、WebUI、区块结构和安装包 |
| Ruff 静态检查与格式检查 | 通过；开发依赖固定为 0.14.10 |
| Vue 页面构建 | 通过；生成相对路径的哈希 JS/CSS 资源 |
| 完整 ZIP 构建与校验 | 通过显式清单、版本、默认值、CRC、相对资源路径和未构建前端检查 |
| 身份主控测试 | 通过；角色主控、技术身份披露、叠加兼容和模式冲突均有回归测试 |

## E 盘本地宿主验证

使用独立目录 E:\LinXiaozhi\Memory\local-test，未改动云端环境。

- AstrBot 4.29.4 从 E 盘工作目录启动，管理页面 http://127.0.0.1:6185/ 返回 HTTP 200；OneBot 6199 仅监听 127.0.0.1。
- 0.2.1 插件已加载，运行时报告版本 0.2.1；配置有效且启用。
- 当前本地配置为 `persona_source=plugin` + `persona_authority=character_owner`。
- 真实本地事件对象验证：目标私聊注入包含身份主控合同的提示；其他用户和其他机器人均被排除。
- 角色主控提示包含 `<identity_authority>`、`<host_compatibility>` 和 `<final_character_check>`，明确角色优先、宿主能力保留及技术问题披露规则。
- 人设林晚已导入并通过作用域验证：`local-napcat:FriendMessage:1046499622` + 机器人 `2142105127`，判定结果 `applied`。
- Vue 页面通过真实浏览器渲染，10 个分组导航均可点击切换；控制台无页面脚本异常。
- NapCat 4.18.42 官方便携包通过完整长度和 SHA-256，Node 22.11.0 预检通过；QQ 已登录，但真实模型和 OneBot 私聊效果仍需观察。

## 尚未验证

- 用户云端的 AstrBot、Python、Agent 和模型组合。
- 真实模型对“你是谁”“你是不是 AstrBot”“你是什么模型”等身份场景的回复质量。
- QQ 实际消息收发、工具循环、图片/音频和流式端到端行为。
- 其他后执行的人设重写插件与本插件的冲突行为。
- 其他 AstrBot 版本和第三方 Agent 路径。

这些项目不因核心、替身或本地宿主测试通过而转为全环境验收通过。
