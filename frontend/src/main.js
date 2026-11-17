import { createApp, reactive, ref, computed, onMounted, onUnmounted, h } from "vue";
import "./style.css";

const bridge = window.AstrBotPluginView;

const list = (value) => (Array.isArray(value) ? [...value] : []);

function unwrapResponse(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("服务端返回了无效响应");
  }
  if (value.status === "error") throw new Error(value.message || "请求失败");
  const result = value.status === "ok" && Object.hasOwn(value, "data") ? value.data : value;
  if (!result || typeof result !== "object" || Array.isArray(result)) {
    throw new Error("服务端返回了无效数据");
  }
  return result;
}

function zonedClock(now, timezone) {
  try {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    }).formatToParts(new Date(now));
    const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return { date: `${values.year}-${values.month}-${values.day}`, time: `${values.hour}:${values.minute}` };
  } catch { return null; }
}

function currentSchedule(today, timezone, now) {
  const local = zonedClock(now, today?.timezone || timezone);
  if (!local) return { reason: "invalid_timezone", slot: null, date: "", time: "" };
  if (!today || !Array.isArray(today.slots)) return { ...local, reason: "no_schedule", slot: null };
  if (today.date !== local.date) return { ...local, reason: "different_day", slot: null };
  const slot = today.slots.find((item) => item.start <= local.time && local.time < item.end) || null;
  return { ...local, reason: slot ? "active" : "gap", slot };
}

const blankConfig = () => ({
  enabled: false,
  persona_source: "plugin",
  persona_authority: {
    mode: "overlay",
    suppress_generic_assistant_identity: true,
    allow_technical_identity_disclosure: true,
  },
  allowed_sessions: [],
  allowed_bot_ids: [],
  dynamic_state: {
    enabled: false, target_session: "", target_bot_id: "",
    activity: "", location: "", mood: "", energy: "", source: "manual",
    updated_at: "", expires_at: "",
  },
  schedule: {
    enabled: false, auto_generate: true, timezone: "Asia/Shanghai",
    generation_rule: "结合角色身份、性格、兴趣和近期背景生成自然且有变化的今日生活安排，遵守作息与固定时段。",
    template_lines: [], allow_manual_override: true, max_segments: 12,
    generation_mode: "llm", provider_id: "", model_timeout: 90, retry_cooldown: 900,
    wake_time: "07:30", sleep_time: "23:00",
    work_start: "09:00", work_end: "17:30", workdays: ["1", "2", "3", "4", "5"],
    work_location: "", home_location: "",
  },
  profile: {
    name: "", nickname: "", gender_identity: "", pronouns: "", age: "", age_mode: "fixed",
    birth_date: "", species: "", nationality: "", native_language: "", timezone: "",
    location: "", occupation: "", education: "", social_status: "",
  },
  background: {
    identity: "", family: "", childhood: "", education_history: "", work_history: "",
    important_events: [], current_situation: "", life_context: "", secrets: [], world_setting: "",
    known_facts: "", unknown_facts: "",
  },
  personality: {
    core_traits: [], positive_traits: [], flaws: [], values: [], dislikes: [], fears: [],
    desires: [], insecurities: [], pride: [], contradictions: [], self_image: "",
    view_of_others: "", changeability: "stable", social_temperature: "slow", legacy_summary: "",
  },
  behavior: {
    when_happy: "", when_sad: "", when_angry: "", when_tired: "", when_embarrassed: "",
    when_anxious: "", when_bored: "", when_confused: "", when_praised: "",
    when_criticized: "", when_disagrees: "", when_apologizing: "", when_refusing: "",
    when_ignored: "", when_topic_changes: "", when_memory_missing: "",
  },
  relationship: {
    target_session: "", target_bot_id: "", role: "", stage: "", duration: "", background: "",
    addressing: "", addressing_for_character: "", shared_history: [], shared_interests: [],
    trust_level: "", intimacy_boundary: "", sensitive_topics: [], conflict_style: "", repair_style: "",
  },
  speech: {
    first_person: "", second_person: "", vocabulary: "", avoided_words: [],
    sentence_length: "adaptive", punctuation: "", question_frequency: "necessary",
    emoji_frequency: "occasional", humor_style: "", affection_style: "",
    disagreement_style: "", apology_style: "", refusal_style: "", greeting_style: "",
    goodbye_style: "", correction_style: "", topic_transition: "", silence_tolerance: "",
    habits: "", tone: "follow_character", extra: "",
  },
  response: {
    length: "adaptive", answer_first: true, ask_followup: "necessary",
    offer_advice: "when_requested", repeat_user: false,
    handle_unknown: "自然承认不知道，不把猜测说成事实。", avoid_cliches: true,
    avoid_psychological_analysis: true, avoid_over_affection: true, reduce_cliches: true,
  },
  roleplay: {
    action_style: "none", action_format: "short_narration", environment_detail: "light",
    inner_monologue: false, sensory_detail: false,
  },
  boundaries: {
    uncomfortable_topics: [], forbidden_actions: [], refusal_level: "clear", privacy_rules: "",
    reality_claims: "不要把未知的现实行为说成已经完成。",
    memory_claims: "不要把示例、推测或缺失上下文当作真实记忆。",
    tool_claims: "不要把计划或建议说成工具已经执行。",
    role_integrity: "不要为了迎合用户随意改变已确认的核心身份。", roleplay: "",
  },
  examples: "",
});

function mergeDeep(target, source) {
  if (!source || typeof source !== "object") return target;
  Object.keys(source).forEach((key) => {
    if (Array.isArray(source[key])) target[key] = list(source[key]);
    else if (source[key] && typeof source[key] === "object") target[key] = mergeDeep(target[key] || {}, source[key]);
    else if (source[key] !== undefined) target[key] = source[key];
  });
  return target;
}

function normalizeScheduleMode(config) {
  if (config.schedule?.generation_mode === "persona") {
    config.schedule.generation_mode = "llm";
    if (["按模板生成；不凭空添加未配置的现实事件。", "根据角色职业、常住地和作息生成；模板为可选固定安排。"].includes(config.schedule.generation_rule)) {
      config.schedule.generation_rule = blankConfig().schedule.generation_rule;
    }
  }
  return config;
}

function generationStatus(status = {}) {
  const labels = {
    enabled: "已就绪", generating: "模型正在生成今日日程", not_generated: "尚未生成今日安排",
    cooldown: "生成暂处于重试冷却", daily_limit: "今日自动尝试次数已达上限，可检查模型后手动重试", generation_failed: "日程生成失败", provider_missing: "未找到可用的生成模型",
    schedule_unavailable: "日程数据暂不可用", disabled: "日程模块未启用", read_failed: "读取日程失败",
  };
  const errors = {
    provider_missing: "请在生成设置中选择可用模型，或配置宿主默认模型。",
    model_timeout: "模型生成超时。", timeout: "模型生成超时。", invalid_json: "模型返回的格式无法解析。",
    invalid_schedule: "模型返回的日程未通过校验。", generation_failed: "模型请求或日程校验失败。",
  };
  const retry = status.next_retry_at && Number.isFinite(Date.parse(status.next_retry_at))
    ? new Date(status.next_retry_at).toLocaleString() : "";
  const code = typeof status.last_error === "string" ? status.last_error : "";
  return {
    title: labels[status.reason] || "日程状态待确认",
    detail: `${errors[code] || (code ? `错误代码：${code}` : "")}${retry ? ` 下一次可重试：${retry}` : ""}`.trim(),
  };
}

const PERSONA_SECTIONS = [
  "identity_control", "profile", "background", "personality", "behavior",
  "relationship", "speech", "response", "roleplay", "boundaries", "examples",
];

const SCHEDULE_SECTIONS = ["schedule_timeline", "schedule_settings"];

const MODULES = {
  persona: { title: "人格模块", description: "维护角色身份、背景、性格和表达方式。日程与即时状态在各自模块中管理。" },
  schedule: { title: "日程模块", description: "管理角色作息、今日安排与当前时段。独立开关，不与人格子页混排。" },
  state: { title: "当前状态", description: "管理有来源和有效期的活动、位置、情绪与精力；有效人工状态优先于日程。" },
  general: { title: "通用设置", description: "管理插件总开关、允许的私聊会话和机器人。这里的作用域适用于所有模块。" },
};

const labels = {
  identity_control: "身份控制", examples: "对话示例",
  schedule_timeline: "今日时间线", schedule_settings: "生成设置",
  profile: "基础资料", dynamic_state: "当前状态", schedule: "今日日程", background: "经历与世界", personality: "性格核心", behavior: "情境行为",
  relationship: "专属关系", speech: "说话方式", response: "回复策略", roleplay: "动作与场景",
  boundaries: "边界保护",
};

const descriptions = {
  profile: "稳定的身份事实。这里填写“她是谁”。",
  schedule: "根据角色设定或固定模板生成今日模拟生活安排；只参考当前时间段，不执行现实动作。",
  background: "成长经历、近期长期背景和世界知识，不表示此刻正在发生。",
  dynamic_state: "带来源、作用域和有效期的临时信息。过期只代表不再注入，不自动证明活动已完成。",
  personality: "性格倾向、价值观、缺点和内在矛盾。",
  behavior: "遇到具体情绪和互动时，她会怎么反应。",
  relationship: "只对绑定的私聊会话和机器人生效。",
  speech: "词汇、句式、标点、称呼和幽默习惯。",
  response: "回复长度、追问、建议和套话策略。",
  roleplay: "动作、场景和旁白偏好；不会替用户决定动作。",
  boundaries: "隐私、现实行为、记忆、工具和角色完整性保护。",
};

