# 首版验证记录

## 版本与范围

- 插件版本：0.1.0，内部测试预览。
- 实现分支：feature/personality-v0.1。
- 官方参考：AstrBot v4.29.4，固定提交 `61335414433db721b3f7ecc93f90deafe0a59d78`。
- 本地解释器：Python 3.12.14。
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

## 尚未验证

- 用户云端的 AstrBot、Python、Agent 和模型组合。
- 在完整 AstrBot 中安装、识别配置、重载和管理员权限配置。
- QQ 实际消息收发、默认 LLM 禁用、发送失败与工具循环。
- 真实模型、图片、音频与流式端到端行为。
- 实际角色的语气、人格一致性与多轮对话效果。
- 其他 AstrBot 版本和第三方 Agent 路径。

这些项目不因核心与替身测试通过而转为已通过。预览包用于下一阶段隔离集成测试，不标为已完成 M2/M3/M4 的真实环境验收。

## 下一阶段需补充

AstrBot 版本、Python 版本、部署方式、Agent 执行器、流式设置、模型名称或提供商类型，以及一个测试私聊来源。不需要提供模型密钥。
