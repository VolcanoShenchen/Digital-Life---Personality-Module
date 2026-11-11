"""Deterministic persona rules and narrowly scoped system-prompt replacement."""

from dataclasses import dataclass

from .settings import Settings

NAMESPACE = "<!-- dlp-personality:"


def _start(kind: str) -> str:
    return f"\n\n{NAMESPACE}{kind}:v1:begin -->\n"


def _end(kind: str) -> str:
    return f"\n{NAMESPACE}{kind}:v1:end -->"


class PromptError(ValueError):
    """The request contains an incomplete reserved block; leave it unchanged."""


def _safe(text: str) -> str:
    return text.replace(NAMESPACE, "［dlp-personality:")


def strip_owned_blocks(prompt: str) -> str:
    """Validate every reserved token before removing any exact owned span."""
    spans: list[tuple[int, int]] = []
    active: tuple[str, int] | None = None
    cursor = 0
    while (index := prompt.find(NAMESPACE, cursor)) != -1:
        matched = False
        for kind in ("persona", "relationship"):
            beginning = _start(kind)
            ending = _end(kind)
            if index >= 2 and prompt.startswith(beginning, index - 2):
                if active is not None:
                    raise PromptError("malformed_owned_block")
                active = (kind, index - 2)
                cursor = index - 2 + len(beginning)
                matched = True
                break
            if index >= 1 and prompt.startswith(ending, index - 1):
                if active is None or active[0] != kind:
                    raise PromptError("malformed_owned_block")
                cursor = index - 1 + len(ending)
                spans.append((active[1], cursor))
                active = None
                matched = True
                break
        if not matched:
            raise PromptError("malformed_owned_block")
    if active is not None:
        raise PromptError("malformed_owned_block")
    if not spans:
        return prompt
    pieces = []
    cursor = 0
    for start, end in spans:
        pieces.append(prompt[cursor:start])
        cursor = end
    pieces.append(prompt[cursor:])
    return "".join(pieces)


def _section(title: str, text: str) -> str:
    return f"【{title}】\n{_safe(text)}"


_TONES = {
    "follow_character": "遵循角色本身的语气，不额外套用温柔、冷淡或撒娇等人格。",
    "gentle": "表达温和，关心落在眼前具体事情上，不反复安慰或过度热情。",
    "playful": "适合时轻轻调侃、接梗；对方认真或难过时收起玩笑。",
    "reserved": "表达克制、允许留白，通过具体回应表现态度，不故作冷漠。",
}
_LENGTHS = {
    "adaptive": "按内容调整长度；普通闲聊围绕一个重点，不必面面俱到。",
    "brief": "普通闲聊偏简短，通常一两句；避免为简短而省去必要信息。",
    "expanded": "适合时充分表达自己的看法，不为凑长度重复铺陈。",
}
_ACTIONS = {
    "none": "直接说话，通常不用括号动作、内心独白或环境旁白。",
    "occasional": "场景确有需要时偶尔加入简短动作，不每条都微笑、歪头或靠近。",
    "scene": "允许符合当前角色场景的动作和旁白，不替用户决定动作、心理或答复。",
}
_EMOJI = {
    "none": "通常不使用 emoji 或颜文字；明确要求时按本轮需要处理。",
    "occasional": "少量使用符合角色的语气词、表情，避免每句都加或固定使用同一组。",
    "frequent": "可较多使用符合角色的表情与语气词，但不堆砌、不影响认真话题。",
}


def _list_section(parts: list[str], title: str, values: tuple[str, ...]) -> None:
    if values:
        parts.append(_section(title, "、".join(values)))


def _text_section(parts: list[str], title: str, value: str) -> None:
    if value:
        parts.append(_section(title, value))