const options = {
  generation_mode: [["llm", "模型生成"], ["template", "用户固定模板"]],
  source: [["manual", "人工填写"], ["confirmed_event", "已确认事件（需人工确认）"]],
  age_mode: [["fixed", "固定年龄"], ["growing", "随时间增长"], ["timeline", "角色时间线"]],
  changeability: [["stable", "稳定"], ["influenced", "容易受影响"], ["adaptive", "随关系变化"]],
  social_temperature: [["slow", "慢热"], ["moderate", "适中"], ["outgoing", "外向"]],
  tone: [["follow_character", "遵循角色"], ["gentle", "温和"], ["playful", "轻松调侃"], ["reserved", "克制"]],
  sentence_length: [["adaptive", "随内容"], ["short", "短句"], ["medium", "适中"], ["long", "偏长"]],
  question_frequency: [["never", "很少"], ["necessary", "必要时"], ["often", "经常"]],
  emoji_frequency: [["none", "不用"], ["occasional", "少量"], ["frequent", "较多"]],
  length: [["adaptive", "随内容"], ["brief", "偏简短"], ["expanded", "充分表达"]],
  ask_followup: [["never", "不主动问"], ["necessary", "必要时问"], ["often", "经常问"]],
  offer_advice: [["when_requested", "用户请求时"], ["relevant", "相关时"], ["default", "默认提供"]],
  action_style: [["none", "无动作"], ["occasional", "偶尔简短动作"], ["scene", "场景化"]],
  action_format: [["parentheses", "括号动作"], ["short_narration", "短旁白"], ["natural", "融入表达"]],
  environment_detail: [["none", "无"], ["light", "少量"], ["rich", "丰富"]],
  refusal_level: [["gentle", "温和"], ["clear", "明确"], ["firm", "坚定"]],
};

const fieldGroups = {
  dynamic_state: [
    ["enabled", "启用临时状态", "checkbox", "仅在所绑定的私聊和机器人中、有效时间内提供状态。"],
    ["target_session", "绑定私聊会话 UMO", "scope", "从允许列表选择或手工填写完整 UMO。"],
    ["target_bot_id", "绑定机器人 QQ 号", "scope", "必须属于允许的机器人列表，不跨账号继承。"],
    ["activity", "当前活动", "textarea", "已经确认此刻在做什么；不要填写长期项目。"],
    ["location", "当前位置", "text", "此刻所在场景，与常住地区分。"],
    ["mood", "当前情绪", "text", "已确认的临时情绪，不是性格倾向。"],
    ["energy", "当前精力", "text", "人工填写或确认的精力描述。"],
    ["source", "信息来源", "select", "“已确认事件”须由你人工确认，不会自动识别事件或推断情绪。"],
    ["updated_at", "状态确认 / 生效时间", "datetime", "以浏览器时区输入，保存为带时区的 ISO 时间。"],
    ["expires_at", "状态失效时间", "datetime", "读取状态不会续期；到期只停止注入，不表示活动完成。"],
  ],
  schedule: [
    ["enabled", "启用日程模块", "checkbox", "启用并保存后生成今日模拟安排；适用范围使用插件会话和机器人白名单。"],
    ["auto_generate", "每天自动生成", "checkbox", "当天没有日程时自动生成一次；不自动覆盖已保存日程。"],
    ["timezone", "日程时区", "text", "例如 Asia/Shanghai。"],
    ["generation_mode", "生成方式", "select", "由模型规划今日活动，或使用你填写的固定模板；模型失败不会回退为规则排表。"],
    ["provider_id", "日程生成模型", "provider", "留空使用宿主默认模型；只显示模型标识，不显示密钥。"],
    ["model_timeout", "模型生成超时（秒）", "number", "10～180秒；生成在后台进行，不阻塞配置保存。"],
    ["retry_cooldown", "失败重试冷却（秒）", "number", "60～86400秒；失败不会每条消息重新调用模型。"],
    ["generation_rule", "模型生成要求", "textarea", "直接提供给模型的生活偏好和规划要求；作息与固定时段作为约束。"],
    ["template_lines", "可选固定安排 / 模板", "list", "每行：HH:MM-HH:MM | 活动 | 地点 | 备注；模型模式下作为固定约束，模板模式下为完整安排。"],
    ["wake_time", "起床时间", "time", "用于角色作息安排。"],
    ["sleep_time", "睡觉时间", "time", "用于角色作息安排。"],
    ["work_start", "工作开始", "time", "工作日的开始时间。"],
    ["work_end", "工作结束", "time", "工作日的结束时间。"],
    ["workdays", "工作日", "list", "每行一个数字：1为周一，7为周日。"],
    ["work_location", "工作地点", "text", "留空时根据角色设定处理。"],
    ["home_location", "居家地点", "text", "留空时根据角色常住地处理。"],
    ["allow_manual_override", "允许手动修改今日安排", "checkbox", "关闭后不允许保存手动编辑的时间段。"],
    ["max_segments", "最多时间段", "number", "生成或保存的时间段数量上限。"],
  ],
  profile: [
    ["name", "姓名", "text", "角色的正式姓名或主要称呼。"], ["nickname", "昵称", "text", "常用昵称或自称。"],
    ["gender_identity", "性别认同", "text", "例如女性、男性、非二元或自定义。"], ["pronouns", "代称", "text", "角色希望如何被指代。"],
    ["age", "年龄", "text", "可以填写数字或文字年龄。"], ["age_mode", "年龄模式", "select", "年龄是固定、增长还是按角色时间线计算。"],
    ["birth_date", "出生日期", "text", "需要计算年龄时填写。"], ["species", "物种", "text", "例如人类、仿生人、精灵。"],
    ["nationality", "国籍或地区", "text", "角色的地域背景。"], ["native_language", "母语", "text", "语言背景。"],
    ["timezone", "所在时区", "text", "例如 Asia/Shanghai。"], ["location", "常住地（非当前位置）", "text", "长期居住区域，不能作为当前所在位置。"],
    ["occupation", "职业", "text", "职业、身份或主要活动。"], ["education", "教育背景", "textarea", "专业、学校或知识背景。"],
    ["social_status", "社会身份", "textarea", "家庭、社会身份或经济状况。"],
  ],
  background: [
    ["identity", "身份与背景", "textarea", "角色是谁、身处什么背景。启用 plugin 模式时必填。"], ["family", "家庭关系", "textarea", "家庭结构与相处方式。"],
    ["childhood", "童年经历", "textarea", "塑造角色的重要成长经历。"], ["education_history", "学习经历", "textarea", "教育经历。"],
    ["work_history", "工作经历", "textarea", "工作经历。"], ["important_events", "重要事件", "list", "每行一项。"],
    ["current_situation", "旧版当前处境（保留待迁移，不注入）", "textarea", "保留旧内容供人工迁移；不会作为长期背景或当前活动提供给模型。"],
    ["life_context", "近期生活背景 / 项目（非当前活动）", "textarea", "描述持续的生活阶段或项目；此刻活动请填写“当前状态”。"],
    ["secrets", "秘密", "list", "角色不会随意主动透露的内容。"],
    ["world_setting", "世界设定", "textarea", "世界基本规则、科技或魔法背景。"], ["known_facts", "明确知道", "textarea", "角色知道的范围。"],
    ["unknown_facts", "明确不知道", "textarea", "角色不应该假装知道的范围。"],
  ],
  personality: [
    ["core_traits", "核心性格", "list", "例如慢热、好奇、有判断力。"], ["positive_traits", "优点", "list", "每行一项。"], ["flaws", "缺点", "list", "缺点和局限。"],
    ["values", "价值观", "list", "角色重视的原则。"], ["dislikes", "偏好与反感", "list", "不喜欢的事物或行为。"], ["fears", "恐惧与担忧", "list", "恐惧和担心。"],
    ["desires", "欲望与目标", "list", "角色想要什么。"], ["insecurities", "不安全感", "list", "不自信的地方。"], ["pride", "自豪之处", "list", "坚持或自豪的部分。"],
    ["contradictions", "性格矛盾", "list", "例如想被理解但不喜欢解释自己。"], ["self_image", "自我评价", "textarea", "角色如何看待自己。"],
    ["view_of_others", "对他人的看法", "textarea", "角色通常如何看待别人。"], ["changeability", "性格稳定程度", "select", "影响角色变化方式。"],
    ["social_temperature", "社交温度", "select", "慢热、适中或外向。"], ["legacy_summary", "旧版性格补充", "textarea", "兼容旧配置，可逐步迁移到上面的字段。"],
  ],
  behavior: [
    ["when_happy", "开心时", "textarea", "开心时如何表现。"], ["when_sad", "难过时", "textarea", "难过时如何表现。"], ["when_angry", "生气时", "textarea", "生气时的语气、行为和缓和方式。"],
    ["when_tired", "疲惫时", "textarea", "疲惫时的回复状态。"], ["when_embarrassed", "尴尬时", "textarea", "尴尬或害羞时。"], ["when_anxious", "焦虑时", "textarea", "焦虑时的表现。"],
    ["when_bored", "无聊时", "textarea", "无聊时的主动行为。"], ["when_confused", "困惑时", "textarea", "不理解时如何处理。"], ["when_praised", "被夸奖时", "textarea", "被夸奖时的反应。"],
    ["when_criticized", "被批评时", "textarea", "被批评时的反应。"], ["when_disagrees", "意见不同时", "textarea", "如何表达不同意见。"], ["when_apologizing", "道歉时", "textarea", "道歉和修复方式。"],
    ["when_refusing", "拒绝时", "textarea", "如何拒绝。"], ["when_ignored", "被冷落时", "textarea", "对方长时间不回应时。"], ["when_topic_changes", "换话题时", "textarea", "用户突然换话题时。"],
    ["when_memory_missing", "不记得时", "textarea", "缺少记忆时如何诚实处理。"],
  ],
  relationship: [
    ["role", "关系角色", "text", "朋友、家人、同事、恋人或自定义。"], ["stage", "关系阶段", "text", "初识、熟悉、亲近、疏远或冲突中。"],
    ["duration", "认识时长", "text", "例如认识三年。"], ["target_session", "目标会话 UMO", "text", "必须属于允许会话。"], ["target_bot_id", "目标机器人 QQ", "text", "必须属于允许机器人。"],
    ["background", "关系背景", "textarea", "已确认的关系背景。"], ["addressing", "角色如何称呼用户", "textarea", "称呼和适用场景。"],
    ["addressing_for_character", "用户如何称呼角色", "textarea", "用户可以如何叫角色。"], ["shared_history", "共同经历", "list", "每行一项，必须是已确认事实。"],
    ["shared_interests", "共同兴趣", "list", "双方共同兴趣。"], ["trust_level", "信任程度", "text", "例如谨慎、一般、信任。"],
    ["intimacy_boundary", "亲密边界", "textarea", "允许的亲密表达范围。"], ["sensitive_topics", "敏感话题", "list", "需要谨慎处理的话题。"],
    ["conflict_style", "冲突处理", "textarea", "发生矛盾时如何处理。"], ["repair_style", "关系修复", "textarea", "如何道歉和修复关系。"],
  ],
  speech: [
    ["first_person", "自称", "text", "例如我、名字或昵称。"], ["second_person", "对用户的称呼", "text", "如何称呼用户。"], ["vocabulary", "常用词汇与句式", "textarea", "口头表达和常用语。"], ["avoided_words", "避免使用的词", "list", "每行一项。"],
    ["sentence_length", "句子长度", "select", "短句、适中或偏长。"], ["punctuation", "标点习惯", "text", "标点、感叹号、省略号等习惯。"], ["question_frequency", "提问频率", "select", "少问、必要时问或经常问。"],
    ["emoji_frequency", "表情频率", "select", "不用、少量或较多。"], ["humor_style", "幽默方式", "textarea", "轻微吐槽、冷幽默、接梗等。"], ["affection_style", "表达在意", "textarea", "如何自然表达关心。"],
    ["disagreement_style", "表达分歧", "textarea", "不同意时怎么说。"], ["apology_style", "道歉方式", "textarea", "如何道歉。"], ["refusal_style", "拒绝方式", "textarea", "如何拒绝。"],
    ["greeting_style", "打招呼", "textarea", "打招呼习惯。"], ["goodbye_style", "结束话题", "textarea", "告别或结束话题习惯。"], ["correction_style", "纠正方式", "textarea", "纠正用户时的表达。"],
    ["topic_transition", "话题转换", "textarea", "转换话题的方式。"], ["silence_tolerance", "沉默与留白", "textarea", "是否允许简短和不追问。"], ["habits", "固定说话习惯", "textarea", "总体表达习惯。"],
    ["tone", "基础语气", "select", "遵循角色、温和、调侃或克制。"], ["extra", "补充表达偏好", "textarea", "其他表达要求。"],
  ],
  response: [
    ["length", "默认回复长度", "select", "只影响闲聊倾向。"], ["answer_first", "先直接回答", "checkbox", "适合问题型消息。"], ["ask_followup", "追问频率", "select", "不主动问、必要时问或经常问。"],
    ["offer_advice", "建议策略", "select", "只在请求时、相关时或默认提供。"], ["repeat_user", "复述用户内容", "checkbox", "是否先复述确认。"], ["handle_unknown", "不知道时怎么说", "textarea", "如何承认未知。"],
    ["avoid_cliches", "减少固定套话", "checkbox", "减少客服式收尾。"], ["avoid_psychological_analysis", "避免擅自心理分析", "checkbox", "不把闲聊改成咨询报告。"], ["avoid_over_affection", "避免过度亲密", "checkbox", "没有关系依据时不煽情。"],
    ["reduce_cliches", "减少重复安慰", "checkbox", "减少逐句复述和固定安慰。"],
  ],
  roleplay: [
    ["action_style", "动作描写", "select", "无、偶尔或场景化。"], ["action_format", "动作格式", "select", "括号、短旁白或自然融入。"], ["environment_detail", "环境细节", "select", "无、少量或丰富。"],
    ["inner_monologue", "允许内心独白", "checkbox", "谨慎开启。"], ["sensory_detail", "允许感官细节", "checkbox", "声音、气味、触感等。"],
  ],
  boundaries: [
    ["uncomfortable_topics", "不适合主动讨论", "list", "每行一项。"], ["forbidden_actions", "不会声称完成的行为", "list", "每行一项。"], ["refusal_level", "拒绝强度", "select", "温和、明确或坚定。"],
    ["privacy_rules", "隐私边界", "textarea", "不暴露哪些资料。"], ["reality_claims", "现实行为边界", "textarea", "不把未知行为说成已完成。"], ["memory_claims", "记忆边界", "textarea", "不把示例和推测当记忆。"],
    ["tool_claims", "工具结果边界", "textarea", "不把计划说成工具已执行。"], ["role_integrity", "角色完整性", "textarea", "不为迎合随意改变身份。"], ["roleplay", "场景扮演边界", "textarea", "场景扮演的额外边界。"],
  ],
};

