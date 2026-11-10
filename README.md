# General_purpose_personality_plugin

AstrBot 私聊人格与表达插件，预览版本 `0.1.0`。

通过 AstrBot 正常聊天请求加入可配置的角色、语言习惯和示例，复用宿主的模型、历史、工具和消息发送。当前目标平台为 NapCat 经 AstrBot `aiocqhttp` 适配器接入的 QQ 私聊。

## 当前状态

- 已实现首版代码、配置面板、管理员诊断、关键测试与完整安装包构建。
- 固定源码核对基线：AstrBot **4.29.4**、Python **3.12+**、内置 Agent。元数据暂限定 `==4.29.4`，不据此声称已在完整宿主中运行过。
- 已完成本地逻辑和 API 替身测试；真实 AstrBot 加载、QQ 收发、模型/工具/流式和对话效果尚待验证。
- 首版是供隔离测试的预览版。详细结果见 [验证记录](docs/VALIDATION.md)。

## 功能

- 单角色：身份、性格、价值观、偏好和边界均可配置。
- 两种来源：`plugin` 管理完整人格；`astrbot` 沿用当前宿主人格，仅调整表达。
- 语气、闲聊长度、动作描写、表情、说话习惯和对话示例。
- 双重作用域：必须同时匹配完整私聊 UMO 与机器人自身 QQ 号。
- 一条专属关系：同时绑定指定私聊与机器人，其他会话不会继承。
- 管理员私聊命令 `/人格状态`，只展示注入判定，不显示完整资料。
- 安装后默认关闭；空会话名单或空机器人名单均不会生效。

首版不含持久情绪、长期记忆、多角色、主动联系、生活日程、分段发送或语音生图。聊天中的短期承接依赖 AstrBot 提供的上下文。语气通过模型提示引导，效果需要实际试聊，规则本身会增加输入 token。

## 开始测试

1. 核对目标 AstrBot 版本、Python 及 Agent 执行方式。
2. 上传完整 ZIP，或将插件目录放入 AstrBot 插件目录。
3. 在插件配置页选择人格来源，填写角色资料。
4. 填写 `allowed_sessions` 完整私聊 UMO 及 `allowed_bot_ids` 机器人 QQ 号。
5. 如需专属关系，同时填写 `relationship.target_session` 和 `relationship.target_bot_id`。
6. 启用、保存并重载，私聊测试；管理员可发送 `/人格状态`。

安装详情、示例配置和原因码见 [安装说明](docs/INSTALL.md)。

`plugin` 模式要求角色称呼、身份和性格非空。请将目标 AstrBot 人格整理为必要基础规则，避免两处重复定义身份；插件不会自动覆盖宿主人格或工具说明。

## 名称与仓库

- 项目与展示名称：`General_purpose_personality_plugin`。
- AstrBot 内部标识及安装目录：`astrbot_plugin_digital_life_personality`。
- 远端：[VolcanoShenchen/Digital-Life---Personality-Module](https://github.com/VolcanoShenchen/Digital-Life---Personality-Module)。

内部标识用于宿主加载和配置文件，不更改项目名称。本地 Git 默认分支为 `main`，实现位于 `feature/personality-v0.1`；尚未推送。远端访问状态见项目计划。

## 开发与构建

在 Python 3.12+ 环境中执行：

```bash
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m unittest discover -s tests -v
python scripts/build_plugin.py
python scripts/build_plugin.py --verify dist/astrbot_plugin_digital_life_personality-v0.1.0.zip
```

构建器使用显式文件清单，输出 ZIP 和 SHA-256 校验文件。默认输出已存在时会拒绝覆盖，请选择新的 `--output` 目录。

运行只依赖 Python 标准库及 AstrBot 自带 API；本仓库不包含 AstrBot 或 QQ 登录环境。

## 文档

- [项目计划](docs/PLAN.md)
- [首版详细设计](docs/DESIGN_V0_1.md)
- [AstrBot 对接架构](docs/ARCHITECTURE.md)
- [验收方案](docs/ACCEPTANCE.md)
- [安装说明](docs/INSTALL.md)
- [验证记录](docs/VALIDATION.md)
- [变更记录](CHANGELOG.md)
- [开发约定](CONTRIBUTING.md)

## 许可证

许可证待确定，公开发布前补充正式授权声明。当前交付为项目内部测试预览包。
