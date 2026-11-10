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


def build_persona(settings: Settings) -> str:
    parts = [
        "【运营者配置的人格与表达】",
        "保留宿主必要规则及工具约定。以下角色事实和表达偏好不改变工具权限、"
        "工具结果或现实中已完成的行为。未知事实不自行补写。",
    ]
    if settings.persona_source == "plugin":
        character = settings.character
        parts.extend(
            [
                _section("角色称呼", character.name),
                _section("角色身份与背景", character.identity),
                _section("性格、立场与偏好", character.personality),
            ]
        )
        if character.boundaries:
            parts.append(_section("角色边界", character.boundaries))
    else:
        parts.append("身份、背景和性格沿用宿主当前会话人设，本区块只补充表达偏好。")
    expression = settings.expression
    parts.extend(
        [
            "【表达习惯】",
            _TONES[expression.tone],
            _LENGTHS[expression.length],
            "长度和风格是偏好。用户当轮明确的格式、长度和任务需要优先得到满足；"
            "解释、代码和认真求助时正常展开，不机械截短。",
            _ACTIONS[expression.actions],
            _EMOJI[expression.emoji],
            "先回应具体内容，再决定是否追问。不必每次叫昵称、提问或声明陪伴。"
            "对方只想吐槽时不要自动变成建议清单；认真求助时应把事情说清楚。",
            "保持角色自己的判断和分歧，具体表达，不为了迎合而随意改口。",
            "依据已有对话延续情绪和态度，变化要有上下文原因；对方换话题时跟随。"
            "缺少的经历或记忆自然承认，不把推测说成共同经历。",
        ]
    )
    if expression.habits:
        parts.append(_section("固定说话习惯", expression.habits))
    if expression.reduce_cliches:
        parts.append(
            "【减少套话】\n避免无关总结、逐句复述、擅自分析用户心理及固定安慰。"
            "不要习惯性以‘我理解你的感受’‘我会一直陪着你’‘有什么可以帮你的吗’收尾。"
            "有具体语境时自然表达，不把词语列表当作绝对禁词。"
            "不刻意制造错字、随机发脾气或滥用省略号。"
        )
    if settings.examples:
        parts.append(
            _section(
                "语气示例：仅为表达示范，不是真实会话历史",
                "学习节奏和措辞，不照抄；其中的名字、经历、关系与工具动作均不是已确认事实。\n"
                + settings.examples,
            )
        )
    if expression.extra:
        parts.append(_section("补充表达偏好", expression.extra))
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
    parts = ["【仅适用于当前私聊的已配置关系】"]
    if relation.background:
        parts.append(_section("关系背景", relation.background))
    if relation.addressing:
        parts.append(_section("称呼与使用场景", relation.addressing))
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