function fieldModel(config, group, key) {
  return computed({
    get: () => config[group][key],
    set: (value) => { config[group][key] = value; },
  });
}

function toLocalDateTime(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) return "";
  const local = new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 19);
}

function fromLocalDateTime(value) {
  if (!value) return "";
  const parsed = new Date(value);
  return Number.isFinite(parsed.getTime()) ? parsed.toISOString() : "";
}

function stateSummary(saved, now) {
  if (!saved) return { title: "等待读取", detail: "保存后由服务端校验状态；页面时钟不会延长有效期。", active: false };
  const reasonLabels = {
    disabled: "临时状态未启用", empty: "尚未填写状态内容", no_content: "尚未填写状态内容",
    expired: "状态已过期", not_started: "尚未到生效时间", active: "状态有效", valid: "状态有效",
    invalid_config: "状态配置无效", invalid_time: "时间配置无效", plugin_disabled: "插件未启用",
  };
  const start = Date.parse(saved.updated_at || "");
  const end = Date.parse(saved.expires_at || "");
  let reason = saved.reason || "unknown";
  let active = Boolean(saved.active);
  if (["plugin_disabled", "invalid_config"].includes(reason)) { active = false; }
  else if (!saved.enabled) { reason = "disabled"; active = false; }
  else if (!saved.has_content) { reason = "no_content"; active = false; }
  else if (Number.isFinite(end) && now >= end) { reason = "expired"; active = false; }
  else if (Number.isFinite(start) && now < start) { reason = "not_started"; active = false; }
  else if (Number.isFinite(start) && Number.isFinite(end) && ["active", "valid", "not_started"].includes(reason)) {
    reason = "active"; active = true;
  }
  const seconds = Number.isFinite(end) ? Math.max(0, Math.ceil((end - now) / 1000)) : null;
  const duration = seconds === null ? "" : `${Math.floor(seconds / 3600)}小时 ${Math.floor((seconds % 3600) / 60)}分 ${seconds % 60}秒`;
  return {
    title: reasonLabels[reason] || reason,
    detail: reason === "expired" ? "有效期已结束，不再作为当前事实注入；不能据此认定活动已完成。"
      : active && duration ? `剩余 ${duration}（按已保存截止时间计算）`
      : "当前为已保存状态的判定；表单修改只有保存成功后生效。",
    active,
  };
}