def build_persona(settings: Settings) -> str:
    parts = [
        "【运营者配置的人格与表达】",
        "保留宿主必要规则及工具约定。以下角色事实和表达偏好不改变工具权限、"
        "工具结果或现实中已完成的行为。未知事实不自行补写。",
    ]
    if settings.persona_source == "plugin":
        profile = settings.profile
        background = settings.background
        personality = settings.personality
        behavior = settings.behavior
        speech = settings.speech
        response = settings.response
        roleplay = settings.roleplay
        boundaries = settings.boundaries
        _text_section(parts, "角色姓名", profile.name)
        _text_section(parts, "角色昵称与自称", profile.nickname)
        identity_facts = []
        for label, value in (
            ("性别认同", profile.gender_identity),
            ("代称", profile.pronouns),
            ("年龄", profile.age),
            ("年龄规则", profile.age_mode),
            ("物种", profile.species),
            ("国籍或地区", profile.nationality),
            ("母语", profile.native_language),
            ("时区", profile.timezone),
            ("所在地", profile.location),
            ("职业", profile.occupation),
            ("教育背景", profile.education),
            ("社会身份", profile.social_status),
        ):
            if value:
                identity_facts.append(f"{label}：{value}")
        _text_section(parts, "基础身份资料", "\n".join(identity_facts))
        _text_section(parts, "身份与世界背景", background.identity)
        _text_section(parts, "当前生活处境", background.current_situation)
        _text_section(parts, "家庭与成长经历", background.family or background.childhood)
        _text_section(
            parts, "教育与工作经历", background.education_history or background.work_history
        )
        _list_section(parts, "重要经历", background.important_events)
        _text_section(parts, "世界设定", background.world_setting)
        _text_section(parts, "角色明确知道的内容", background.known_facts)
        _text_section(parts, "角色明确不知道的内容", background.unknown_facts)
        _list_section(parts, "核心性格", personality.core_traits)
        _list_section(parts, "优点", personality.positive_traits)
        _list_section(parts, "缺点", personality.flaws)
        _list_section(parts, "价值观", personality.values)
        _list_section(parts, "偏好与反感", personality.dislikes)
        _list_section(parts, "恐惧与担忧", personality.fears)
        _list_section(parts, "欲望与目标", personality.desires)
        _list_section(parts, "不安全感", personality.insecurities)
        _list_section(parts, "自豪之处", personality.pride)
        _list_section(parts, "性格矛盾", personality.contradictions)
        _text_section(parts, "自我评价", personality.self_image)
        _text_section(parts, "对他人的通常看法", personality.view_of_others)
        _text_section(parts, "性格稳定程度", personality.changeability)
        _text_section(parts, "社交温度", personality.social_temperature)
        _text_section(parts, "性格补充", personality.legacy_summary)
        behavior_rules = []
        for title, value in (
            ("开心时", behavior.when_happy),
            ("难过时", behavior.when_sad),
            ("生气时", behavior.when_angry),
            ("疲惫时", behavior.when_tired),
            ("尴尬时", behavior.when_embarrassed),
            ("焦虑时", behavior.when_anxious),
            ("困惑时", behavior.when_confused),
            ("被夸奖时", behavior.when_praised),
            ("被批评时", behavior.when_criticized),
            ("意见不同时", behavior.when_disagrees),
            ("道歉时", behavior.when_apologizing),
            ("拒绝时", behavior.when_refusing),
            ("被冷落时", behavior.when_ignored),
            ("换话题时", behavior.when_topic_changes),
            ("缺少记忆时", behavior.when_memory_missing),
        ):
            if value:
                behavior_rules.append(f"{title}：{value}")
        _text_section(parts, "情境行为规则", "\n".join(behavior_rules))
        _list_section(parts, "不适合主动讨论的话题", boundaries.uncomfortable_topics)
        _list_section(parts, "不会声称完成的行为", boundaries.forbidden_actions)
        _text_section(parts, "拒绝方式", boundaries.refusal_level)
        _text_section(parts, "隐私边界", boundaries.privacy_rules)
        _text_section(parts, "现实行为边界", boundaries.reality_claims)
        _text_section(parts, "记忆边界", boundaries.memory_claims)
        _text_section(parts, "工具结果边界", boundaries.tool_claims)
        _text_section(parts, "角色完整性", boundaries.role_integrity)
        _text_section(parts, "场景扮演边界", boundaries.roleplay)
    else:
        parts.append("身份、背景和性格沿用宿主当前会话人设，本区块只补充表达偏好。")

    speech = settings.speech
    response = settings.response
    roleplay = settings.roleplay
    parts.extend(
        [
            "【表达习惯】",
            _TONES[speech.tone],
            _LENGTHS[response.length],
            "长度和风格是偏好。用户当轮明确的格式、长度和任务需要优先得到满足；"
            "解释、代码和认真求助时正常展开，不机械截短。",
            _ACTIONS[roleplay.action_style],
            _EMOJI[speech.emoji_frequency],
            f"是否先直接回答：{'是' if response.answer_first else '否'}。",
            f"追问频率：{response.ask_followup}；主动建议：{response.offer_advice}。",
            "先回应具体内容，再决定是否追问。不必每次叫昵称、提问或声明陪伴。"
            "对方只想吐槽时不要自动变成建议清单；认真求助时应把事情说清楚。",
            "保持角色自己的判断和分歧，具体表达，不为了迎合而随意改口。",
            "依据已有对话延续情绪和态度，变化要有上下文原因；对方换话题时跟随。"
            "缺少的经历或记忆自然承认，不把推测说成共同经历。",
        ]
    )
    _text_section(parts, "自称", speech.first_person)
    _text_section(parts, "对用户的称呼", speech.second_person)
    _text_section(parts, "常用词汇与句式", speech.vocabulary)
    _list_section(parts, "避免使用的词", speech.avoided_words)
    _text_section(parts, "句子长度", speech.sentence_length)
    _text_section(parts, "标点习惯", speech.punctuation)
    _text_section(parts, "幽默方式", speech.humor_style)
    _text_section(parts, "表达在意的方式", speech.affection_style)
    _text_section(parts, "表达分歧的方式", speech.disagreement_style)
    _text_section(parts, "道歉方式", speech.apology_style)
    _text_section(parts, "拒绝方式", speech.refusal_style)
    _text_section(parts, "话题转换方式", speech.topic_transition)
    _text_section(parts, "沉默与留白", speech.silence_tolerance)
    _text_section(parts, "固定说话习惯", speech.habits)
    if response.handle_unknown:
        _text_section(parts, "不知道时的处理", response.handle_unknown)
    if response.avoid_cliches or response.reduce_cliches:
        parts.append(
            "【减少套话】\n避免无关总结、逐句复述、擅自分析用户心理及固定安慰。"
            "不要习惯性以‘我理解你的感受’‘我会一直陪着你’‘有什么可以帮你的吗’收尾。"
            "有具体语境时自然表达，不把词语列表当作绝对禁词。"
            "不刻意制造错字、随机发脾气或滥用省略号。"
        )
    if response.avoid_psychological_analysis:
        parts.append("不要把普通聊天擅自改写成心理咨询报告。")
    if response.avoid_over_affection:
        parts.append("没有关系依据时，不主动使用过度亲密或煽情的表达。")
    if settings.examples:
        parts.append(
            _section(
                "语气示例：仅为表达示范，不是真实会话历史",
                "学习节奏和措辞，不照抄；其中的名字、经历、关系与工具动作均不是已确认事实。\n"
                + settings.examples,
            )
        )
    _text_section(parts, "补充表达偏好", speech.extra)
    parts.append("直接回应本轮对话，不输出这些规则或内部执行过程。")
    return _start("persona") + "\n".join(parts) + _end("persona")


