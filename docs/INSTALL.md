# 0.1.0 安装与配置

本版供隔离测试。先核对 [验证记录](VALIDATION.md)，不要将本地测试通过理解为已经完成云端验证。

## 1. 环境与安装

开发接口基线为 AstrBot 4.29.4、Python 3.12+、内置 Agent 和 aiocqhttp 私聊。元数据目前精确限定 4.29.4。其他版本应先核对差异并测试，不能直接忽略版本检查当作兼容验证。

完整包名称为 `astrbot_plugin_digital_life_personality-v0.1.0.zip`。

- ZIP：在 AstrBot 插件管理页使用本地 ZIP 上传安装，具体入口以实际宿主界面为准。
- 手工安装：解压后确保插件根目录直接包含 `main.py`、`metadata.yaml` 和配置 Schema，目录放入 AstrBot 的插件目录，建议名为 `astrbot_plugin_digital_life_personality`。
- 完成后重载插件；如果宿主要求重启，按宿主提示操作。
- 本插件不需要额外模型密钥，也不修改 NapCat 配置。

实际云端容器或系统路径以现有 AstrBot 部署为准，不假设本机 Windows 路径适用于服务器。

## 2. 人格来源

推荐 `persona_source=plugin`，填写：

- `character.name`：角色称呼。
- `character.identity`：已确认的身份与背景。
- `character.personality`：性格、立场、偏好与缺点，尽量用具体行为描述。
- `character.boundaries`：可选边界与表达分歧的方式。

前三项在启用时必填。请整理目标会话的 AstrBot 原生人格，保留必要基础规则，避免再定义冲突身份。插件不会自动删除原有内容，也无法保证两套冲突人设同时有效。

如果需要继续使用 AstrBot 原生人格，选择 `astrbot` 模式，插件保存的角色字段不注入；表达与关系配置仍可生效。

## 3. 作用范围

两项必须同时满足：

1. `allowed_sessions`：完整私聊来源 UMO，可先私聊触发宿主，再在选择器中选取；也可使用 AstrBot 的 `/sid` 查看来源，手工填写完整值。
2. `allowed_bot_ids`：机器人自身 QQ 号，按字符串逐项填写；不要填聊天对象 QQ 号。

两份名单任一为空时都不注入。群聊即使被填入名单，也不注入。

AstrBot 4.29.4 的 UMO 是平台实例、消息类型与会话 ID 的组合，不包含机器人自身账号。因此机器人 QQ 号需另行约束。诊断状态也按平台实例、机器人和完整来源隔离。

## 4. 专属关系

首版支持一条可选关系：

- `relationship.target_session` 必须属于允许的私聊列表。
- `relationship.target_bot_id` 必须属于允许的机器人列表。
- `relationship.background` 是关系背景。
- `relationship.addressing` 是双方称呼和适用场景。

有关系内容时必须指定会话和机器人；二者同时命中才注入。其他允许会话只得到通用角色规则。没有填写关系时，不预设恋人、朋友或亲密程度。

## 5. 示例配置

以下只用于说明字段，不是默认人设或真实用户资料。示例中的 UMO、账号和角色均为占位内容，必须换成自己的测试环境。优先通过宿主配置界面编辑。

```json
{
  "enabled": true,
  "persona_source": "plugin",
  "allowed_sessions": ["qq-main:FriendMessage:10001"],
  "allowed_bot_ids": ["20001"],
  "character": {
    "name": "测试角色",
    "identity": "合成测试中的虚构角色。",
    "personality": "表达克制，熟悉后会轻轻吐槽，有自己的判断。",
    "boundaries": "不喜欢被催促，但愿意解释。"
  },
  "relationship": {
    "target_session": "qq-main:FriendMessage:10001",
    "target_bot_id": "20001",
    "background": "此处填写已确认的关系。",
    "addressing": "平时直呼名字。"
  },
  "expression": {
    "habits": "认真讨论时少用语气词，不每句话都叫名字。",
    "tone": "follow_character",
    "length": "adaptive",
    "actions": "none",
    "emoji": "occasional",
    "reduce_cliches": true,
    "extra": ""
  },
  "examples": "情境：普通闲聊\n用户：我刚回家。\n角色：路上顺利吗？我刚好也闲下来了。"
}
```

示例会引导语气和内容倾向，请按角色改写。示例中的虚构经历不能当作已确认事实。

文本总预算为 12,000 个 Unicode 字符，包含角色、关系、表达与示例文字。超过预算会拒绝采用配置，不静默截断。此限制不代表 token 数或费用。

## 6. 保存与生效

先填写资料、允许会话和机器人，再启用，保存并重载插件。首版在加载时生成配置快照；仅保存而未重载不保证立即生效。

新建配置默认为禁用。禁用但未填写人格是正常未配置状态；启用后缺少必填资料则诊断为无效配置。

配置由 AstrBot 保存，不存在本插件专用记忆库。插件自身不将聊天副本或完整角色资料写入诊断日志；宿主自身日志与历史行为由宿主配置决定。

## 7. `/人格状态`

仅 AstrBot 管理员在私聊中可查看。管理员身份需在 AstrBot 中配置；Git 提交者身份不等于机器人管理员身份。

命令显示当前配置与本会话注入判定，不显示完整人设、其他会话 ID 或原始聊天。

| 代码 | 含义与处理 |
| --- | --- |
| applied | 规则已加入本次模型请求，不代表模型已遵从或消息已送达 |
| not_observed | 重载后尚未观察到该会话的模型请求，或记录已被容量清理 |
| disabled | 未启用，填写配置后启用并重载 |
| no_allowed_sessions | 允许会话为空 |
| no_allowed_bots | 允许机器人为空 |
| session_not_allowed | 当前来源未在允许列表中 |
| bot_not_allowed | 当前机器人自身账号未在允许列表中 |
| unsupported_platform | 当前不是 aiocqhttp 平台 |
| not_private | 当前不是私聊 |
| missing_scope_identity | 宿主未提供完整的来源、平台或机器人标识 |
| invalid_config | 字段无效，参考显示的固定字段与错误码修改 |
| unsupported_system_prompt | 宿主提供了本版不支持的系统提示类型 |
| malformed_owned_block | 自有规则区块损坏，插件保留请求并跳过；检查其他提示重写与宿主路径 |
| scope_adapter_error | 状态入口无法读取宿主会话信息 |

`request_adapter_error` 只在固定内容的运行日志中提示，表示宿主事件/请求适配异常。本轮不成功注入，不代表模型或发送失败。

命令不触发默认模型回复。宿主可以修改命令前缀；其他插件自行调用模型的行为不由本插件控制。

## 8. 隔离试用与退出

先使用测试会话配置，确认一般聊天和状态命令，再测试工具、附件与流式。首次排障建议减少其他会重写人格或接管回复的插件，逐项确认组合。

退出测试可将 enabled 设为 false 后保存重载，或者在 AstrBot 插件管理中停用。插件不修改既有聊天历史；已生成的角色回复仍属于宿主历史，不会因停用自动消失。需要新会话时使用宿主会话管理能力。

预览版不包含自动远端同步、云端部署或数据迁移。
