# 动态状态与稳定人格

版本：0.3.0。

## 当前处境为什么不再重复

`background.current_situation` 现在只保留为旧配置迁移资料，不会进入稳定人格提示。它不再代表“当前正在做什么”。长期项目或近期生活阶段请填写 `background.life_context`，页面会标注“非当前活动”。

当前活动要填写到 `dynamic_state.activity`，并同时填写作用域和有效时间。这样模型在有效窗口内可以知道当前状态，过期后不会继续把旧活动当作当前事实。

## 动态状态字段

| 字段 | 作用 |
| --- | --- |
| `dynamic_state.enabled` | 是否启用临时状态 |
| `dynamic_state.target_session` | 状态绑定的完整私聊 UMO |
| `dynamic_state.target_bot_id` | 状态绑定的机器人 QQ 号 |
| `dynamic_state.activity` | 当前在做什么 |
| `dynamic_state.location` | 当前所在位置，不是常住地 |
| `dynamic_state.mood` | 当前情绪 |
| `dynamic_state.energy` | 当前精力 |
| `dynamic_state.source` | `manual` 或人工确认的 `confirmed_event` |
| `dynamic_state.updated_at` | 状态确认/开始时间，必须带时区 |
| `dynamic_state.expires_at` | 状态失效时间，必须带时区 |

状态有效必须同时满足：插件启用、状态启用、有内容、当前时间在开始和截止时间之间、绑定会话和机器人匹配。读取 WebUI 或发送消息不会延长有效期。

过期后的状态只会停止注入，不会被解释为“活动已经完成”。没有新状态时，模型会被告知不要把历史回复或长期背景当成此刻活动，也不要为了让每次回答不同而编造新活动。

## WebUI 操作

打开插件详情页的 `settings` → `当前状态`：

1. 填写状态绑定的 UMO 和机器人 QQ 号。
2. 填写当前活动、位置、情绪和精力。
3. 选择来源。`confirmed_event` 仍要求人工确认，不会自动识别。
4. 设置开始和失效时间，页面按浏览器时区输入并保存为带时区 ISO 时间。
5. 可以用 30、60、120 分钟快捷按钮设置时间；按钮只修改草稿，不会自动启用或保存。
6. 保存后状态卡片每秒重新计算剩余时间；过期会显示“已过期”。

## 设计边界

稳定人格包含“生气时如何回应”等行为规则，这些规则不会证明角色现在正在生气。动态情绪只表示一条有来源和时效的临时状态。

动态状态通过 AstrBot `TextPart.mark_as_temp()` 作为当前请求的额外用户内容块发送，不写入对话历史。若目标宿主请求不支持临时内容块，插件会跳过该状态，保留稳定人格请求。

消息分段本版本暂不处理。当前连续气泡行为仍由 AstrBot 宿主的分段配置决定，详细限制见 [动静态与发送方案](STATE_AND_DELIVERY_PLAN.md)。