function renderField(config, group, field, providers = []) {
  const [key, label, type, hint] = field;
  const model = fieldModel(config, group, key);
  if (type === "checkbox") {
    return h("label", { class: "check-row", key }, [
      h("input", {
        type: "checkbox",
        checked: Boolean(model.value),
        onChange: (event) => { model.value = event.target.checked; },
      }),
      h("span", label),
      h("small", hint),
    ]);
  }
  if (type === "number" || type === "time") {
    return h("label", { class: "field", key }, [
      h("span", label),
      h("input", {
        id: `${group}-${key}`, type, step: type === "number" ? 1 : 60,
        min: type === "number" ? key === "model_timeout" ? 10 : key === "retry_cooldown" ? 60 : 1 : undefined,
        max: type === "number" ? key === "model_timeout" ? 180 : key === "retry_cooldown" ? 86400 : key === "max_segments" ? 32 : undefined : undefined,
        value: model.value,
        onInput: (event) => {
          model.value = type === "number" ? event.target.valueAsNumber : event.target.value;
        },
      }),
      h("small", hint),
    ]);
  }
  if (type === "provider") {
    return h("label", { class: "field wide", key }, [
      h("span", label),
      h("input", { id: "schedule-provider-id", type: "text", list: "schedule-provider-options",
        placeholder: "宿主默认模型", value: model.value || "",
        onInput: (event) => { model.value = event.target.value; } }),
      h("datalist", { id: "schedule-provider-options" }, providers.map((provider) =>
        h("option", { key: provider.id, value: provider.id }, provider.label || provider.id))),
      h("small", hint),
    ]);
  }
  if (type === "scope") {
    const identifiers = key === "target_session" ? config.allowed_sessions : config.allowed_bot_ids;
    const listId = `dynamic-state-${key}-options`;
    return h("label", { class: "field wide", key }, [
      h("span", label),
      h("input", {
        id: `dynamic-state-${key}`, type: "text", list: listId, value: model.value || "",
        onInput: (event) => { model.value = event.target.value; },
      }),
      h("datalist", { id: listId }, (identifiers || []).map((value) => h("option", { value }))),
      h("small", hint),
    ]);
  }
  if (type === "datetime") {
    return h("label", { class: "field", key }, [
      h("span", label),
      h("input", {
        id: `dynamic-state-${key}`, type: "datetime-local", step: 1,
        value: toLocalDateTime(model.value),
        onChange: (event) => { model.value = fromLocalDateTime(event.target.value); },
      }),
      h("small", hint),
      model.value ? h("small", { class: "iso-time" }, `保存值：${model.value}`) : null,
    ]);
  }
  const control =
    type === "list" || type === "textarea"
      ? h("textarea", {
          rows: type === "list" ? 3 : 3,
          value: type === "list" ? (model.value || []).join("\n") : (model.value || ""),
          placeholder: type === "list" ? "每行一项" : "",
          onInput: (event) => {
            model.value = type === "list"
              ? event.target.value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
              : event.target.value;
          },
        })
      : type === "select"
        ? h("select", {
            value: model.value,
            onChange: (event) => { model.value = event.target.value; },
          }, (options[key] || []).map(([value, text]) => h("option", { value }, text)))
        : h("input", {
            type: "text",
            value: model.value || "",
            onInput: (event) => { model.value = event.target.value; },
          });
  return h("label", { class: `field ${type === "textarea" || type === "list" ? "wide" : ""}`, key }, [
    h("span", label),
    control,
    h("small", hint),
  ]);
}