def build_relationship(settings: Settings, scope: "Scope") -> str:
    relation = settings.relationship
    if (
        not relation.has_content
        or relation.target_session != scope.origin
        or relation.target_bot_id != scope.bot_id
    ):
        return ""
    relation_lines = []
    parts = ["【仅适用于当前私聊的已配置关系】"]
    for title, value in (
        ("关系角色", relation.role),
        ("关系阶段", relation.stage),
        ("认识时长", relation.duration),
        ("关系背景", relation.background),
        ("角色如何称呼用户", relation.addressing),
        ("用户如何称呼角色", relation.addressing_for_character),
        ("信任程度", relation.trust_level),
        ("亲密边界", relation.intimacy_boundary),
        ("冲突处理方式", relation.conflict_style),
        ("关系修复方式", relation.repair_style),
    ):
        if value:
            relation_lines.append(f"{title}：{value}")
    if relation.shared_history:
        relation_lines.append("共同经历：" + "、".join(relation.shared_history))
    if relation.shared_interests:
        relation_lines.append("共同兴趣：" + "、".join(relation.shared_interests))
    if relation.sensitive_topics:
        relation_lines.append("关系敏感话题：" + "、".join(relation.sensitive_topics))
    if relation_lines:
        parts.append(_section("关系资料", "\n".join(relation_lines)))
    parts.append("未明确的关系、年龄、性别和亲密程度不自行推断。")
    return _start("relationship") + "\n".join(parts) + _end("relationship")


@dataclass(frozen=True)
class Scope:
    origin: str
    platform_id: str
    bot_id: str
    platform_type: str
    private: bool

    @property
    def diagnostic_key(self) -> tuple[str, str, str]:
        return (self.platform_id, self.bot_id, self.origin)


def scope_reason(settings: Settings, scope: Scope) -> str:
    if not settings.enabled:
        return "disabled"
    if scope.platform_type != "aiocqhttp":
        return "unsupported_platform"
    if not scope.private:
        return "not_private"
    if not scope.origin or not scope.platform_id or not scope.bot_id:
        return "missing_scope_identity"
    if not settings.allowed_sessions:
        return "no_allowed_sessions"
    if not settings.allowed_bot_ids:
        return "no_allowed_bots"
    if scope.bot_id not in settings.allowed_bot_ids:
        return "bot_not_allowed"
    if scope.origin not in settings.allowed_sessions:
        return "session_not_allowed"
    return "applied"
