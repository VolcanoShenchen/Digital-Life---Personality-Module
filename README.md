# General_purpose_personality_plugin

AstrBot 私聊人格与表达插件，预览版本 `0.5.0`。

通过 AstrBot 正常聊天请求加入结构化角色资料、情境行为、语言习惯和回复策略，复用宿主的模型、历史、工具和消息发送。当前目标平台为 NapCat 经 AstrBot `aiocqhttp` 适配器接入的 QQ 私聊。

## 当前状态

- 已实现结构化人格配置、两种人格来源、管理员诊断、Vue 配置页面与完整安装包构建。
- 开发基线：AstrBot **4.29.4**、Python **3.12+**、内置 Agent。元数据暂限定 `==4.29.4`。
- 已完成141项本地测试、本地宿主重载、真实Edge模型生成与人工编辑回读；实际DeepSeek模型一次生成12段并校验通过，未发送QQ消息。聊天效果仍需试聊。
- 本版是供隔离测试的预览版。详细结果见 [验证记录](docs/VALIDATION.md)。

## 功能

- 单角色结构化资料：姓名、性别认同、年龄、职业、经历、世界观和边界。
- 性格拆分为核心特征、优点、缺点、价值观、恐惧、欲望、矛盾与自我评价。
- 情境行为：开心、难过、生气、疲惫、被夸奖、被批评、意见不同、道歉、拒绝等。
- 语言与回复策略：自称、称呼、词汇、句式、标点、幽默、追问、建议、套话控制。
- 两种来源：`plugin` 管理完整人格；`astrbot` 沿用当前宿主人格，仅补充表达。
- 双重作用域：必须同时匹配完整私聊 UMO 与机器人自身 QQ 号。
- 一条专属关系：可描述关系角色、阶段、称呼、共同经历、信任、冲突与修复方式。
- 管理员私聊命令 `/人格状态`，只展示注入判定，不显示完整资料。
- 安装后默认关闭；空会话名单或空机器人名单均不会生效。

- 可选今日日程模块：由所选AstrBot聊天模型结合角色设定和约束生成每日具体活动，时间线展示并支持单段编辑。异步生成、结构校验、去重、失败冷却和人工计划保护。
- 模型生成要求真正参与规划；旧 `persona` 日程模式按模型模式处理，不再使用代码固定活动生成。
- 日程模型请求消耗所选提供商额度，默认成功后当天复用，不在每条聊天时重复生成。
- 人工当前状态有有效期，可按字段优先覆盖日程，不进入稳定人格。

本版不含自动情绪成长、长期记忆、多角色、主动消息、分段发送或语音生图。日程规划调用模型但不执行工具和现实动作；生成质量与角色表达仍需实际试用。

## 配置入口

在 AstrBot WebUI 的插件详情中打开 `settings` 视图。先选择一级入口“人格模块”“日程模块”“当前状态”或“通用设置”；人格模块内再选择身份、性格、表达等子页。模块切换保留草稿，底部“保存全部配置”统一保存各模块设置。详见 [配置 WebUI](docs/WEBUI.md)。

也可使用 AstrBot 原生插件配置页。旧版 `character.*` 和 `expression.*` 字段仍可读取，并在加载时迁移到结构化区域，便于逐步调整。

## 开始测试

1. 核对目标 AstrBot 版本、Python 及 Agent 执行方式。
2. 上传完整 ZIP，或将插件目录放入 AstrBot 插件目录。
3. 打开 `settings` 视图或原生配置页，填写角色资料。
4. 填写完整私聊 UMO 与机器人自身 QQ 号。
5. 如需专属关系，同时填写关系目标会话和机器人。
6. 启用、保存并重载，私聊测试；管理员可发送 `/人格状态`。

安装详情、原因码和字段说明见 [安装说明](docs/INSTALL.md)。

`plugin` 模式要求角色姓名、身份背景和核心性格非空。请将目标 AstrBot 人格整理为必要基础规则，避免两处重复定义身份；插件不会自动覆盖宿主人格或工具说明。

## 名称与仓库

- 项目与展示名称：`General_purpose_personality_plugin`。
- AstrBot 内部标识及安装目录：`astrbot_plugin_digital_life_personality`。
- 远端：[VolcanoShenchen/Digital-Life---Personality-Module](https://github.com/VolcanoShenchen/Digital-Life---Personality-Module)。

当前日程实现位于 `feature/schedule-v0.4`，尚未推送。0.2.1曾推送至远端main；新版本发布与远端同步分别处理。

## 开发与构建

Python 3.12+：

```bash
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m unittest discover -s tests -v
python scripts/build_plugin.py --output dist/preview
python scripts/build_plugin.py --verify dist/preview/astrbot_plugin_digital_life_personality-v0.4.0.zip
```

前端使用 Vue 3 + Vite。首次构建需要 Node.js 20+ 与 pnpm：

```bash
pnpm install
pnpm run build
```

页面源码位于 `frontend/`，构建产物输出到 `views/settings/`。发行包只包含构建后的静态页面，不包含 Node 依赖；打包器会检查未构建的前端入口并拒绝生成安装包。

构建器按显式清单打包，并自动收录 Vite 生成的哈希资源，输出 ZIP 与 SHA-256。运行只依赖 Python 标准库和 AstrBot 自带 API；本仓库不包含 AstrBot、Node 或 QQ 登录环境。

## 文档

- [项目计划](docs/PLAN.md)
- [首版详细设计](docs/DESIGN_V0_1.md)
- [AstrBot 对接架构](docs/ARCHITECTURE.md)
- [验收方案](docs/ACCEPTANCE.md)
- [安装说明](docs/INSTALL.md)
- [配置 WebUI](docs/WEBUI.md)
- [字段拆分对照清单](docs/FIELD_MAPPING.md)
- [身份主控验收](docs/IDENTITY_AUTHORITY.md)
- [动态状态说明](docs/DYNAMIC_STATE.md)
- [今日日程说明](docs/SCHEDULE.md)
- [验证记录](docs/VALIDATION.md)
- [变更记录](CHANGELOG.md)
- [开发约定](CONTRIBUTING.md)

## 许可证

许可证待确定，公开发布前补充正式授权声明。当前交付为项目内部测试预览包。