function useAppState() {
  const config = reactive(blankConfig());
  const summary = reactive({ version: "—", valid: false, enabled: false, authority_mode: "overlay", config_error: "" });
  const activeModule = ref("persona");
  const active = ref("profile");
  const lastPersonaSection = ref("profile");
  const visibleSections = computed(() => activeModule.value === "persona" ? PERSONA_SECTIONS
    : activeModule.value === "schedule" ? SCHEDULE_SECTIONS : []);
  function selectModule(module) {
    if (!Object.hasOwn(MODULES, module)) return;
    if (activeModule.value === "persona" && PERSONA_SECTIONS.includes(active.value)) {
      lastPersonaSection.value = active.value;
    }
    activeModule.value = module;
    active.value = module === "persona" ? lastPersonaSection.value
      : module === "schedule" ? "schedule_timeline"
      : module === "state" ? "dynamic_state" : "general";
    if (module === "schedule") loadSchedule({ preserveDraft: true, background: true });
    else stopSchedulePoll();
  }
  function selectSection(section) {
    if (activeModule.value === "persona" && PERSONA_SECTIONS.includes(section)) {
      active.value = section;
      lastPersonaSection.value = section;
    } else if (activeModule.value === "schedule" && SCHEDULE_SECTIONS.includes(section)) {
      active.value = section;
    }
  }
  const busy = ref(false);
  const loaded = ref(false);
  const scheduleLoaded = ref(false);
  const loadedSnapshot = ref("");
  const message = ref("");
  const messageKind = ref("ok");
  const scheduleToday = ref(null);
  const scheduleBusy = ref(false);
  const scheduleDraft = ref([]);
  const scheduleDraftOrigins = ref([]);
  const scheduleEditingIndex = ref(null);
  const scheduleDirty = ref(false);
  const scheduleStatus = ref({});
  const scheduleSavedConfig = ref({ enabled: false, auto_generate: false, generation_mode: "llm" });
  const scheduleProviders = ref([]);
  const scheduleDefaultProvider = ref("");
  const scheduleProvidersError = ref("");
  const scheduleConflict = ref(false);
  const scheduleTimezone = ref("Asia/Shanghai");
  const sections = Object.keys(fieldGroups);
  const clock = ref(Date.now());
  const scheduleCurrent = computed(() => {
    const current = currentSchedule(scheduleToday.value, scheduleTimezone.value, clock.value);
    if (!summary.enabled) return { ...current, reason: "plugin_disabled", slot: null };
    if (!scheduleLoaded.value) return { ...current, reason: scheduleStatus.value.reason === "read_failed" ? "unavailable" : "loading", slot: null };
    if (!scheduleSavedConfig.value.enabled || scheduleStatus.value.reason === "disabled") return { ...current, reason: "disabled", slot: null };
    if (["schedule_unavailable", "read_failed"].includes(scheduleStatus.value.reason)) return { ...current, reason: "unavailable", slot: null };
    return current;
  });
  const generationBlocked = computed(() => {
    const status = scheduleStatus.value;
    const retry = Date.parse(status.next_retry_at || "");
    return status.reason === "generating" || (Number.isFinite(retry) && retry > clock.value);
  });
  const canGenerate = computed(() => loaded.value && scheduleLoaded.value && summary.enabled && scheduleSavedConfig.value.enabled && config.schedule.enabled && !scheduleBusy.value && !busy.value && !generationBlocked.value && !["unavailable", "different_day"].includes(scheduleCurrent.value.reason));
  const canEditSchedule = computed(() => loaded.value && scheduleLoaded.value && summary.enabled && scheduleSavedConfig.value.enabled && config.schedule.enabled && !scheduleBusy.value && !busy.value && config.schedule.allow_manual_override && Boolean(scheduleToday.value) && !["unavailable", "different_day"].includes(scheduleCurrent.value.reason));
  const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "浏览器本地时区";
  const dynamicStatus = computed(() => stateSummary(summary.dynamic_state, clock.value));
  let clockTimer;
  let schedulePollTimer;
  let scheduleReadBusy = false;
  let disposed = false;
  function stopSchedulePoll() {
    clearTimeout(schedulePollTimer);
    schedulePollTimer = undefined;
  }
  function syncSchedulePoll() {
    stopSchedulePoll();
    if (!disposed && activeModule.value === "schedule" && scheduleStatus.value.reason === "generating") {
      schedulePollTimer = setTimeout(() => loadSchedule({ preserveDraft: true, background: true }), 2000);
    }
  }
  function setValidity(minutes) {
    const now = new Date();
    config.dynamic_state.updated_at = now.toISOString();
    config.dynamic_state.expires_at = new Date(now.getTime() + minutes * 60_000).toISOString();
    message.value = `已设置 ${minutes} 分钟有效期；保存后生效，未自动开启状态。`;
    messageKind.value = "ok";
  }

  const sessionsText = computed({
    get: () => (config.allowed_sessions || []).join("\n"),
    set: (value) => {
      config.allowed_sessions = value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
    },
  });
  const botsText = computed({
    get: () => (config.allowed_bot_ids || []).join("\n"),
    set: (value) => {
      config.allowed_bot_ids = value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
    },
  });
  const relationFilled = computed(() =>
    ["background", "addressing", "role", "stage", "target_session"]
      .some((key) => Boolean(config.relationship[key])));

  async function connect() {
    if (!bridge || typeof bridge.ready !== "function") {
      throw new Error("未检测到 AstrBot 插件桥接，请从插件详情页打开此视图");
    }
    // The bridge only resolves after the dashboard parent replies. A missing
    // reply must not leave the page waiting forever.
    await Promise.race([
      bridge.ready(),
      new Promise((_, reject) =>
        setTimeout(
          () => reject(new Error("等待 AstrBot 面板握手超时，请从插件详情页打开此视图")),
          8000,
        )),
    ]);
  }

  function withTimeout(promise, message) {
    return Promise.race([
      promise,
      new Promise((_, reject) => setTimeout(() => reject(new Error(message)), 12000)),
    ]);
  }

  function showError(prefix, error) {
    message.value = `${prefix}：${error.message || error}`;
    messageKind.value = "error";
  }

  function applyScheduleResult(result, { preserveDraft = false } = {}) {
    if (!Object.hasOwn(result, "today") || !result.status || !result.config) {
      throw new Error("日程响应缺少配置或今日数据");
    }
    if (result.today !== null && (!result.today || !Array.isArray(result.today.slots))) {
      throw new Error("日程时间段数据无效");
    }
    const previousReason = scheduleStatus.value.reason;
    const previousRevision = scheduleToday.value?.revision;
    if (preserveDraft && scheduleDirty.value) {
      scheduleConflict.value = Boolean(result.today?.revision !== scheduleToday.value?.revision);
    } else {
      scheduleToday.value = result.today;
      scheduleDraft.value = (result.today?.slots || []).map((slot) => ({ ...slot }));
      scheduleDraftOrigins.value = (result.today?.slots || []).map((_, index) => index);
      scheduleEditingIndex.value = null;
      scheduleDirty.value = false;
      scheduleConflict.value = false;
    }
    scheduleTimezone.value = result.today?.timezone || result.config.timezone || "Asia/Shanghai";
    scheduleSavedConfig.value = normalizeScheduleMode({ schedule: { ...result.config } }).schedule;
    scheduleStatus.value = result.status;
    scheduleLoaded.value = true;
    if (previousReason === "generating" && result.status.reason !== "generating" && result.today?.generation_mode === "llm" && result.today.revision !== previousRevision) {
      message.value = scheduleConflict.value
        ? "模型已生成新日程；手动草稿保留原版本，请处理冲突后重新读取。"
        : "模型已生成今日日程并完成校验，时间线已更新。";
      messageKind.value = scheduleConflict.value ? "error" : "ok";
    }
  }

  async function loadSchedule({ discardDraft = false, preserveDraft = false, background = false } = {}) {
    if (scheduleReadBusy || disposed) return false;
    if (scheduleDirty.value && !discardDraft && !preserveDraft) {
      if (!window.confirm("重新读取会丢弃未保存的今日日程草稿，继续吗？")) return false;
    }
    scheduleReadBusy = true;
    if (!background) scheduleLoaded.value = false;
    try {
      await connect();
      const result = unwrapResponse(await withTimeout(bridge.apiGet("schedule"), "读取今日日程超时"));
      if (disposed) return false;
      applyScheduleResult(result, { preserveDraft });
      return true;
    } catch (error) {
      if (!disposed) {
        scheduleStatus.value = { enabled: false, reason: "read_failed" };
        showError("读取日程失败", error);
      }
      return false;
    } finally {
      scheduleReadBusy = false;
      syncSchedulePoll();
    }
  }

  async function loadProviders() {
    try {
      const result = unwrapResponse(await withTimeout(bridge.apiGet("schedule/providers"), "读取模型列表超时"));
      if (!Array.isArray(result.providers)) throw new Error("模型列表格式无效");
      scheduleProviders.value = result.providers.filter((item) => item && typeof item.id === "string")
        .map((item) => ({ id: item.id, label: typeof item.label === "string" ? item.label : item.id }));
      scheduleDefaultProvider.value = typeof result.default_id === "string" ? result.default_id : "";
      scheduleProvidersError.value = "";
    } catch {
      scheduleProvidersError.value = "模型列表暂时无法读取；可保留空值使用宿主默认模型，或手填模型标识。";
    }
  }

  function settingsChanged() {
    return loadedSnapshot.value !== JSON.stringify(config);
  }

  async function generateSchedule() {
    if (!canGenerate.value) return;
    if (settingsChanged()) {
      message.value = "请先保存设置，再生成日程。生成仅使用已经保存的角色与作息配置。";
      messageKind.value = "error";
      return;
    }
    const existing = scheduleToday.value;
    const replacing = Boolean(existing || scheduleDirty.value);
    if (replacing && !window.confirm("今天已有安排或手动草稿。重新生成将替换今日时间段，确定继续吗？")) return;
    scheduleBusy.value = true;
    try {
      await connect();
      const body = { confirm: replacing };
      if (existing?.revision !== undefined) {
        body.revision = existing.revision;
        body.date = existing.date;
        body.timezone = existing.timezone;
      }
      const result = unwrapResponse(await withTimeout(bridge.apiPost("schedule/generate", body), "提交日程生成超时"));
      if (!result.accepted && !result.saved) {
        if (!result.status) throw new Error("服务端未确认日程生成请求");
        applyScheduleResult({ ...result, config: result.config || scheduleSavedConfig.value }, { preserveDraft: true });
        message.value = `未发起新的模型请求：${generationStatus(result.status).title}。请查看生成状态与重试时间。`;
        messageKind.value = "error";
        syncSchedulePoll();
        return;
      }
      applyScheduleResult({ ...result, config: result.config || scheduleSavedConfig.value }, { preserveDraft: true });
      if (result.accepted) {
        message.value = result.status?.reason === "generating"
          ? "生成请求已受理，模型正在后台规划今日日程；页面将自动读取结果。"
          : `生成请求已受理：${generationStatus(result.status).title}。`;
      } else {
        message.value = "固定模板日程已保存。";
      }
      messageKind.value = "ok";
      syncSchedulePoll();
    } catch (error) { showError("生成日程失败", error); }
    finally { scheduleBusy.value = false; }
  }

  const comparableSlot = (slot) => ["start", "end", "activity", "location", "notes"].map((key) => String(slot?.[key] || ""));
  function refreshScheduleDirty() {
    scheduleDirty.value = JSON.stringify(scheduleDraft.value.map(comparableSlot)) !== JSON.stringify((scheduleToday.value?.slots || []).map(comparableSlot));
  }
  function openSlot(index) {
    if (!canEditSchedule.value || !scheduleDraft.value[index]) return;
    scheduleEditingIndex.value = scheduleEditingIndex.value === index ? null : index;
  }
  function closeSlot() { scheduleEditingIndex.value = null; }
  function editSlot(index, key, value) {
    if (!scheduleDraft.value[index] || !["start", "end", "activity", "location", "notes"].includes(key)) return;
    scheduleDraft.value[index][key] = value;
    refreshScheduleDirty();
  }
  function addSlot() {
    if (!canEditSchedule.value || scheduleDraft.value.length >= config.schedule.max_segments) return;
    scheduleDraft.value.push({ start: "", end: "", activity: "", location: "", notes: "" });
    scheduleDraftOrigins.value.push(null);
    scheduleEditingIndex.value = scheduleDraft.value.length - 1;
    refreshScheduleDirty();
  }
  function deleteSlot(index) {
    if (!canEditSchedule.value || !scheduleDraft.value[index]) return;
    scheduleDraft.value.splice(index, 1);
    scheduleDraftOrigins.value.splice(index, 1);
    if (scheduleEditingIndex.value === index) scheduleEditingIndex.value = null;
    else if (scheduleEditingIndex.value > index) scheduleEditingIndex.value -= 1;
    refreshScheduleDirty();
  }
  function cancelSlot(index) {
    if (!canEditSchedule.value || !scheduleDraft.value[index]) return;
    const origin = scheduleDraftOrigins.value[index];
    if (origin === null) {
      scheduleDraft.value.splice(index, 1);
      scheduleDraftOrigins.value.splice(index, 1);
    } else if (scheduleToday.value?.slots[origin]) {
      scheduleDraft.value[index] = { ...scheduleToday.value.slots[origin] };
    }
    scheduleEditingIndex.value = null;
    refreshScheduleDirty();
  }
  function restoreSlot(origin) {
    if (!canEditSchedule.value || scheduleDraftOrigins.value.includes(origin) || !scheduleToday.value?.slots[origin]) return;
    const before = scheduleDraftOrigins.value.findIndex((value) => value === null || value > origin);
    const index = before < 0 ? scheduleDraft.value.length : before;
    scheduleDraft.value.splice(index, 0, { ...scheduleToday.value.slots[origin] });
    scheduleDraftOrigins.value.splice(index, 0, origin);
    if (scheduleEditingIndex.value !== null && scheduleEditingIndex.value >= index) scheduleEditingIndex.value += 1;
    refreshScheduleDirty();
  }
  function validateSlots(slots) {
    if (!slots.length) throw new Error("至少保留一个时间段");
    if (slots.length > config.schedule.max_segments) throw new Error("时间段数量超过设置上限");
    let previousEnd = "00:00";
    for (const [index, slot] of slots.entries()) {
      if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(slot.start)) throw new Error(`第 ${index + 1} 段开始时间无效`);
      if (!/^(?:(?:[01]\d|2[0-3]):[0-5]\d|24:00)$/.test(slot.end)) throw new Error(`第 ${index + 1} 段结束时间无效`);
      if (slot.start >= slot.end) throw new Error(`第 ${index + 1} 段不能跨夜或倒置`);
      if (slot.start < previousEnd) throw new Error(`第 ${index + 1} 段与前段重叠或未按时间排序`);
      if (!slot.activity.trim()) throw new Error(`第 ${index + 1} 段需要填写活动`);
      previousEnd = slot.end;
    }
  }
  async function saveToday() {
    if (!canEditSchedule.value || !scheduleDirty.value) return;
    if (settingsChanged()) {
      message.value = "请先保存设置，再保存今日日程；未保存的时间段草稿会保留。";
      messageKind.value = "error";
      return;
    }
    scheduleBusy.value = true;
    try {
      const slots = scheduleDraft.value.map((slot) => Object.fromEntries(
        ["start", "end", "activity", "location", "notes"].map((key) => [key, String(slot[key] || "").trim()])
      ));
      validateSlots(slots);
      await connect();
      unwrapResponse(await withTimeout(bridge.apiPost("schedule/update", {
        slots, revision: scheduleToday.value.revision,
        date: scheduleToday.value.date, timezone: scheduleToday.value.timezone,
      }), "保存今日日程超时"));
      if (await loadSchedule({ discardDraft: true })) {
        message.value = "今日日程已保存并重新读取。";
        messageKind.value = "ok";
      }
    } catch (error) { showError("保存今日日程失败（草稿已保留）", error); }
    finally { scheduleBusy.value = false; }
  }

  async function load() {
    loaded.value = false;
    try {
      await connect();
      const result = unwrapResponse(await withTimeout(
        bridge.apiGet("settings"), "读取配置超时，请刷新或从插件详情页重新打开",
      ));
      if (!result.config || typeof result.config !== "object" || Array.isArray(result.config) || !result.summary) {
        throw new Error("配置响应缺少 config / summary，未采用空白表单");
      }
      mergeDeep(config, normalizeScheduleMode(result.config));
      Object.assign(summary, result.summary);
      loadedSnapshot.value = JSON.stringify(config);
      loaded.value = true;
      await loadSchedule();
      loadProviders();
    } catch (error) { showError("读取配置失败", error); }
  }

  async function save() {
    if (!loaded.value || busy.value || scheduleBusy.value) return;
    busy.value = true;
    message.value = "保存中…";
    try {
      await connect();
      const payload = JSON.parse(JSON.stringify(config));
      const result = unwrapResponse(await withTimeout(
        bridge.apiPost("settings", payload), "保存超时，请确认插件仍已启用后重试",
      ));
      if (!result.saved || !result.config || !result.summary) throw new Error("服务端未确认配置保存成功");
      mergeDeep(config, normalizeScheduleMode(result.config));
      Object.assign(summary, result.summary);
      loadedSnapshot.value = JSON.stringify(config);
      const hadDraft = scheduleDirty.value;
      if (await loadSchedule({ preserveDraft: true })) {
        const status = scheduleStatus.value;
        message.value = status.reason === "generating"
          ? "设置已保存，日程正在生成；生成完成前继续保留已有有效安排。"
          : ["cooldown", "generation_failed", "provider_missing", "daily_limit"].includes(status.reason)
            ? `设置已保存；${generationStatus(status).title}，请查看时间线中的原因和重试时间。`
            : hadDraft ? "设置已保存并重新读取日程；手动草稿和原版本保留，请再保存今日。"
              : "设置已保存，新请求立即生效；已读取日程状态。";
        messageKind.value = "ok";
      }
    } catch (error) { showError("保存失败", error); }
    finally { busy.value = false; }
  }

  onMounted(() => {
    load();
    clockTimer = setInterval(() => { clock.value = Date.now(); }, 1000);
  });
  onUnmounted(() => { disposed = true; clearInterval(clockTimer); stopSchedulePoll(); });

  return {
    config, summary, active, activeModule, visibleSections, selectModule, selectSection,
    busy, message, messageKind, sections,
    sessionsText, botsText, relationFilled, save,
    dynamicStatus, browserTimezone, setValidity, scheduleToday, scheduleCurrent, scheduleBusy, generateSchedule,
    loaded, scheduleLoaded, scheduleDraft, scheduleDraftOrigins, scheduleEditingIndex,
    scheduleDirty, scheduleStatus, scheduleSavedConfig, scheduleConflict,
    scheduleProviders, scheduleDefaultProvider, scheduleProvidersError,
    canGenerate, canEditSchedule, loadSchedule, editSlot, addSlot, deleteSlot, saveToday,
    openSlot, closeSlot, cancelSlot, restoreSlot,
  };
}

