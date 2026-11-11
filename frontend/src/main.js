import { createApp, reactive, ref, computed, onMounted, h } from "vue";
import "./style.css";

const bridge = window.AstrBotPluginView;

const list = (value) => (Array.isArray(value) ? [...value] : []);

const blankConfig = () => ({
  enabled: false,
  persona_source: "plugin",
  allowed_sessions: [],
  allowed_bot_ids: [],
  profile: {
    name: "", nickname: "", gender_identity: "", pronouns: "", age: "", age_mode: "fixed",
    birth_date: "", species: "", nationality: "", native_language: "", timezone: "",
    location: "", occupation: "", education: "", social_status: "",
  },
  background: {
    identity: "", family: "", childhood: "", education_history: "", work_history: "",
    important_events: [], current_situation: "", secrets: [], world_setting: "",
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

const labels = {
  profile: "基础资料", background: "经历与世界", personality: "性格核心", behavior: "情境行为",
  relationship: "专属关系", speech: "说话方式", response: "回复策略", roleplay: "动作与场景",
  boundaries: "边界保护",
};

const descriptions = {
  profile: "稳定的身份事实。这里填写“她是谁”。",
  background: "成长经历、当前处境和世界知识。未知内容不自动编造。",
  personality: "性格倾向、价值观、缺点和内在矛盾。",
  behavior: "遇到具体情绪和互动时，她会怎么反应。",
  relationship: "只对绑定的私聊会话和机器人生效。",
  speech: "词汇、句式、标点、称呼和幽默习惯。",
  response: "回复长度、追问、建议和套话策略。",
  roleplay: "动作、场景和旁白偏好；不会替用户决定动作。",
  boundaries: "隐私、现实行为、记忆、工具和角色完整性保护。",
};

const options = {
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
  profile: [
    ["name", "姓名", "text", "角色的正式姓名或主要称呼。"], ["nickname", "昵称", "text", "常用昵称或自称。"],
    ["gender_identity", "性别认同", "text", "例如女性、男性、非二元或自定义。"], ["pronouns", "代称", "text", "角色希望如何被指代。"],
    ["age", "年龄", "text", "可以填写数字或文字年龄。"], ["age_mode", "年龄模式", "select", "年龄是固定、增长还是按角色时间线计算。"],
    ["birth_date", "出生日期", "text", "需要计算年龄时填写。"], ["species", "物种", "text", "例如人类、仿生人、精灵。"],
    ["nationality", "国籍或地区", "text", "角色的地域背景。"], ["native_language", "母语", "text", "语言背景。"],
    ["timezone", "所在时区", "text", "例如 Asia/Shanghai。"], ["location", "所在地", "text", "常住地或当前生活地点。"],
    ["occupation", "职业", "text", "职业、身份或主要活动。"], ["education", "教育背景", "textarea", "专业、学校或知识背景。"],
    ["social_status", "社会身份", "textarea", "家庭、社会身份或经济状况。"],
  ],
  background: [
    ["identity", "身份与背景", "textarea", "角色是谁、身处什么背景。启用 plugin 模式时必填。"], ["family", "家庭关系", "textarea", "家庭结构与相处方式。"],
    ["childhood", "童年经历", "textarea", "塑造角色的重要成长经历。"], ["education_history", "学习经历", "textarea", "教育经历。"],
    ["work_history", "工作经历", "textarea", "工作经历。"], ["important_events", "重要事件", "list", "每行一项。"],
    ["current_situation", "当前处境", "textarea", "角色现在的生活状态。"], ["secrets", "秘密", "list", "角色不会随意主动透露的内容。"],
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

function renderField(config, group, field) {
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
  const summary = reactive({ version: "—", valid: false, enabled: false, config_error: "" });
  const active = ref("profile");
  const busy = ref(false);
  const message = ref("");
  const messageKind = ref("ok");
  const sections = Object.keys(fieldGroups);

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

  async function load() {
    try {
      await connect();
      const result = await withTimeout(
        bridge.apiGet("settings"),
        "读取配置超时，请刷新或从插件详情页重新打开",
      );
      mergeDeep(config, result.config || {});
      Object.assign(summary, result.summary || {});
    } catch (error) {
      message.value = `读取配置失败：${error.message || error}`;
      messageKind.value = "error";
    }
  }

  async function save() {
    busy.value = true;
    message.value = "保存中…";
    try {
      await connect();
      const payload = JSON.parse(JSON.stringify(config));
      const result = await withTimeout(
        bridge.apiPost("settings", payload),
        "保存超时，请确认插件仍已启用后重试",
      );
      mergeDeep(config, result.config || payload);
      Object.assign(summary, result.summary || {});
      message.value = "已保存，新请求立即使用新配置。";
      messageKind.value = "ok";
    } catch (error) {
      message.value = `保存失败：${error.message || error}`;
      messageKind.value = "error";
    } finally {
      busy.value = false;
    }
  }

  onMounted(load);

  return {
    config, summary, active, busy, message, messageKind, sections,
    sessionsText, botsText, relationFilled, save,
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

function renderApp(state) {
  const {
    config, summary, active, busy, message, messageKind, sections,
    sessionsText, botsText, relationFilled, save,
  } = state;
  return h("div", { class: "app-shell" }, [
    h("header", { class: "hero" }, [
      h("div", [
        h("p", { class: "eyebrow" }, "DIGITAL LIFE · PERSONALITY"),
        h("h1", "人格与表达配置"),
        h("p", { class: "lead" }, "把“她是谁”和“她怎么回应”分开填写。每个字段只承担一个作用，保存后立即用于新的模型请求。"),
      ]),
      h("div", { class: `summary ${summary.valid ? "valid" : ""}` }, [
        h("b", summary.enabled ? "已启用" : "未启用"),
        h("span", `配置：${summary.valid ? "有效" : "未完成"}`),
        h("span", `版本：${summary.version}`),
        summary.config_error ? h("small", summary.config_error) : null,
      ]),
    ]),
    message.value ? h("div", { class: `flash ${messageKind.value}` }, message.value) : null,
    h("div", { class: "scope-card" }, [
      h("div", [
        h("b", "生效范围"),
        h("small", "需要同时匹配完整私聊 UMO 和机器人自身 QQ 号。留空不会对任何会话生效。"),
      ]),
      h("label", { class: "switch" }, [
        h("input", {
          type: "checkbox",
          checked: config.enabled,
          onChange: (event) => { config.enabled = event.target.checked; },
        }),
        h("span", "启用"),
      ]),
    ]),
    h("section", { class: "panel basics" }, [
      h("div", { class: "panel-title" }, [
        h("div", [
          h("h2", "基础作用域"),
          h("p", "先填写范围，再配置角色。不会自动猜测用户或机器人身份。"),
        ]),
        h("select", {
          value: config.persona_source,
          onChange: (event) => { config.persona_source = event.target.value; },
        }, [
          h("option", { value: "plugin" }, "插件管理完整人格"),
          h("option", { value: "astrbot" }, "沿用 AstrBot 人格，只调整表达"),
        ]),
      ]),
      h("div", { class: "basic-grid" }, [
        h("label", { class: "field wide" }, [
          h("span", "允许的私聊会话 UMO"),
          h("textarea", {
            rows: 3,
            value: sessionsText.value,
            placeholder: "每行一个完整 UMO",
            onInput: (event) => { sessionsText.value = event.target.value; },
          }),
          h("small", "可通过 AstrBot 的 /sid 获取。"),
        ]),
        h("label", { class: "field wide" }, [
          h("span", "允许的机器人 QQ 号"),
          h("textarea", {
            rows: 3,
            value: botsText.value,
            placeholder: "每行一个机器人自身 QQ 号",
            onInput: (event) => { botsText.value = event.target.value; },
          }),
          h("small", "用于隔离同一适配器中的多个机器人。"),
        ]),
      ]),
    ]),
    h("div", { class: "workspace" }, [
      h("nav", { class: "tabs" }, [
        ...sections.map((key) =>
          h("button", {
            class: active.value === key ? "active" : "",
            onClick: () => { active.value = key; },
          }, labels[key])),
        h("button", {
          class: active.value === "examples" ? "active" : "",
          onClick: () => { active.value = "examples"; },
        }, "对话示例"),
      ]),
      h("main", { class: "content" }, [
        active.value === "examples"
          ? h("section", { class: "panel detail" }, [
              h("div", { class: "panel-title" }, [
                h("div", [
                  h("h2", "对话示例"),
                  h("p", "示例只学习节奏和措辞，不会成为真实记忆或工具执行结果。"),
                ]),
              ]),
              h("textarea", {
                class: "examples",
                rows: 18,
                value: config.examples || "",
                placeholder: "情境：普通闲聊\n用户：我刚回家。\n角色：路上顺利吗？",
                onInput: (event) => { config.examples = event.target.value; },
              }),
            ])
          : h("section", { class: "panel detail" }, [
              h("div", { class: "panel-title" }, [
                h("div", [
                  h("h2", labels[active.value]),
                  h("p", descriptions[active.value]),
                ]),
                h("span", { class: "count" }, `${fieldGroups[active.value].length} 个字段`),
              ]),
              h("div", { class: "field-grid" }, fieldGroups[active.value].map((field) => renderField(config, active.value, field))),
              active.value === "relationship" && !relationFilled.value
                ? h("div", { class: "tip" }, "关系字段全部留空时，不会预设任何亲密关系。")
                : null,
            ]),
      ]),
    ]),
    h("footer", [
      h("span", "结构化配置兼容旧版 character / expression 字段。"),
      h("button", { class: "save", disabled: busy.value, onClick: save }, busy.value ? "保存中…" : "保存配置"),
    ]),
  ]);
}

createApp(App).mount("#app");
