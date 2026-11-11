# 首版验证记录

## 版本与范围

- 插件版本：0.1.0，内部测试预览。
- 实现分支：feature/personality-v0.1。
- 官方参考：AstrBot v4.29.4，固定提交 `61335414433db721b3f7ecc93f90deafe0a59d78`。
- 单元测试解释器：Python 3.12.14；E 盘宿主测试使用独立 Python 3.12.10。
- 本地宿主：官方 PyPI AstrBot 4.29.4，NapCat 4.18.42 便携 Node 包，Windows AMD64。
- 静态工具：Ruff 0.14.10。

## 官方源码核对

以下为静态接口核对，不是完整 AstrBot 实例中的运行测试：

- [Python 约束](https://github.com/AstrBotDevs/AstrBot/blob/61335414433db721b3f7ecc93f90deafe0a59d78/pyproject.toml)：要求 Python >=3.12。
- [Star 基类](https://github.com/AstrBotDevs/AstrBot/blob/61335414433db721b3f7ecc93f90deafe0a59d78/astrbot/core/star/base.py)：配置构造签名与子类注册。
- [消息事件](https://github.com/AstrBotDevs/AstrBot/blob/61335414433db721b3f7ecc93f90deafe0a59d78/astrbot/core/platform/astr_message_event.py)：平台、机器人、私聊、管理员、停止事件及默认 LLM 禁用接口。
- [会话标识](https://github.com/AstrBotDevs/AstrBot/blob/61335414433db721b3f7ecc93f90deafe0a59d78/astrbot/core/platform/message_session.py)：UMO 不包含机器人 self_id，需额外约束。
- [请求结构](https://github.com/AstrBotDevs/AstrBot/blob/61335414433db721b3f7ecc93f90deafe0a59d78/astrbot/core/provider/entities.py)：只修改 system_prompt，保留其他请求字段。

## 本地检查

使用合成配置和 API 替身，不连接 QQ、不调用模型。

| 检查 | 结果 |
| --- | --- |
| unittest | 49 项通过：28 核心、14 适配/Schema、2 区块结构回归、5 安装包 |
| Ruff 静态检查与格式检查 | 已运行并通过；开发依赖固定为 0.14.10 |
| 完整 ZIP 构建与校验 | 通过显式清单、版本、默认值与 CRC 检查，附 SHA-256 校验文件 |
| 独立只读代码审查 | 对照固定宿主源码核对；发现并修复损坏区块跨段删除问题，回归测试通过 |

测试重点：空白名单不生效；会话和机器人联合匹配；关系不跨对象注入；严格配置与预算；示例不作为历史写入；重复请求幂等；损坏/嵌套/交叉标记保留原文；请求其他字段不变；管理员显式二次校验；取消传播；诊断不包含原始配置或聊天；安装包拒绝缺项、改版号和意外运行数据。

本地可复现命令见项目 README。API 替身仅模拟公开接口形状，未执行完整 AstrBot 加载器、调度器或 QQ 适配器。

## E 盘本地宿主验证

使用独立目录 E:\LinXiaozhi\Memory\local-test，未改动云端环境。

- 官方 Python 3.12.10 嵌入式运行时与 AstrBot 4.29.4 wheel 安装到 E 盘，pip check 通过。
- AstrBot 从 E 盘工作目录启动，启动日志确认人格插件 0.1.0 成功加载，宿主生成插件配置文件。
- 管理页面 http://127.0.0.1:6185/ 返回 HTTP 200；管理服务和 OneBot 6199 都仅监听 127.0.0.1。
- 使用已安装的真实 AstrMessageEvent/ProviderRequest 类完成无网络烟测：人格和关系注入、重复请求、历史与附件引用保留、同 UMO 不同机器人拒绝、管理员事件停止及默认 LLM 禁用。
- 烟测的发送方法由无网络子类截获，未执行完整消息调度器、真实 QQ 传输或模型调用；不能据此声称私聊端到端通过。
- NapCat 4.18.42 官方便携包通过完整长度和官方 SHA-256，Node 22.11.0 预检通过；未登录 WebUI http://127.0.0.1:6099/webui/ 返回 HTTP 200。
- 通过本地 Dashboard API 登录检查，AstrBot 已发现 `settings` 插件视图；视图入口使用宿主登录态，不另起服务。
- WebUI 配置接口通过 51 项本地测试，覆盖读取、保存、无效配置拒绝和未认证拒绝。
- NapCat 测试 QQ 数据、配置、日志及进程级 AppData 均指向 E 盘；尚未扫码或启用反向 WS 客户端。

本地环境不放入 Git。实际记录位于该环境的 logs/astrbot-startup.log、logs/actual-api-smoke.json、logs/requirements-installed.txt 及 napcat/prepared-status.json，不包含在发布包中。

## 尚未验证

- 用户云端的 AstrBot、Python、Agent 和模型组合。
- 配置保存后的真实热重载、实际管理员账号的消息权限流程。
- QQ 实际消息收发、默认 LLM 禁用、发送失败与工具循环。
- 真实模型、图片、音频与流式端到端行为。
- 实际角色的语气、人格一致性与多轮对话效果。
- 其他 AstrBot 版本和第三方 Agent 路径。

这些项目不因核心与替身测试通过而转为已通过。预览包用于下一阶段隔离集成测试，不标为已完成 M2/M3/M4 的真实环境验收。

## 下一阶段需补充

AstrBot 版本、Python 版本、部署方式、Agent 执行器、流式设置、模型名称或提供商类型，以及一个测试私聊来源。不需要提供模型密钥。