const App = {
  setup() {
    const state = useAppState();
    // Returning a render function keeps the raw refs unwrapped. Passing the
    // state object through the component proxy would unwrap active.value.
    return () => renderApp(state);
  },
};

function renderScheduleEditor(state) {
  const { scheduleEditingIndex, scheduleDraft, scheduleDraftOrigins, canEditSchedule,
    editSlot, closeSlot, cancelSlot, deleteSlot } = state;
  const index = scheduleEditingIndex.value;
  const slot = index === null ? null : scheduleDraft.value[index];
  if (!slot) return null;
  return h("div", { class: "schedule-slot-editor", id: "schedule-slot-editor", "data-editing-index": index }, [
    h("div", { class: "slot-editor-heading" }, [
      h("b", scheduleDraftOrigins.value[index] === null ? "新增时间段 · 未保存草稿" : "编辑这个时间段 · 未保存草稿"),
      h("button", { type: "button", class: "timeline-text-button", id: "schedule-close-editor", onClick: closeSlot }, "收起"),
    ]),
    ...[["start", "开始", "HH:MM"], ["end", "结束", "HH:MM 或 24:00"], ["activity", "活动", "此时在做什么"], ["location", "地点", "此时在哪里"], ["notes", "备注", "可选说明"]].map(([key, label, placeholder]) =>
      h("label", { class: `field slot-${key}` }, [
        h("span", label),
        h("input", { id: `schedule-slot-${index}-${key}`, type: "text", value: slot[key] || "", placeholder,
          disabled: !canEditSchedule.value, onInput: (event) => editSlot(index, key, event.target.value) }),
      ])),
    h("div", { class: "slot-editor-actions" }, [
      h("button", { type: "button", id: "schedule-cancel-slot", disabled: !canEditSchedule.value,
        onClick: () => cancelSlot(index) }, "取消本段修改"),
      h("button", { type: "button", class: "slot-delete", "data-delete-slot": index,
        disabled: !canEditSchedule.value, onClick: () => deleteSlot(index) }, "删除此段"),
    ]),
    h("p", { class: "slot-editor-note" }, "编辑仅修改草稿；收起不会丢失修改，点击下方“保存今日日程”后才会替换已保存内容。"),
  ]);
}

