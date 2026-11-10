"""Pure, immutable configuration parsing for the personality plugin."""

from collections.abc import Mapping
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Character:
    name: str = ""
    identity: str = ""
    personality: str = ""
    boundaries: str = ""


@dataclass(frozen=True)
class Relationship:
    target_session: str = ""
    target_bot_id: str = ""
    background: str = ""
    addressing: str = ""

    @property
    def has_content(self) -> bool:
        return bool(self.background or self.addressing)


@dataclass(frozen=True)
class Expression:
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
    character: Character
    relationship: Relationship
    expression: Expression
    examples: str

    @classmethod
    def parse(cls, data: Mapping[str, Any]) -> "Settings":
        if not isinstance(data, Mapping):
            raise ConfigError("config", "expected_object")
        enabled = _boolean(data, "enabled", False)
        source = _choice(data, "persona_source", ("plugin", "astrbot"))
        sessions = _id_list(data, "allowed_sessions")
        bot_ids = _id_list(data, "allowed_bot_ids")
        char_data = _object(data, "character")
        character = Character(
            **{
                name: _text(char_data, name, "character.")
                for name in ("name", "identity", "personality", "boundaries")
            }
        )
        relation_data = _object(data, "relationship")
        relationship = Relationship(
            **{
                name: _text(relation_data, name, "relationship.")
                for name in ("target_session", "target_bot_id", "background", "addressing")
            }
        )
        expr_data = _object(data, "expression")
        expression = Expression(
            habits=_text(expr_data, "habits", "expression."),
            tone=_choice(
                expr_data,
                "tone",
                ("follow_character", "gentle", "playful", "reserved"),
                "expression.",
            ),
            length=_choice(expr_data, "length", ("adaptive", "brief", "expanded"), "expression."),
            actions=_choice(expr_data, "actions", ("none", "occasional", "scene"), "expression."),
            emoji=_choice(expr_data, "emoji", ("occasional", "none", "frequent"), "expression."),
            reduce_cliches=_boolean(expr_data, "reduce_cliches", True, "expression."),
            extra=_text(expr_data, "extra", "expression."),
        )
        examples = _text(data, "examples")
        if enabled and source == "plugin":
            for field in ("name", "identity", "personality"):
                if not getattr(character, field):
                    raise ConfigError("character." + field, "required")
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
        user_texts = (
            character.name,
            character.identity,
            character.personality,
            character.boundaries,
            relationship.background,
            relationship.addressing,
            expression.habits,
            expression.extra,
            examples,
        )
        if sum(len(text) for text in user_texts) > TEXT_BUDGET:
            raise ConfigError("text_budget", "exceeded_12000_characters")
        return cls(
            enabled, source, sessions, bot_ids, character, relationship, expression, examples
        )
