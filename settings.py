"""Structured, immutable configuration for the personality plugin."""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any

TEXT_BUDGET = 12_000


class ConfigError(ValueError):
    """An error containing only a known field name and a fixed reason code."""

    def __init__(self, field: str, code: str):
        self.field = field
        self.code = code
        super().__init__(f"{field}: {code}")


def _object(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, Mapping):
        raise ConfigError(key, "expected_object")
    return value


def _text(data: Mapping[str, Any], key: str, prefix: str = "") -> str:
    value = data.get(key, "")
    if not isinstance(value, str):
        raise ConfigError(prefix + key, "expected_text")
    return value.strip()


def _boolean(data: Mapping[str, Any], key: str, default: bool, prefix: str = "") -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(prefix + key, "expected_boolean")
    return value


def _choice(data: Mapping[str, Any], key: str, choices: tuple[str, ...], prefix: str = "") -> str:
    value = data.get(key, choices[0])
    if not isinstance(value, str) or value not in choices:
        raise ConfigError(prefix + key, "invalid_choice")
    return value


def _id_list(data: Mapping[str, Any], key: str) -> frozenset[str]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise ConfigError(key, "expected_list")
    identifiers = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(key, "expected_nonempty_identifier")
        identifiers.add(item.strip())
    return frozenset(identifiers)


def _text_list(data: Mapping[str, Any], key: str, prefix: str = "") -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise ConfigError(prefix + key, "expected_list")
    result = []
    for item in value:
        if not isinstance(item, str):
            raise ConfigError(prefix + key, "expected_text_items")
        item = item.strip()
        if item:
            result.append(item)
    return tuple(result)


def _migrate_legacy(data: Mapping[str, Any]) -> dict[str, Any]:
    """Fill structured sections from the first-version free-text fields."""
    raw = deepcopy(dict(data))
    character = raw.get("character") if isinstance(raw.get("character"), Mapping) else {}
    expression = raw.get("expression") if isinstance(raw.get("expression"), Mapping) else {}
    profile = dict(raw.get("profile") or {})
    background = dict(raw.get("background") or {})
    personality = dict(raw.get("personality") or {})
    speech = dict(raw.get("speech") or {})
    response = dict(raw.get("response") or {})
    roleplay = dict(raw.get("roleplay") or {})
    boundaries = dict(raw.get("boundaries") or {})

    profile.setdefault("name", character.get("name", ""))
    background.setdefault("identity", character.get("identity", ""))
    personality.setdefault("legacy_summary", character.get("personality", ""))
    boundaries.setdefault("roleplay", character.get("boundaries", ""))
    speech.setdefault("habits", expression.get("habits", ""))
    speech.setdefault("tone", expression.get("tone", "follow_character"))
    speech.setdefault("emoji_frequency", expression.get("emoji", "occasional"))
    response.setdefault("length", expression.get("length", "adaptive"))
    response.setdefault("reduce_cliches", expression.get("reduce_cliches", True))
    roleplay.setdefault("action_style", expression.get("actions", "none"))
    speech.setdefault("extra", expression.get("extra", ""))

    raw.update(
        {
            "profile": profile,
            "background": background,
            "personality": personality,
            "speech": speech,
            "response": response,
            "roleplay": roleplay,
            "boundaries": boundaries,
        }
    )
    return raw


@dataclass(frozen=True)
class PersonaAuthority:
    mode: str = "overlay"
    suppress_generic_assistant_identity: bool = True
    allow_technical_identity_disclosure: bool = True


@dataclass(frozen=True)
class Character:
    """Legacy compatibility view of the original character fields."""

    name: str = ""
    identity: str = ""
    personality: str = ""
    boundaries: str = ""


@dataclass(frozen=True)
class Profile:
    name: str = ""
    nickname: str = ""
    gender_identity: str = ""
    pronouns: str = ""
    age: str = ""
    age_mode: str = "fixed"
    birth_date: str = ""
    species: str = ""
    nationality: str = ""
    native_language: str = ""
    timezone: str = ""
    location: str = ""
    occupation: str = ""
    education: str = ""
    social_status: str = ""


@dataclass(frozen=True)
class Background:
    identity: str = ""
    family: str = ""
    childhood: str = ""
    education_history: str = ""
    work_history: str = ""
    important_events: tuple[str, ...] = ()
    current_situation: str = ""
    secrets: tuple[str, ...] = ()
    world_setting: str = ""
    known_facts: str = ""
    unknown_facts: str = ""


