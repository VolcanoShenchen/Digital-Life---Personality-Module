# 验证记录

## 版本与范围

- 插件版本：0.2.0，内部测试预览。
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
| unittest | 60 项通过：28 项旧配置兼容、15 项适配与 Schema、8 项结构化提示、2 项区块结构、7 项安装包 |
| Ruff 静态检查与格式检查 | 通过；开发依赖固定为 0.14.10 |
| Vue 页面构建 | 通过；生成 `index.html` 与带哈希的 JS/CSS 资源 |
| 完整 ZIP 构建与校验 | 通过显式清单、版本、默认值、CRC 与未构建前端检查，附 SHA-256 |
| 独立只读代码审查 | 对照固定宿主源码核对；已修复损坏区块跨段删除问题并保留回归测试 |

测试重点：

- 结构化身份、性格、情境行为、表达与关系字段确实进入提示，且按区块分隔。
- 旧版 `character.*`、`expression.*` 配置可加载并映射到新字段。
- 关系字段只对目标会话和目标机器人生效。
- 空白名单不生效；会话和机器人联合匹配；严格类型、枚举、必填与 12,000 字符预算。
- 示例不作为历史写入；重复请求幂等；损坏/嵌套/交叉标记保留原文。
- 请求其他字段不变；管理员显式二次校验；取消传播。
- 诊断不包含原始配置或聊天。
- WebUI 读取、保存、无效配置拒绝和未认证拒绝。
- 安装包拒绝缺项、改版号、未构建前端和意外运行数据。

本地可复现命令见项目 README。API 替身仅模拟公开接口形状，未执行完整 AstrBot 加载器、调度器或 QQ 适配器。

## E 盘本地宿主验证

使用独立目录 E:\LinXiaozhi\Memory\local-test，未改动云端环境。

- 官方 Python 3.12.10 嵌入式运行时与 AstrBot 4.29.4 wheel 安装到 E 盘，pip check 通过。
- AstrBot 从 E 盘工作目录启动，管理页面 http://127.0.0.1:6185/ 返回 HTTP 200；管理服务和 OneBot 6199 仅监听 127.0.0.1。
- 使用已安装的真实 AstrMessageEvent/ProviderRequest 类完成无网络烟测：人格和关系注入、重复请求、历史与附件引用保留、同 UMO 不同机器人拒绝、管理员事件停止及默认 LLM 禁用。
- 烟测的发送方法由无网络子类截获，未执行完整消息调度器、真实 QQ 传输或模型调用。
- NapCat 4.18.42 官方便携包通过完整长度和官方 SHA-256，Node 22.11.0 预检通过；未登录 WebUI http://127.0.0.1:6099/webui/ 返回 HTTP 200。
- 反向 WebSocket 配置已启用并指向 `ws://127.0.0.1:6199/ws`，但 QQ 尚未登录，实际 OneBot 建连未验证。
- 通过本地 Dashboard API 登录检查，AstrBot 已发现 `settings` 视图；插件设置 API 可返回 `config` 与 `summary`。
- 0.2.0 的 Vue 页面已同步到本地宿主，旧手写页面资源已清理。

本地环境不放入 Git。宿主日志、实际 API 烟测和安装版本清单位于该环境 `logs/` 与 `napcat/prepared-status.json`，不包含在发布包中。

## 尚未验证

- 用户云端的 AstrBot、Python、Agent 和模型组合。
- 浏览器中的 Vue 页面交互、保存后配置文件落盘及宿主热重载。
- QQ 实际消息收发、默认 LLM 禁用、发送失败与工具循环。
- 真实模型、图片、音频与流式端到端行为。
- 实际角色的语气、人格一致性与多轮对话效果。
- 其他 AstrBot 版本和第三方 Agent 路径。

这些项目不因核心与替身测试通过而转为已通过。预览包用于下一阶段隔离集成测试。

## 下一阶段需补充

AstrBot 版本、Python 版本、部署方式、Agent 执行器、流式设置、模型名称或提供商类型，以及一个测试私聊来源。不需要提供模型密钥。
