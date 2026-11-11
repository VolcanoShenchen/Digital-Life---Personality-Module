# 0.2.0 人格字段拆分对照清单

本清单对应配置结构、Vue 配置页和提示词注入。新字段已可用，旧字段仍兼容。

## 一、基础身份

| 配置键 | 含义 | 状态 |
| --- | --- | --- |
| `profile.name` | 姓名 | 已实现，plugin 模式必填 |
| `profile.nickname` | 昵称或自称 | 已实现 |
| `profile.gender_identity` | 性别认同 | 已实现 |
| `profile.pronouns` | 代称 | 已实现 |
| `profile.age` | 年龄 | 已实现，文本可写数字或描述 |
| `profile.age_mode` | 固定、增长、角色时间线 | 已实现 |
| `profile.birth_date` | 出生日期 | 已实现 |
| `profile.species` | 物种 | 已实现 |
| `profile.nationality` | 国籍或地区 | 已实现 |
| `profile.native_language` | 母语 | 已实现 |
| `profile.timezone` | 所在时区 | 已实现 |
| `profile.location` | 所在地 | 已实现 |
| `profile.occupation` | 职业 | 已实现 |
| `profile.education` | 教育背景 | 已实现 |
| `profile.social_status` | 社会身份 | 已实现 |

`age_mode` 目前只作为角色资料说明注入，不自动计算当前年龄。出生日期不参与运行时年龄推算。

## 二、经历与世界

| 配置键 | 含义 | 状态 |
| --- | --- | --- |
| `background.identity` | 身份与背景 | 已实现，plugin 模式必填 |
| `background.family` | 家庭关系 | 已实现 |
| `background.childhood` | 童年经历 | 已实现 |
| `background.education_history` | 学习经历 | 已实现 |
| `background.work_history` | 工作经历 | 已实现 |
| `background.important_events` | 重要事件 | 已实现，列表 |
| `background.current_situation` | 当前处境 | 已实现 |
| `background.secrets` | 秘密 | 已实现，列表 |
| `background.world_setting` | 世界设定 | 已实现 |
| `background.known_facts` | 明确知道 | 已实现 |
| `background.unknown_facts` | 明确不知道 | 已实现 |

秘密目前不会自动隐藏或按触发条件解锁，只是提示模型不要随意主动提及；条件触发需要后续状态或记忆模块。

## 三、性格核心

| 配置键 | 含义 | 状态 |
| --- | --- | --- |
| `personality.core_traits` | 核心性格 | 已实现，plugin 模式必填之一 |
| `personality.positive_traits` | 优点 | 已实现 |
| `personality.flaws` | 缺点 | 已实现 |
| `personality.values` | 价值观 | 已实现 |
| `personality.dislikes` | 偏好与反感 | 已实现 |
| `personality.fears` | 恐惧与担忧 | 已实现 |
| `personality.desires` | 欲望与目标 | 已实现 |
| `personality.insecurities` | 不安全感 | 已实现 |
| `personality.pride` | 自豪之处 | 已实现 |
| `personality.contradictions` | 性格矛盾 | 已实现 |
| `personality.self_image` | 自我评价 | 已实现 |
| `personality.view_of_others` | 对他人的看法 | 已实现 |
| `personality.changeability` | 性格稳定程度 | 已实现为资料说明 |
| `personality.social_temperature` | 社交温度 | 已实现为资料说明 |
| `personality.legacy_summary` | 旧版性格补充 | 已实现，兼容迁移 |

`changeability` 和 `social_temperature` 目前只是提示信息，没有独立的状态机或关系成长算法。

## 四、情境行为

| 配置键 | 含义 | 状态 |
| --- | --- | --- |
| `behavior.when_happy` | 开心时 | 已实现 |
| `behavior.when_sad` | 难过时 | 已实现 |
| `behavior.when_angry` | 生气时 | 已实现 |
| `behavior.when_tired` | 疲惫时 | 已实现 |
| `behavior.when_embarrassed` | 尴尬时 | 已实现 |
| `behavior.when_anxious` | 焦虑时 | 已实现 |
| `behavior.when_bored` | 无聊时 | 已实现 |
| `behavior.when_confused` | 困惑时 | 已实现 |
| `behavior.when_praised` | 被夸奖时 | 已实现 |
| `behavior.when_criticized` | 被批评时 | 已实现 |
| `behavior.when_disagrees` | 意见不同时 | 已实现 |
| `behavior.when_apologizing` | 道歉时 | 已实现 |
| `behavior.when_refusing` | 拒绝时 | 已实现 |
| `behavior.when_ignored` | 被冷落时 | 已实现 |
| `behavior.when_topic_changes` | 换话题时 | 已实现 |
| `behavior.when_memory_missing` | 缺少记忆时 | 已实现 |

这些规则全部进入稳定人格提示；是否在某一轮真正适用仍由模型依据上下文判断，插件不做情绪分类。

## 五、说话方式

| 配置键 | 含义 | 状态 |
| --- | --- | --- |
| `speech.first_person` | 自称 | 已实现 |
| `speech.second_person` | 对用户的称呼 | 已实现 |
| `speech.vocabulary` | 常用词汇与句式 | 已实现 |
| `speech.avoided_words` | 避免用词 | 已实现，列表 |
| `speech.sentence_length` | 句子长度 | 已实现 |
| `speech.punctuation` | 标点习惯 | 已实现 |
| `speech.question_frequency` | 提问频率 | 已实现 |
| `speech.emoji_frequency` | 表情频率 | 已实现 |
| `speech.humor_style` | 幽默方式 | 已实现 |
| `speech.affection_style` | 表达在意 | 已实现 |
| `speech.disagreement_style` | 表达分歧 | 已实现 |
| `speech.apology_style` | 道歉方式 | 已实现 |
| `speech.refusal_style` | 拒绝方式 | 已实现 |
| `speech.greeting_style` | 打招呼 | 已实现 |
| `speech.goodbye_style` | 结束话题 | 已实现 |
| `speech.correction_style` | 纠正方式 | 已实现 |
| `speech.topic_transition` | 话题转换 | 已实现 |
| `speech.silence_tolerance` | 沉默与留白 | 已实现 |
| `speech.habits` | 固定说话习惯 | 已实现 |
| `speech.tone` | 基础语气 | 已实现 |
| `speech.extra` | 补充表达 | 已实现 |