@dataclass(frozen=True)
class Personality:
    core_traits: tuple[str, ...] = ()
    positive_traits: tuple[str, ...] = ()
    flaws: tuple[str, ...] = ()
    values: tuple[str, ...] = ()
    dislikes: tuple[str, ...] = ()
    fears: tuple[str, ...] = ()
    desires: tuple[str, ...] = ()
    insecurities: tuple[str, ...] = ()
    pride: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    self_image: str = ""
    view_of_others: str = ""
    changeability: str = "stable"
    social_temperature: str = "slow"
    legacy_summary: str = ""


@dataclass(frozen=True)
class Behavior:
    when_happy: str = ""
    when_sad: str = ""
    when_angry: str = ""
    when_tired: str = ""
    when_embarrassed: str = ""
    when_anxious: str = ""
    when_bored: str = ""
    when_confused: str = ""
    when_praised: str = ""
    when_criticized: str = ""
    when_disagrees: str = ""
    when_apologizing: str = ""
    when_refusing: str = ""
    when_ignored: str = ""
    when_topic_changes: str = ""
    when_memory_missing: str = ""


@dataclass(frozen=True)
class Speech:
    first_person: str = ""
    second_person: str = ""
    vocabulary: str = ""
    avoided_words: tuple[str, ...] = ()
    sentence_length: str = "adaptive"
    punctuation: str = ""
    question_frequency: str = "necessary"
    emoji_frequency: str = "occasional"
    humor_style: str = ""
    affection_style: str = ""
    disagreement_style: str = ""
    apology_style: str = ""
    refusal_style: str = ""
    greeting_style: str = ""
    goodbye_style: str = ""
    correction_style: str = ""
    topic_transition: str = ""
    silence_tolerance: str = ""
    habits: str = ""
    tone: str = "follow_character"
    extra: str = ""


@dataclass(frozen=True)
class ResponsePolicy:
    length: str = "adaptive"
    answer_first: bool = True
    ask_followup: str = "necessary"
    offer_advice: str = "when_requested"
    repeat_user: bool = False
    handle_unknown: str = "自然承认不知道，不把猜测说成事实。"
    avoid_cliches: bool = True
    avoid_psychological_analysis: bool = True
    avoid_over_affection: bool = True
    reduce_cliches: bool = True


@dataclass(frozen=True)
class Roleplay:
    action_style: str = "none"
    action_format: str = "short_narration"
    environment_detail: str = "light"
    inner_monologue: bool = False
    sensory_detail: bool = False


@dataclass(frozen=True)
class Boundaries:
    uncomfortable_topics: tuple[str, ...] = ()
    forbidden_actions: tuple[str, ...] = ()
    refusal_level: str = "clear"
    privacy_rules: str = ""
    reality_claims: str = "不要把未知的现实行为说成已经完成。"
    memory_claims: str = "不要把示例、推测或缺失上下文当作真实记忆。"
    tool_claims: str = "不要把计划或建议说成工具已经执行。"
    role_integrity: str = "不要为了迎合用户随意改变已确认的核心身份。"
    roleplay: str = ""


@dataclass(frozen=True)
class Relationship:
    target_session: str = ""
    target_bot_id: str = ""
    role: str = ""
    stage: str = ""
    duration: str = ""
    background: str = ""
    addressing: str = ""
    addressing_for_character: str = ""
    shared_history: tuple[str, ...] = ()
    shared_interests: tuple[str, ...] = ()
    trust_level: str = ""
    intimacy_boundary: str = ""
    sensitive_topics: tuple[str, ...] = ()
    conflict_style: str = ""
    repair_style: str = ""

    @property
    def has_content(self) -> bool:
        return any(
            (
                self.background,
                self.addressing,
                self.role,
                self.stage,
                self.duration,
                self.addressing_for_character,
                self.trust_level,
                self.intimacy_boundary,
                self.conflict_style,
                self.repair_style,
                self.shared_history,
                self.shared_interests,
                self.sensitive_topics,
            )
        )


@dataclass(frozen=True)
class Expression:
    """Legacy compatibility view retained for callers of the first version."""

    habits: str = ""
    tone: str = "follow_character"
    length: str = "adaptive"
    actions: str = "none"
    emoji: str = "occasional"
    reduce_cliches: bool = True
    extra: str = ""