function renderSchedule(state) {
  const { config, loaded, busy, scheduleToday, scheduleCurrent, scheduleBusy,
    scheduleLoaded, scheduleDraft, scheduleDraftOrigins, scheduleEditingIndex, scheduleDirty,
    scheduleStatus, scheduleSavedConfig, scheduleConflict, canGenerate, canEditSchedule, loadSchedule, generateSchedule,
    openSlot, restoreSlot, addSlot, saveToday, selectSection } = state;
  const today = scheduleToday.value;
  const generation = generationStatus(scheduleStatus.value);
  const generating = scheduleStatus.value.reason === "generating";
  const generationError = Boolean(scheduleStatus.value.last_error) || ["generation_failed", "provider_missing", "cooldown", "daily_limit"].includes(scheduleStatus.value.reason);
  const current = scheduleCurrent.value;
  const usable = ["active", "gap"].includes(current.reason);
  const title = current.reason === "plugin_disabled" ? "插件未启用"
    : current.reason === "disabled" ? "日程模块未启用"
    : current.reason === "loading" ? "正在读取今日安排"
    : current.reason === "unavailable" ? "暂时无法读取日程"
    : current.reason === "different_day" ? "这份安排已跨日，请重新读取"
    : current.reason === "invalid_timezone" ? "日程时区无效"
    : !today && generating ? "模型正在生成今日日程"
    : !today && generationError ? generation.title
    : current.slot ? `${current.slot.activity} · ${current.slot.location || "未填写位置"}`
    : "当前没有匹配时段";
  const reasonNote = current.reason === "plugin_disabled" ? "请先在通用设置启用插件，再保存日程生成设置。"
    : current.reason === "disabled" ? "前往生成设置开启并保存；开启自动生成后，会根据已保存的角色与作息创建今日内容。"
    : current.reason === "different_day" ? "下方仅保留上次读取的日期内容，不作为今天的位置或活动；重新读取后查看今日安排。"
    : current.reason === "unavailable" ? "当前活动高亮已停止。你可以重新读取；未保存的草稿会保留。"
    : current.reason === "loading" ? "当前页面不使用尚未读取完成的内容推断角色状态。"
    : current.reason === "invalid_timezone" ? "请到生成设置检查时区；页面没有把旧数据标记为当前活动。"
    : current.slot ? `${current.slot.start} - ${current.slot.end}；当前卡片只参考已保存内容。`
    : today ? "时间线允许空档；没有匹配时段时不虚构当前活动。" : "尚未生成今日安排。保存生成设置后，自动生成会建立今日时间线。";
  const phaseOf = (slot) => !usable ? "inactive" : slot.start <= current.time && current.time < slot.end ? "current"
    : slot.end <= current.time ? "past" : "upcoming";
  const sameSlot = (left, right) => ["start", "end", "activity", "location", "notes"].every((key) => String(left?.[key] || "") === String(right?.[key] || ""));
  const draftEntries = scheduleDraftOrigins.value.map((origin, index) => ({ origin, index })).filter((entry) => entry.origin === null);
  return h("section", { class: "panel detail schedule-timeline-panel", "data-section": "schedule_timeline" }, [
    h("div", { class: "panel-title" }, [h("div", [h("h2", "今日时间线"),
      h("p", "自动生成的安排在这里按时间展示；生成规则与作息参数单独放在“生成设置”。")]),
      scheduleDirty.value ? h("span", { class: "timeline-draft-badge", role: "status" }, "有未保存草稿") : null,
    ]),
    h("div", { class: "schedule-overview" }, [
      h("div", { class: `dynamic-state-status ${usable && current.slot ? "is-active" : ""}` }, [
        h("small", `已保存安排 · ${today?.date || "未生成"} · ${today?.timezone || scheduleSavedConfig.value.timezone || config.schedule.timezone}`),
        today && current.date && today.date !== current.date ? h("small", { class: "timeline-stale-note" }, "这份数据不属于今天，仅供查看；没有标记任何当前活动。") : null,
        h("strong", { id: "schedule-current", role: "status", "aria-live": "polite" }, title),
        h("p", reasonNote),
        h("small", `生成状态：${generation.title}`),
        today ? h("small", today.manual_override ? "内容来源：已保存的人工调整"
          : today.generation_mode === "llm" ? `内容来源：模型生成${today.provider_id || scheduleStatus.value.provider_id ? ` · ${today.provider_id || scheduleStatus.value.provider_id}` : ""}`
            : today.generation_mode === "template" ? "内容来源：用户固定模板" : "内容来源：旧版规则安排（可重新生成模型日程）")
          : h("small", `每天自动生成（已保存）：${scheduleSavedConfig.value.auto_generate ? "开启" : "关闭"}`),
      ]),
      generating || generationError ? h("div", { id: "schedule-generation-status", class: `schedule-generation-status ${generationError ? "has-error" : "is-generating"}`, role: "status", "aria-live": "polite" }, [
        h("b", generating ? "模型正在生成今日日程" : "上次生成未成功"),
        h("p", generation.detail || (generating ? "生成在后台进行；本页每2秒只读查询进度，不会重复请求生成。已有有效日程继续使用。" : "请检查模型设置后重试；已有有效日程不会被规则排表替换。")),
        h("small", "模型调用可能产生费用。通常每日生成一次，不在每条消息时调用。"),
      ]) : null,
      scheduleConflict.value ? h("div", { id: "schedule-draft-conflict", class: "schedule-generation-status has-error", role: "status" }, [
        h("b", "后台日程已更新，手动草稿仍保留原版本"),
        h("p", "为防止覆盖新安排，继续保存会进行版本校验。请先复制需要保留的修改，再重新读取最新时间线。"),
      ]) : null,
      h("div", { class: "validity-actions schedule-timeline-toolbar" }, [
        h("button", { id: "schedule-reload", type: "button", disabled: scheduleBusy.value || busy.value || !loaded.value,
          onClick: () => loadSchedule() }, "重新读取"),
        h("button", { id: "schedule-generate", type: "button", disabled: !canGenerate.value,
          onClick: generateSchedule }, generating ? "模型生成中…" : scheduleBusy.value ? "处理中…" : today ? "重新生成今日安排" : "生成今日安排"),
        h("button", { id: "schedule-open-settings", type: "button", class: "timeline-text-button",
          onClick: () => selectSection("schedule_settings") }, "前往生成设置"),
      ]),
      today ? h("p", { class: "timezone-note timeline-plan-note" }, "时间线显示已保存计划。时段已过仅表示时间经过，不代表活动已完成；有效人工当前状态仍优先于日程。") : null,
      today && today.slots.length ? h("ol", { class: "schedule-timeline", id: "schedule-timeline", "aria-label": "已保存日程时间线" },
        today.slots.map((slot, savedIndex) => {
          const phase = phaseOf(slot);
          const draftIndex = scheduleDraftOrigins.value.indexOf(savedIndex);
          const deleted = draftIndex < 0;
          const changed = deleted || !sameSlot(slot, scheduleDraft.value[draftIndex]);
          const expanded = !deleted && scheduleEditingIndex.value === draftIndex;
          return h("li", { key: savedIndex, class: `timeline-entry is-${phase}`,
            "data-timeline-index": savedIndex, "data-phase": phase,
            "aria-current": phase === "current" ? "time" : undefined }, [
            h("div", { class: "timeline-marker", "aria-hidden": "true" }),
            h("div", { class: "timeline-entry-body" }, [
              h("div", { class: "timeline-entry-header" }, [
                h("time", { class: "timeline-time" }, `${slot.start} - ${slot.end}`),
                h("span", { class: "timeline-phase" }, phase === "current" ? "当前时段" : phase === "past" ? "计划时段已过" : phase === "upcoming" ? "尚未到时段" : "未作为当前安排使用"),
                changed ? h("span", { class: "timeline-draft-badge" }, deleted ? "草稿中待删除" : "本段有未保存修改") : null,
              ]),
              h("h3", slot.activity),
              slot.location ? h("p", { class: "timeline-location" }, slot.location) : null,
              slot.notes ? h("p", { class: "timeline-notes" }, slot.notes) : null,
              h("button", { id: `schedule-edit-slot-${savedIndex}`, type: "button", class: "timeline-edit-button",
                "data-edit-slot": savedIndex, "aria-expanded": expanded, "aria-controls": expanded ? "schedule-slot-editor" : undefined,
                disabled: !canEditSchedule.value,
                onClick: () => deleted ? restoreSlot(savedIndex) : openSlot(draftIndex) }, deleted ? "撤销删除" : expanded ? "收起编辑" : "编辑"),
              expanded ? renderScheduleEditor(state) : null,
            ]),
          ]);
        })) : h("div", { class: "timeline-empty", id: "schedule-timeline-empty" }, [
          h("b", "今天还没有生成的内容"),
          h("p", "在生成设置中启用日程并保存。开启每天自动生成时，后端会创建当天安排，无需逐段填写。"),
        ]),
      draftEntries.length ? h("div", { class: "schedule-new-drafts", "aria-label": "新增时间段草稿" }, [
        h("h3", "新增时间段 · 未保存"),
        ...draftEntries.map(({ index }) => h("div", { key: index, class: "timeline-new-draft", "data-draft-index": index }, [
          h("p", "这段仅为草稿，保存前不会出现在已保存时间线或当前活动中。"),
          h("button", { type: "button", id: `schedule-edit-draft-${index}`, class: "timeline-edit-button",
            disabled: !canEditSchedule.value, "aria-expanded": scheduleEditingIndex.value === index,
            onClick: () => openSlot(index) }, scheduleEditingIndex.value === index ? "收起编辑" : "编辑新增草稿"),
          scheduleEditingIndex.value === index ? renderScheduleEditor(state) : null,
        ])),
      ]) : null,
      today ? h("div", { class: "schedule-timeline-actions validity-actions" }, [
        h("button", { id: "schedule-add-slot", type: "button", disabled: !canEditSchedule.value || scheduleDraft.value.length >= config.schedule.max_segments,
          onClick: addSlot }, "添加时间段"),
        scheduleDirty.value ? h("button", { id: "schedule-save-today", type: "button", class: "timeline-save-button",
          disabled: !canEditSchedule.value, onClick: saveToday }, "保存今日日程") : null,
      ]) : null,
      today && scheduleSavedConfig.value.allow_manual_override === false ? h("p", { class: "timezone-note" }, "已保存设置不允许人工修改；可在生成设置中开启后保存。") : null,
    ]),
  ]);
}

function renderScheduleSettings(state) {
  const { config, selectSection, scheduleProviders, scheduleDefaultProvider, scheduleProvidersError } = state;
  return h("section", { class: "panel detail schedule-settings-panel", "data-section": "schedule_settings" }, [
    h("div", { class: "panel-title" }, [h("div", [h("h2", "生成设置"),
      h("p", "这里只配置自动生成方式。今日活动与位置请在“今日时间线”查看，不需要手工逐段创建。")])]),
    h("div", { class: "schedule-settings-intro" }, [
      h("p", "启用日程与每天自动生成，保存后由所选模型结合角色资料和生成要求规划今日活动。通常每日调用一次，可能产生费用；不是每条消息都调用。生成失败保留已有有效计划，不回退为硬编码作息或固定模板。"),
      h("small", `宿主默认模型：${scheduleDefaultProvider.value || "未配置或尚未获取"}。留空模型标识时使用该默认值。`),
      scheduleProvidersError.value ? h("p", { class: "provider-list-error", role: "status" }, scheduleProvidersError.value) : null,
      h("button", { id: "schedule-open-timeline", type: "button", class: "timeline-edit-button",
        onClick: () => selectSection("schedule_timeline") }, "查看今日时间线"),
    ]),
    h("div", { class: "field-grid" }, fieldGroups.schedule.map((field) => renderField(config, "schedule", field, scheduleProviders.value))),
  ]);
}
function renderIdentityControl(config) {
  return h("section", { class: "panel detail", "data-section": "identity_control" }, [
    h("div", { class: "panel-title" }, [h("div", [
      h("h2", "身份控制"),
      h("p", "选择角色资料来源与身份优先方式。总开关和会话白名单请前往通用设置。"),
    ])]),
    h("div", { class: "field-grid" }, [
      h("label", { class: "field", for: "persona-source" }, [
        h("span", "人格来源"),
        h("select", { id: "persona-source", value: config.persona_source,
          onChange: (event) => { config.persona_source = event.target.value; } }, [
          h("option", { value: "plugin" }, "插件管理完整人格"),
          h("option", { value: "astrbot" }, "沿用 AstrBot 人格"),
        ]),
        h("small", "沿用 AstrBot 人格时，本插件只补充表达规则。"),
      ]),
      h("label", { class: "field", for: "authority-mode" }, [
        h("span", "身份控制模式"),
        h("select", { id: "authority-mode", value: config.persona_authority.mode,
          disabled: config.persona_source !== "plugin",
          onChange: (event) => { config.persona_authority.mode = event.target.value; } }, [
          h("option", { value: "overlay" }, "叠加模式（兼容）"),
          h("option", { value: "character_owner" }, "角色主控模式（推荐）"),
        ]),
        h("small", "角色主控模式要求人格来源为插件；后台会校验不兼容的组合。"),
      ]),
      h("label", { class: "check-row", for: "persona-suppress-assistant" }, [
        h("input", { id: "persona-suppress-assistant", type: "checkbox",
          checked: config.persona_authority.suppress_generic_assistant_identity,
          disabled: config.persona_source !== "plugin",
          onChange: (event) => { config.persona_authority.suppress_generic_assistant_identity = event.target.checked; } }),
        h("span", "抑制通用助手自我介绍"),
        h("small", "主控模式下避免无缘无故自称 AI 或 AstrBot 助手。"),
      ]),
      h("label", { class: "check-row", for: "persona-technical-disclosure" }, [
        h("input", { id: "persona-technical-disclosure", type: "checkbox",
          checked: config.persona_authority.allow_technical_identity_disclosure,
          disabled: config.persona_source !== "plugin",
          onChange: (event) => { config.persona_authority.allow_technical_identity_disclosure = event.target.checked; } }),
        h("span", "允许明确技术问题披露运行环境"),
        h("small", "用户明确询问平台或模型时如实说明，不改变日常角色身份。"),
      ]),
    ]),
  ]);
}