`sentence_length` 与 `question_frequency` 是提示偏好，不会在发送前机械截断或删除问句。

## 六、回复策略

| 配置键 | 含义 | 状态 |
| --- | --- | --- |
| `response.length` | 默认回复长度 | 已实现 |
| `response.answer_first` | 先直接回答 | 已实现 |
| `response.ask_followup` | 追问频率 | 已实现 |
| `response.offer_advice` | 建议策略 | 已实现 |
| `response.repeat_user` | 复述用户内容 | 已实现为提示说明 |
| `response.handle_unknown` | 不知道时怎么说 | 已实现 |
| `response.avoid_cliches` | 减少固定套话 | 已实现 |
| `response.avoid_psychological_analysis` | 避免擅自心理分析 | 已实现 |
| `response.avoid_over_affection` | 避免过度亲密 | 已实现 |
| `response.reduce_cliches` | 减少重复安慰 | 已实现，兼容旧设置 |

## 七、动作与场景

| 配置键 | 含义 | 状态 |
| --- | --- | --- |
| `roleplay.action_style` | 无、偶尔、场景化 | 已实现 |
| `roleplay.action_format` | 括号、短旁白、自然融入 | 已实现为提示说明 |
| `roleplay.environment_detail` | 环境细节 | 已实现为提示说明 |
| `roleplay.inner_monologue` | 内心独白 | 已实现为提示说明 |
| `roleplay.sensory_detail` | 感官细节 | 已实现为提示说明 |

场景动作仍由模型生成，插件不会替用户决定动作或把旁白转成图片。

## 八、边界保护

| 配置键 | 含义 | 状态 |
| --- | --- | --- |
| `boundaries.uncomfortable_topics` | 不适合主动讨论 | 已实现 |
| `boundaries.forbidden_actions` | 不会声称完成的行为 | 已实现 |
| `boundaries.refusal_level` | 拒绝强度 | 已实现 |
| `boundaries.privacy_rules` | 隐私边界 | 已实现 |
| `boundaries.reality_claims` | 现实行为边界 | 已实现 |
| `boundaries.memory_claims` | 记忆边界 | 已实现 |
| `boundaries.tool_claims` | 工具结果边界 | 已实现 |
| `boundaries.role_integrity` | 角色完整性 | 已实现 |
| `boundaries.roleplay` | 场景扮演边界 | 已实现 |

这些是提示规则，不是硬编码过滤器；无法保证模型绝对不违反，但会明确要求它不编造工具执行、记忆和现实行为。

## 九、专属关系

| 配置键 | 含义 | 状态 |
| --- | --- | --- |
| `relationship.target_session` | 目标会话 UMO | 已实现 |
| `relationship.target_bot_id` | 目标机器人 QQ | 已实现 |
| `relationship.role` | 关系角色 | 已实现 |
| `relationship.stage` | 关系阶段 | 已实现 |
| `relationship.duration` | 认识时长 | 已实现 |
| `relationship.background` | 关系背景 | 已实现 |
| `relationship.addressing` | 角色如何称呼用户 | 已实现 |
| `relationship.addressing_for_character` | 用户如何称呼角色 | 已实现 |
| `relationship.shared_history` | 共同经历 | 已实现，列表 |
| `relationship.shared_interests` | 共同兴趣 | 已实现，列表 |
| `relationship.trust_level` | 信任程度 | 已实现 |
| `relationship.intimacy_boundary` | 亲密边界 | 已实现 |
| `relationship.sensitive_topics` | 敏感话题 | 已实现，列表 |
| `relationship.conflict_style` | 冲突处理 | 已实现 |
| `relationship.repair_style` | 关系修复 | 已实现 |

关系资料只在 UMO 与机器人同时匹配时注入，不自动继承到其他会话。

## 十、对话示例与动态状态

| 内容 | 状态 |
| --- | --- |
| `examples` 多行表达示例 | 已实现，仍为文本 |
| 多条示例结构化列表 | 未实现，待后续 |
| `state.current_mood` 等动态状态 | 未实现，待独立模块 |
| 长期记忆与自动学习 | 未实现，待独立模块 |

当前动态承接完全依赖 AstrBot 已提供的聊天上下文。插件不保存跨会话情绪、好感度或未完成话题。

## 旧字段迁移对照

| 旧字段 | 新位置 |
| --- | --- |
| `character.name` | `profile.name` |
| `character.identity` | `background.identity` |
| `character.personality` | `personality.legacy_summary` |
| `character.boundaries` | `boundaries.roleplay` |
| `expression.habits` | `speech.habits` |
| `expression.tone` | `speech.tone` |
| `expression.length` | `response.length` |
| `expression.actions` | `roleplay.action_style` |
| `expression.emoji` | `speech.emoji_frequency` |
| `expression.reduce_cliches` | `response.reduce_cliches` |
| `expression.extra` | `speech.extra` |

迁移只发生在内存配置快照，不自动改写配置文件。旧字段仍会参与必填校验，以保证已有配置不被突然判为无效。
