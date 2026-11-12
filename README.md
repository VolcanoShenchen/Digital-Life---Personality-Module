# General_purpose_personality_plugin

AstrBot 私聊人格与表达插件，预览版本 `0.2.1`。

通过 AstrBot 正常聊天请求加入结构化角色资料、情境行为、语言习惯和回复策略，复用宿主的模型、历史、工具和消息发送。当前目标平台为 NapCat 经 AstrBot `aiocqhttp` 适配器接入的 QQ 私聊。

## 当前状态

- 已实现结构化人格配置、两种人格来源、管理员诊断、Vue 配置页面与完整安装包构建。
- 开发基线：AstrBot **4.29.4**、Python **3.12+**、内置 Agent。元数据暂限定 `==4.29.4`。
- 已完成 60 项本地测试、完整宿主启动/插件加载、Vue 页面发现及真实配置 API 烟测；QQ 收发、模型/工具/流式和角色效果仍待验证。
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

首版不含持久情绪、长期记忆、多角色、主动联系、生活日程、分段发送或语音生图。聊天中的短期承接依赖 AstrBot 提供的上下文。语气通过模型提示引导，效果需要实际试聊，规则本身会增加输入 token。

## 配置入口

在 AstrBot WebUI 的插件详情中打开 `settings` 视图。页面按区域组织全部字段，保存时严格校验；详见 [配置 WebUI](docs/WEBUI.md)。

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

内部标识用于宿主加载和配置文件，不更改项目名称。本地 Git 默认分支为 `main`，实现位于 `feature/personality-v0.1`；尚未推送。远端访问状态见项目计划。

## 开发与构建

Python 3.12+：

```bash
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m unittest discover -s tests -v
python scripts/build_plugin.py --output dist/preview
python scripts/build_plugin.py --verify dist/preview/astrbot_plugin_digital_life_personality-v0.2.0.zip
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
- [验证记录](docs/VALIDATION.md)
- [变更记录](CHANGELOG.md)
- [开发约定](CONTRIBUTING.md)

## 许可证

许可证待确定，公开发布前补充正式授权声明。当前交付为项目内部测试预览包。