function renderGeneral(state) {
  const { config, sessionsText, botsText } = state;
  return h("section", { class: "panel detail general-settings", "data-section": "general" }, [
    h("div", { class: "panel-title" }, [h("div", [
      h("h2", "通用设置"), h("p", "总开关与生效范围。留空白名单不会对任何会话生效。"),
    ])]),
    h("div", { class: "field-grid" }, [
      h("label", { class: "check-row field-wide", for: "plugin-enabled" }, [
        h("input", { id: "plugin-enabled", type: "checkbox", checked: config.enabled,
          onChange: (event) => { config.enabled = event.target.checked; } }),
        h("span", "启用插件（总开关）"),
        h("small", "总开关决定人格与动态上下文是否生效，各模块开关仍独立保存。"),
      ]),
      h("label", { class: "field wide", for: "allowed-sessions" }, [
        h("span", "允许的私聊会话 UMO"),
        h("textarea", { id: "allowed-sessions", rows: 3, value: sessionsText.value,
          placeholder: "每行一个完整 UMO", onInput: (event) => { sessionsText.value = event.target.value; } }),
        h("small", "可通过 AstrBot 的 /sid 获取完整值。"),
      ]),
      h("label", { class: "field wide", for: "allowed-bots" }, [
        h("span", "允许的机器人 QQ 号"),
        h("textarea", { id: "allowed-bots", rows: 3, value: botsText.value,
          placeholder: "每行一个机器人自身 QQ 号", onInput: (event) => { botsText.value = event.target.value; } }),
        h("small", "需要同时匹配会话 UMO 与机器人自身账号，避免跨会话和跨账号串用。"),
      ]),
    ]),
  ]);
}

function renderModuleDetail(state) {
  const { config, active, busy, dynamicStatus, browserTimezone, setValidity, relationFilled } = state;
  const section = active.value;
  if (section === "schedule_timeline") return renderSchedule(state);
  if (section === "schedule_settings") return renderScheduleSettings(state);
  if (section === "general") return renderGeneral(state);
  if (section === "identity_control") return renderIdentityControl(config);
  if (section === "examples") return h("section", { class: "panel detail", "data-section": section }, [
    h("div", { class: "panel-title" }, [h("div", [h("h2", "对话示例"),
      h("p", "示例只学习节奏和措辞，不会成为真实记忆或工具执行结果。")])]),
    h("textarea", { id: "persona-examples", class: "examples", rows: 18, value: config.examples || "",
      placeholder: "情境：普通闲聊\n用户：我刚回家。\n角色：路上顺利吗？",
      onInput: (event) => { config.examples = event.target.value; } }),
  ]);
  const fields = fieldGroups[section] || [];
  return h("section", { class: "panel detail", "data-section": section }, [
    h("div", { class: "panel-title" }, [
      h("div", [h("h2", labels[section] || "模块配置"), h("p", descriptions[section] || "")]),
      h("span", { class: "count" }, `${fields.length} 个字段`),
    ]),
    section === "dynamic_state" ? h("div", { class: "dynamic-state-overview" }, [
      h("div", { class: `dynamic-state-status ${dynamicStatus.value.active ? "is-active" : ""}`,
        role: "status", "aria-live": "polite" }, [
        h("small", "已保存状态 · 实时有效期"),
        h("strong", { id: "dynamic-state-status" }, dynamicStatus.value.title),
        h("p", dynamicStatus.value.detail),
      ]),
      h("p", { class: "timezone-note" }, `时间输入使用浏览器时区：${browserTimezone}；保存为带时区的 ISO 时间。`),
      h("div", { class: "validity-actions" }, [h("span", "从现在开始："),
        ...[30, 60, 120].map((minutes) => h("button", { key: minutes, type: "button",
          "data-validity-minutes": minutes, disabled: busy.value,
          onClick: () => setValidity(minutes) }, `${minutes} 分钟`)),
      ]),
      h("p", { class: "timezone-note" }, "快捷设置只更新草稿；保存后生效，不自动启用或续期。"),
    ]) : null,
    h("div", { class: "field-grid" }, fields.map((field) => renderField(config, section, field))),
    section === "dynamic_state" ? h("div", { class: "tip" }, "状态必须绑定允许的会话和机器人。来源由你人工确认；过期只停止注入，不代表活动完成。") : null,
    section === "relationship" && !relationFilled.value ? h("div", { class: "tip" }, "关系字段留空时不预设亲密关系。") : null,
  ]);
}

function renderApp(state) {
  const {
    config, summary, active, activeModule, visibleSections, selectModule, selectSection,
    busy, message, messageKind, sections, save, loaded, scheduleBusy,
  } = state;
  const module = MODULES[activeModule.value];
  const subheading = ["persona", "schedule"].includes(activeModule.value) ? labels[active.value] : "";
  const moduleStatus = !loaded.value ? "等待读取配置"
    : activeModule.value === "schedule" ? `日程开关（草稿）：${config.schedule.enabled ? "开启" : "关闭"}`
    : activeModule.value === "state" ? `当前状态开关（草稿）：${config.dynamic_state.enabled ? "开启" : "关闭"}`
    : activeModule.value === "general" ? `总开关（草稿）：${config.enabled ? "开启" : "关闭"}`
    : `已保存身份控制：${summary.authority_mode === "character_owner" ? "角色主控" : "叠加"}`;
  return h("div", { class: "app-shell" }, [
    h("nav", { class: "module-nav", "aria-label": "一级模块导航" },
      Object.entries(MODULES).map(([key, item]) => h("button", {
        key, type: "button", "data-module": key,
        class: activeModule.value === key ? "active" : "",
        "aria-pressed": activeModule.value === key,
        onClick: () => selectModule(key),
      }, item.title))),
    h("header", { class: "hero" }, [
      h("div", [h("p", { class: "eyebrow" }, "DIGITAL LIFE · MODULES"),
        h("h1", "数字生命 · 模块配置"),
        h("p", { class: "module-breadcrumb", "data-testid": "module-breadcrumb" },
          `${module.title}${subheading ? ` > ${subheading}` : ""}`),
        h("p", { class: "lead" }, module.description),
      ]),
      h("div", { class: `summary ${summary.valid ? "valid" : ""}` }, [
        h("b", summary.enabled ? "插件已启用" : "插件未启用"),
        h("span", `已保存配置：${summary.valid ? "有效" : "未完成"}`),
        h("span", moduleStatus), h("span", `版本：${summary.version}`),
        summary.config_error ? h("small", summary.config_error) : null,
      ]),
    ]),
    message.value ? h("div", { class: `flash ${messageKind.value}`, role: "status" }, message.value) : null,
    h("div", { class: `workspace ${visibleSections.value.length ? "has-subnav" : "module-single"}` }, [
      visibleSections.value.length ? h("nav", { class: "tabs", "aria-label": `${module.title}二级目录` },
        visibleSections.value.map((key) => h("button", {
          key, type: "button", "data-section": key,
          class: active.value === key ? "active" : "",
          "aria-current": active.value === key ? "page" : undefined,
          onClick: () => selectSection(key),
        }, labels[key]))) : null,
      h("main", { class: "content", "data-active-module": activeModule.value }, [renderModuleDetail(state)]),
    ]),
    h("footer", [h("span", "统一保存所有模块配置；切换模块保留草稿。今日时间段请使用日程内的专用保存按钮。"),
      h("button", { class: "save", type: "button", disabled: !loaded.value || busy.value || scheduleBusy.value,
        onClick: save }, busy.value ? "保存中…" : !loaded.value ? "等待读取配置" : "保存全部配置"),
    ]),
  ]);
}

createApp(App).mount("#app");
