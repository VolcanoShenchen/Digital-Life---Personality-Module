# General_purpose_personality_plugin

面向 AstrBot 的通用人格与回复表达插件。当前主要使用场景为 AstrBot + NapCat 的 QQ 私聊。

## 项目状态

当前处于方案设计与仓库基础建设阶段。仓库目前只包含规划文档和 Git 基础配置，尚不具备 AstrBot 插件的安装和运行能力。

- 项目名称已确定为 `General_purpose_personality_plugin`。
- 使用全新设计，不依赖其他陪伴插件的实现、功能或数据结构。
- 本地 Git 默认分支为 `main`；远端仓库暂不配置。
- 业务代码在相应方案确认后编写。

## 目标

- 配置角色身份、性格、价值观、关系与相处方式。
- 调整语言习惯、表达节奏、动作描写及示例对话。
- 通过 AstrBot 的官方流程接入模型、会话与消息处理。
- 通过实际试聊评估人格一致性、回应针对性与表达自然程度。

## 规划文档

- [项目计划](docs/PLAN.md)
- [开发约定](CONTRIBUTING.md)

首版功能范围和宿主兼容范围仍需在设计与验证阶段明确。状态、长期记忆、主动联系等模块分别评估后再纳入开发。

## 当前仓库内容

```text
.gitignore
.gitattributes
README.md
CONTRIBUTING.md
docs/
  PLAN.md
```

## 许可证

许可证待确定，公开发布前补充正式授权声明。