@dataclass(frozen=True)
class Settings:
    enabled: bool
    persona_source: str
    allowed_sessions: frozenset[str]
    allowed_bot_ids: frozenset[str]
    persona_authority: PersonaAuthority
    character: Character
    relationship: Relationship
    expression: Expression
    examples: str
    profile: Profile
    background: Background
    personality: Personality
    behavior: Behavior
    speech: Speech
    response: ResponsePolicy
    roleplay: Roleplay
    boundaries: Boundaries

    @classmethod
    def parse(cls, data: Mapping[str, Any]) -> "Settings":
        if not isinstance(data, Mapping):
            raise ConfigError("config", "expected_object")
        original = data
        legacy_character = _object(original, "character") if "character" in original else {}
        legacy_expression = _object(original, "expression") if "expression" in original else {}
        if "character" in original:
            for field in ("name", "identity", "personality", "boundaries"):
                _text(legacy_character, field, "character.")
        if "expression" in original:
            _text(legacy_expression, "habits", "expression.")
            _choice(
                legacy_expression,
                "tone",
                ("follow_character", "gentle", "playful", "reserved"),
                "expression.",
            )
            _choice(legacy_expression, "length", ("adaptive", "brief", "expanded"), "expression.")
            _choice(legacy_expression, "actions", ("none", "occasional", "scene"), "expression.")
            _choice(legacy_expression, "emoji", ("occasional", "none", "frequent"), "expression.")
            _boolean(legacy_expression, "reduce_cliches", True, "expression.")
            _text(legacy_expression, "extra", "expression.")
        data = _migrate_legacy(original)
        enabled = _boolean(data, "enabled", False)
        source = _choice(data, "persona_source", ("plugin", "astrbot"))
        sessions = _id_list(data, "allowed_sessions")
        bot_ids = _id_list(data, "allowed_bot_ids")
        authority_data = _object(data, "persona_authority")
        authority = PersonaAuthority(
            mode=_choice(
                authority_data, "mode", ("overlay", "character_owner"), "persona_authority."
            ),
            suppress_generic_assistant_identity=_boolean(
                authority_data, "suppress_generic_assistant_identity", True, "persona_authority."
            ),
            allow_technical_identity_disclosure=_boolean(
                authority_data, "allow_technical_identity_disclosure", True, "persona_authority."
            ),
        )

        profile_data = _object(data, "profile")
        profile = Profile(
            name=_text(profile_data, "name", "profile."),
            nickname=_text(profile_data, "nickname", "profile."),
            gender_identity=_text(profile_data, "gender_identity", "profile."),
            pronouns=_text(profile_data, "pronouns", "profile."),
            age=_text(profile_data, "age", "profile."),
            age_mode=_choice(
                profile_data, "age_mode", ("fixed", "growing", "timeline"), "profile."
            ),
            birth_date=_text(profile_data, "birth_date", "profile."),
            species=_text(profile_data, "species", "profile."),
            nationality=_text(profile_data, "nationality", "profile."),
            native_language=_text(profile_data, "native_language", "profile."),
            timezone=_text(profile_data, "timezone", "profile."),
            location=_text(profile_data, "location", "profile."),
            occupation=_text(profile_data, "occupation", "profile."),
            education=_text(profile_data, "education", "profile."),
            social_status=_text(profile_data, "social_status", "profile."),
        )
        background_data = _object(data, "background")
        background = Background(
            identity=_text(background_data, "identity", "background."),
            family=_text(background_data, "family", "background."),
            childhood=_text(background_data, "childhood", "background."),
            education_history=_text(background_data, "education_history", "background."),
            work_history=_text(background_data, "work_history", "background."),
            important_events=_text_list(background_data, "important_events", "background."),
            current_situation=_text(background_data, "current_situation", "background."),
            secrets=_text_list(background_data, "secrets", "background."),
            world_setting=_text(background_data, "world_setting", "background."),
            known_facts=_text(background_data, "known_facts", "background."),
            unknown_facts=_text(background_data, "unknown_facts", "background."),
        )
        personality_data = _object(data, "personality")
        personality = Personality(
            core_traits=_text_list(personality_data, "core_traits", "personality."),
            positive_traits=_text_list(personality_data, "positive_traits", "personality."),
            flaws=_text_list(personality_data, "flaws", "personality."),
            values=_text_list(personality_data, "values", "personality."),
            dislikes=_text_list(personality_data, "dislikes", "personality."),
            fears=_text_list(personality_data, "fears", "personality."),
            desires=_text_list(personality_data, "desires", "personality."),
            insecurities=_text_list(personality_data, "insecurities", "personality."),
            pride=_text_list(personality_data, "pride", "personality."),
            contradictions=_text_list(personality_data, "contradictions", "personality."),
            self_image=_text(personality_data, "self_image", "personality."),
            view_of_others=_text(personality_data, "view_of_others", "personality."),
            changeability=_choice(
                personality_data,
                "changeability",
                ("stable", "influenced", "adaptive"),
                "personality.",
            ),
            social_temperature=_choice(
                personality_data,
                "social_temperature",
                ("slow", "moderate", "outgoing"),
                "personality.",
            ),
            legacy_summary=_text(personality_data, "legacy_summary", "personality."),
        )
        behavior_data = _object(data, "behavior")
        behavior = Behavior(
            **{
                field: _text(behavior_data, field, "behavior.")
                for field in Behavior.__dataclass_fields__
            }
        )
        speech_data = _object(data, "speech")
        speech = Speech(
            first_person=_text(speech_data, "first_person", "speech."),
            second_person=_text(speech_data, "second_person", "speech."),
            vocabulary=_text(speech_data, "vocabulary", "speech."),
            avoided_words=_text_list(speech_data, "avoided_words", "speech."),
            sentence_length=_choice(
                speech_data, "sentence_length", ("adaptive", "short", "medium", "long"), "speech."
            ),
            punctuation=_text(speech_data, "punctuation", "speech."),
            question_frequency=_choice(
                speech_data, "question_frequency", ("necessary", "never", "often"), "speech."
            ),
            emoji_frequency=_choice(
                speech_data, "emoji_frequency", ("none", "occasional", "frequent"), "speech."
            ),
            humor_style=_text(speech_data, "humor_style", "speech."),
            affection_style=_text(speech_data, "affection_style", "speech."),
            disagreement_style=_text(speech_data, "disagreement_style", "speech."),
            apology_style=_text(speech_data, "apology_style", "speech."),
            refusal_style=_text(speech_data, "refusal_style", "speech."),
            greeting_style=_text(speech_data, "greeting_style", "speech."),
            goodbye_style=_text(speech_data, "goodbye_style", "speech."),
            correction_style=_text(speech_data, "correction_style", "speech."),
            topic_transition=_text(speech_data, "topic_transition", "speech."),
            silence_tolerance=_text(speech_data, "silence_tolerance", "speech."),
            habits=_text(speech_data, "habits", "speech."),
            tone=_choice(
                speech_data,
                "tone",
                ("follow_character", "gentle", "playful", "reserved"),
                "speech.",
            ),
            extra=_text(speech_data, "extra", "speech."),
        )
        response_data = _object(data, "response")
        response = ResponsePolicy(
            length=_choice(response_data, "length", ("adaptive", "brief", "expanded"), "response."),
            answer_first=_boolean(response_data, "answer_first", True, "response."),
            ask_followup=_choice(
                response_data, "ask_followup", ("necessary", "never", "often"), "response."
            ),
            offer_advice=_choice(
                response_data,
                "offer_advice",
                ("when_requested", "relevant", "default"),
                "response.",
            ),
            repeat_user=_boolean(response_data, "repeat_user", False, "response."),
            handle_unknown=_text(response_data, "handle_unknown", "response.")
            or "自然承认不知道，不把猜测说成事实。",
            avoid_cliches=_boolean(response_data, "avoid_cliches", True, "response."),
            avoid_psychological_analysis=_boolean(
                response_data, "avoid_psychological_analysis", True, "response."
            ),
            avoid_over_affection=_boolean(response_data, "avoid_over_affection", True, "response."),
            reduce_cliches=_boolean(response_data, "reduce_cliches", True, "response."),
        )
        roleplay_data = _object(data, "roleplay")
        roleplay = Roleplay(
            action_style=_choice(
                roleplay_data, "action_style", ("none", "occasional", "scene"), "roleplay."
            ),
            action_format=_choice(
                roleplay_data,
                "action_format",
                ("short_narration", "parentheses", "natural"),
                "roleplay.",
            ),
            environment_detail=_choice(
                roleplay_data, "environment_detail", ("light", "none", "rich"), "roleplay."
            ),
            inner_monologue=_boolean(roleplay_data, "inner_monologue", False, "roleplay."),
            sensory_detail=_boolean(roleplay_data, "sensory_detail", False, "roleplay."),
        )
        boundary_data = _object(data, "boundaries")
        boundaries = Boundaries(
            uncomfortable_topics=_text_list(boundary_data, "uncomfortable_topics", "boundaries."),
            forbidden_actions=_text_list(boundary_data, "forbidden_actions", "boundaries."),
            refusal_level=_choice(
                boundary_data, "refusal_level", ("clear", "gentle", "firm"), "boundaries."
            ),
            privacy_rules=_text(boundary_data, "privacy_rules", "boundaries."),
            reality_claims=_text(boundary_data, "reality_claims", "boundaries.")
            or "不要把未知的现实行为说成已经完成。",
            memory_claims=_text(boundary_data, "memory_claims", "boundaries.")
            or "不要把示例、推测或缺失上下文当作真实记忆。",
            tool_claims=_text(boundary_data, "tool_claims", "boundaries.")
            or "不要把计划或建议说成工具已经执行。",
            role_integrity=_text(boundary_data, "role_integrity", "boundaries.")
            or "不要为了迎合用户随意改变已确认的核心身份。",
            roleplay=_text(boundary_data, "roleplay", "boundaries."),
        )
        relation_data = _object(data, "relationship")
        relationship = Relationship(
            target_session=_text(relation_data, "target_session", "relationship."),
            target_bot_id=_text(relation_data, "target_bot_id", "relationship."),
            role=_text(relation_data, "role", "relationship."),
            stage=_text(relation_data, "stage", "relationship."),
            duration=_text(relation_data, "duration", "relationship."),
            background=_text(relation_data, "background", "relationship."),
            addressing=_text(relation_data, "addressing", "relationship."),
            addressing_for_character=_text(
                relation_data, "addressing_for_character", "relationship."
            ),
            shared_history=_text_list(relation_data, "shared_history", "relationship."),
            shared_interests=_text_list(relation_data, "shared_interests", "relationship."),
            trust_level=_text(relation_data, "trust_level", "relationship."),
            intimacy_boundary=_text(relation_data, "intimacy_boundary", "relationship."),
            sensitive_topics=_text_list(relation_data, "sensitive_topics", "relationship."),
            conflict_style=_text(relation_data, "conflict_style", "relationship."),
            repair_style=_text(relation_data, "repair_style", "relationship."),
        )
        examples = _text(data, "examples")
        character_data = _object(data, "character")
        character = Character(
            name=_text(character_data, "name", "character."),
            identity=_text(character_data, "identity", "character."),
            personality=_text(character_data, "personality", "character."),
            boundaries=_text(character_data, "boundaries", "character."),
        )

        if authority.mode == "character_owner" and source == "astrbot":
            raise ConfigError("persona_authority.mode", "requires_plugin_persona")

        if enabled and source == "plugin":
            if "character" in original:
                for field in ("name", "identity", "personality"):
                    if not _text(legacy_character, field, "character."):
                        raise ConfigError("character." + field, "required")
            else:
                for field, value in (
                    ("profile.name", profile.name),
                    ("background.identity", background.identity),
                ):
                    if not value:
                        raise ConfigError(field, "required")
                if not (personality.legacy_summary or personality.core_traits):
                    raise ConfigError("personality.core_traits", "required")
        if relationship.has_content and (
            not relationship.target_session or relationship.target_session not in sessions
        ):
            raise ConfigError("relationship.target_session", "target_not_allowed")
        if relationship.target_session and relationship.target_session not in sessions:
            raise ConfigError("relationship.target_session", "target_not_allowed")
        if (relationship.has_content or relationship.target_bot_id) and (
            not relationship.target_bot_id or relationship.target_bot_id not in bot_ids
        ):
            raise ConfigError("relationship.target_bot_id", "target_bot_not_allowed")
        text_count = sum(
            len(value)
            for key in (
                "character",
                "profile",
                "background",
                "personality",
                "behavior",
                "speech",
                "response",
                "roleplay",
                "boundaries",
                "relationship",
                "expression",
                "examples",
            )
            for value in _string_values(original.get(key, {}))
        )
        if text_count > TEXT_BUDGET:
            raise ConfigError("text_budget", "exceeded_12000_characters")
        expression = Expression(
            speech.habits,
            speech.tone,
            response.length,
            roleplay.action_style,
            speech.emoji_frequency,
            response.reduce_cliches,
            speech.extra,
        )
        return cls(
            enabled=enabled,
            persona_source=source,
            allowed_sessions=sessions,
            allowed_bot_ids=bot_ids,
            persona_authority=authority,
            character=character,
            relationship=relationship,
            expression=expression,
            examples=examples,
            profile=profile,
            background=background,
            personality=personality,
            behavior=behavior,
            speech=speech,
            response=response,
            roleplay=roleplay,
            boundaries=boundaries,
        )


def _string_values(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _string_values(item)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            yield from _string_values(item)
    elif hasattr(value, "__dataclass_fields__"):
        yield from _string_values(asdict(value))
