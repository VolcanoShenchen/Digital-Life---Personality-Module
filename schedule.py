"""Validated daily schedules; model planning is isolated in schedule_planner.

Reading a schedule never calls a model. Only explicitly selected templates can
be generated synchronously. Model failure never creates substitute activities.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .settings import ConfigError

if TYPE_CHECKING:
    from .personality import Scope
    from .settings import Settings

SCHEDULE_START = "<dlp_schedule_context_v1>\n"
SCHEDULE_END = "\n</dlp_schedule_context_v1>"
DEFAULT_RULE = (
    "结合角色身份、性格、兴趣和近期背景生成自然且有变化的今日生活安排，遵守作息与固定时段。"
)
PLANNER_VERSION = 1
GENERATOR_VERSION = 3


@dataclass(frozen=True)
class ScheduleConfig:
    enabled: bool = False
    auto_generate: bool = True
    timezone: str = "Asia/Shanghai"
    generation_rule: str = DEFAULT_RULE
    template_lines: tuple[str, ...] = ()
    allow_manual_override: bool = True
    max_segments: int = 12
    generation_mode: str = "llm"
    wake_time: str = "07:30"
    sleep_time: str = "23:00"
    work_start: str = "09:00"
    work_end: str = "17:30"
    workdays: tuple[str, ...] = ("1", "2", "3", "4", "5")
    work_location: str = ""
    home_location: str = ""
    provider_id: str = ""
    model_timeout: int = 90
    retry_cooldown: int = 900


@dataclass(frozen=True)
class ScheduleSlot:
    start: str
    end: str
    activity: str
    location: str = ""
    notes: str = ""
    source: str = "template"


class ScheduleError(ValueError):
    """Fixed error code; never retain raw model or provider error text."""


ScheduleParseError = ScheduleError


def minutes(value: Any, *, end: bool = False) -> int:
    if end and value == "24:00":
        return 1440
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ScheduleError("expected_HH_MM")
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def clock(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def parse_template_line(line: str) -> ScheduleSlot:
    if not isinstance(line, str):
        raise ScheduleError("template_line_format")
    parts = [part.strip() for part in line.split("|", 3)]
    if len(parts) < 2 or not parts[1]:
        raise ScheduleError("template_line_format")
    window = parts[0].split("-")
    if len(window) != 2:
        raise ScheduleError("template_time_range")
    start, end = (value.strip() for value in window)
    if minutes(start) >= minutes(end, end=True):
        raise ScheduleError("template_time_order")
    return ScheduleSlot(
        start, end, parts[1], parts[2] if len(parts) > 2 else "", parts[3] if len(parts) > 3 else ""
    )


def validate_slots(slots: Any, maximum: int = 32, source: str | None = None) -> list[dict]:
    if not isinstance(slots, list) or not 1 <= len(slots) <= maximum:
        raise ScheduleError("invalid_slot_count")
    clean = []
    for item in slots:
        if not isinstance(item, Mapping):
            raise ScheduleError("invalid_slot_object")
        record = {}
        for key in ("start", "end", "activity", "location", "notes"):
            value = item.get(key, "")
            if not isinstance(value, str):
                raise ScheduleError("invalid_slot_text")
            record[key] = value.strip()
        if (
            not record["activity"]
            or len(record["activity"]) > 300
            or len(record["location"]) > 200
            or len(record["notes"]) > 1000
        ):
            raise ScheduleError("invalid_slot_text_length")
        if minutes(record["start"]) >= minutes(record["end"], end=True):
            raise ScheduleError("slot_time_order")
        record["source"] = source or item.get("source", "manual")
        if record["source"] not in ("manual", "template", "llm", "persona"):
            raise ScheduleError("invalid_slot_source")
        clean.append(record)
    clean.sort(key=lambda item: item["start"])
    for previous, current in zip(clean, clean[1:], strict=False):
        if minutes(previous["end"], end=True) > minutes(current["start"]):
            raise ScheduleError("overlapping_slots")
    return clean


def parse_schedule_config(data: Mapping[str, Any]) -> ScheduleConfig:
    raw = data.get("schedule", {})
    if not isinstance(raw, Mapping):
        raise ConfigError("schedule", "expected_object")
    values = {}
    defaults = ScheduleConfig()
    for key in ("enabled", "auto_generate", "allow_manual_override"):
        value = raw.get(key, getattr(defaults, key))
        if not isinstance(value, bool):
            raise ConfigError("schedule." + key, "expected_boolean")
        values[key] = value
    for key in (
        "timezone",
        "generation_rule",
        "generation_mode",
        "wake_time",
        "sleep_time",
        "work_start",
        "work_end",
        "work_location",
        "home_location",
        "provider_id",
    ):
        value = raw.get(key, getattr(defaults, key))
        if not isinstance(value, str):
            raise ConfigError("schedule." + key, "expected_text")
        values[key] = value.strip()
    if values["generation_mode"] == "persona":
        values["generation_mode"] = "llm"
        if values["generation_rule"] in {
            "按模板生成；不凭空添加未配置的现实事件。",
            "根据角色职业、常住地和作息生成；模板为可选固定安排。",
        }:
            values["generation_rule"] = DEFAULT_RULE
    if values["generation_mode"] not in ("llm", "template"):
        raise ConfigError("schedule.generation_mode", "invalid_choice")
    try:
        ZoneInfo(values["timezone"])
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ConfigError("schedule.timezone", "unknown_timezone") from error
    for key, lower, upper in (
        ("max_segments", 1, 32),
        ("model_timeout", 10, 180),
        ("retry_cooldown", 60, 86400),
    ):
        value = raw.get(key, getattr(defaults, key))
        if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
            raise ConfigError("schedule." + key, "invalid_range")
        values[key] = value
    maximum = values["max_segments"]
    for key in ("template_lines", "workdays"):
        value = raw.get(key, list(getattr(defaults, key)))
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ConfigError("schedule." + key, "expected_text_list")
        values[key] = tuple(item.strip() for item in value if item.strip())
    if any(day not in {str(n) for n in range(1, 8)} for day in values["workdays"]):
        raise ConfigError("schedule.workdays", "expected_ISO_weekdays_1_to_7")
    if sum(len(line) for line in values["template_lines"]) + len(values["generation_rule"]) > 6000:
        raise ConfigError("schedule", "rules_text_budget_exceeded")
    if len(values["provider_id"]) > 300:
        raise ConfigError("schedule.provider_id", "text_too_long")
    try:
        wake, sleep, start, end = (
            minutes(values[key]) for key in ("wake_time", "sleep_time", "work_start", "work_end")
        )
        if not wake < sleep or not start < end:
            raise ScheduleError("invalid_routine_order")
        if values["generation_mode"] == "llm" and not wake < start < end < sleep:
            raise ScheduleError("work_must_fit_awake_window")
        if values["template_lines"]:
            validate_slots(
                [asdict(parse_template_line(line)) for line in values["template_lines"]], maximum
            )
        elif values["enabled"] and values["generation_mode"] == "template":
            raise ScheduleError("template_required")
        if values["enabled"] and values["generation_mode"] == "llm" and maximum < 5:
            raise ScheduleError("llm_mode_needs_at_least_5_slots")
    except ScheduleError as error:
        raise ConfigError("schedule", str(error)) from error
    return ScheduleConfig(**values)


def local_now(config: ScheduleConfig, now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ScheduleError("timezone_required")
    return now.astimezone(ZoneInfo(config.timezone))


def owner_identity(settings: Settings) -> dict:
    """Explicit stable-persona whitelist; excludes relationship/history/secrets."""
    profile_keys = (
        "name",
        "nickname",
        "gender_identity",
        "pronouns",
        "age",
        "age_mode",
        "birth_date",
        "species",
        "nationality",
        "native_language",
        "timezone",
        "location",
        "occupation",
        "education",
        "social_status",
    )
    background_keys = (
        "identity",
        "family",
        "childhood",
        "education_history",
        "work_history",
        "important_events",
        "life_context",
        "world_setting",
        "known_facts",
        "unknown_facts",
    )
    personality_keys = (
        "core_traits",
        "positive_traits",
        "flaws",
        "values",
        "dislikes",
        "fears",
        "desires",
        "insecurities",
        "pride",
        "contradictions",
        "self_image",
        "view_of_others",
        "changeability",
        "social_temperature",
        "legacy_summary",
    )
    behavior_keys = (
        "when_happy",
        "when_sad",
        "when_angry",
        "when_tired",
        "when_embarrassed",
        "when_anxious",
        "when_bored",
        "when_confused",
        "when_praised",
        "when_criticized",
        "when_disagrees",
        "when_apologizing",
        "when_refusing",
        "when_ignored",
        "when_topic_changes",
        "when_memory_missing",
    )
    return {
        "name": settings.profile.name or settings.character.name,
        "identity": settings.background.identity or settings.character.identity,
        "occupation": settings.profile.occupation,
        "home": settings.profile.location,
        "source": settings.persona_source,
        "profile": {key: getattr(settings.profile, key) for key in profile_keys},
        "background": {key: getattr(settings.background, key) for key in background_keys},
        "personality": {key: getattr(settings.personality, key) for key in personality_keys},
        "behavior": {key: getattr(settings.behavior, key) for key in behavior_keys},
    }


def signature(config: ScheduleConfig, owner: dict | None = None) -> str:
    rules = asdict(config)
    for control in ("enabled", "auto_generate", "allow_manual_override"):
        rules.pop(control)
    payload = {"owner": owner or {}, "rules": rules, "planner_version": PLANNER_VERSION}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def owner_signature(owner: dict | None = None) -> str:
    return hashlib.sha256(
        json.dumps(owner or {}, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def matches_owner(plan: dict, owner: dict | None) -> bool:
    if plan.get("owner_signature") == owner_signature(owner):
        return True
    # 0.4.x signed only these stable identity fields. Preserve an explicitly
    # edited plan for the same character while rejecting old automatic rules.
    legacy = {
        key: (owner or {}).get(key, "")
        for key in ("name", "identity", "occupation", "home", "source")
    }
    return bool(
        plan.get("manual_override") and plan.get("owner_signature") == owner_signature(legacy)
    )


def generate_slots(config: ScheduleConfig, today: date, owner: dict | None = None) -> list[dict]:
    """Only an explicit user template may produce activities without a model."""
    if config.generation_mode != "template":
        raise ScheduleError("model_generation_required")
    return validate_slots(
        [asdict(parse_template_line(line)) for line in config.template_lines],
        config.max_segments,
        "template",
    )


def validate_model_response(
    response: str, config: ScheduleConfig, expected_date: date
) -> list[dict]:
    if not isinstance(response, str) or len(response) > 65536:
        raise ScheduleError("invalid_model_response")
    text = response.strip()
    if text.startswith("```"):
        match = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
        if not match:
            raise ScheduleError("invalid_model_json")
        text = match.group(1).strip()
    try:
        document = json.loads(text)
    except (ValueError, TypeError) as error:
        raise ScheduleError("invalid_model_json") from error
    if not isinstance(document, dict) or "tool_calls" in document:
        raise ScheduleError("invalid_model_document")
    if set(document) != {"date", "timezone", "slots"}:
        raise ScheduleError("invalid_model_document")
    if document["date"] != expected_date.isoformat() or document["timezone"] != config.timezone:
        raise ScheduleError("model_date_or_timezone_mismatch")
    for item in document["slots"] if isinstance(document["slots"], list) else []:
        if not isinstance(item, dict) or set(item) != {
            "start",
            "end",
            "activity",
            "location",
            "notes",
        }:
            raise ScheduleError("invalid_model_slot_schema")
    slots = validate_slots(document["slots"], config.max_segments, "llm")
    if slots[0]["start"] != "00:00" or slots[-1]["end"] != "24:00":
        raise ScheduleError("model_incomplete_day")
    if any(left["end"] != right["start"] for left, right in zip(slots, slots[1:], strict=False)):
        raise ScheduleError("model_incomplete_day")
    for line in config.template_lines:
        anchor = asdict(parse_template_line(line))
        if not any(
            all(slot[key] == anchor[key] for key in ("start", "end", "activity", "location"))
            for slot in slots
        ):
            raise ScheduleError("model_fixed_anchor_changed")
    return slots


class ScheduleStore:
    """Atomic lazy storage; reads do not call or schedule model generation."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / "today_schedule.json"
        self.status_path = self.root / "generation_status.json"
        self._lock = threading.RLock()

    def load(self) -> dict | None:
        if not self.path.is_file():
            return None
        try:
            data = json.loads(self.path.read_text("utf-8"))
            if not isinstance(data, dict) or data.get("schema_version") != 1:
                raise ScheduleError("stored_schema_invalid")
            date.fromisoformat(data["date"])
            ZoneInfo(data["timezone"])
            data["slots"] = validate_slots(data["slots"])
            if not isinstance(data.get("revision"), str) or not data.get("revision"):
                raise ScheduleError("stored_revision_invalid")
            return data
        except (ValueError, TypeError, KeyError, ZoneInfoNotFoundError) as error:
            raise ScheduleError("stored_schedule_invalid") from error

    def _write_json(self, path: Path, value: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.root / (".schedule-" + uuid.uuid4().hex + ".tmp")
        try:
            temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _save(self, value: dict) -> None:
        self._write_json(self.path, value)

    def load_generation_status(self) -> dict | None:
        with self._lock:
            if not self.status_path.is_file():
                return None
            try:
                value = json.loads(self.status_path.read_text("utf-8"))
                if not isinstance(value, dict):
                    raise ValueError
                return value
            except (ValueError, TypeError) as error:
                raise ScheduleError("stored_generation_status_invalid") from error

    def save_generation_status(self, value: dict) -> None:
        with self._lock:
            self._write_json(self.status_path, value)

    def _record(
        self,
        config: ScheduleConfig,
        today: date,
        slots: list,
        owner: dict | None,
        manual: bool,
        provider_id: str = "",
    ) -> dict:
        return {
            "schema_version": 1,
            "revision": uuid.uuid4().hex,
            "date": today.isoformat(),
            "timezone": config.timezone,
            "generated_at": datetime.now(UTC).isoformat(),
            "generation_mode": config.generation_mode,
            "generator_version": GENERATOR_VERSION,
            "planner_version": PLANNER_VERSION,
            "provider_id": provider_id,
            "source": "manual" if manual else config.generation_mode,
            "generation_rule": config.generation_rule,
            "owner_signature": owner_signature(owner),
            "rules_signature": signature(config, owner),
            "manual_override": manual,
            "slots": slots,
        }

    @staticmethod
    def _check_revision(existing: dict | None, revision: str | None) -> None:
        if revision is not None and (existing or {}).get("revision") != revision:
            raise ScheduleError("revision_conflict")

    def generate(
        self,
        config: ScheduleConfig,
        today: date | None = None,
        *,
        owner: dict | None = None,
        revision: str | None = None,
        confirm: bool = False,
    ) -> dict:
        if not config.enabled:
            raise ScheduleError("module_disabled")
        if config.generation_mode != "template":
            raise ScheduleError("model_generation_required")
        today = today or local_now(config).date()
        with self._lock:
            existing = self.load()
            self._check_revision(existing, revision)
            if (
                existing
                and existing.get("date") == today.isoformat()
                and existing.get("timezone") == config.timezone
                and matches_owner(existing, owner)
                and existing.get("manual_override")
                and not confirm
            ):
                raise ScheduleError("manual_schedule_requires_confirmation")
            slots = generate_slots(config, today, owner)
            result = self._record(config, today, slots, owner, False)
            self._save(result)
            return result

    def get_or_generate(
        self, config: ScheduleConfig, now: datetime | None = None, *, owner: dict | None = None
    ) -> dict | None:
        if not config.enabled:
            return None
        today = local_now(config, now).date()
        with self._lock:
            current = self.load()
            same_owner = (
                current
                and matches_owner(current, owner)
                and current.get("timezone") == config.timezone
            )
            if same_owner and current.get("date") == today.isoformat():
                if current.get("manual_override"):
                    return current
                matching_source = current.get("generation_mode") == config.generation_mode and all(
                    slot.get("source") == config.generation_mode for slot in current["slots"]
                )
                if matching_source and current.get("rules_signature") == signature(config, owner):
                    return current
            if config.generation_mode != "template" or not config.auto_generate:
                return None
            return self.generate(config, today, owner=owner)

    def current_slot(
        self, config: ScheduleConfig, now: datetime | None = None, *, owner: dict | None = None
    ) -> dict | None:
        plan = self.get_or_generate(config, now, owner=owner)
        if not plan:
            return None
        current = local_now(config, now)
        instant = current.hour * 60 + current.minute
        for slot in plan["slots"]:
            if minutes(slot["start"]) <= instant < minutes(slot["end"], end=True):
                return {**slot, "date": plan["date"], "timezone": config.timezone}
        return None

    def commit_model(
        self,
        config: ScheduleConfig,
        slots: list,
        *,
        owner: dict,
        expected_revision: str | None,
        expected_date: date,
        provider_id: str,
        now: datetime | None = None,
    ) -> dict:
        if not config.enabled or config.generation_mode != "llm":
            raise ScheduleError("module_disabled")
        if local_now(config, now).date() != expected_date:
            raise ScheduleError("generation_date_changed")
        clean = validate_slots(slots, config.max_segments, "llm")
        with self._lock:
            current = self.load()
            if (current or {}).get("revision") != expected_revision:
                raise ScheduleError("revision_conflict")
            result = self._record(config, expected_date, clean, owner, False, provider_id)
            self._save(result)
            return result

    def update_slots(
        self,
        config: ScheduleConfig,
        slots: list,
        today: date | None = None,
        *,
        owner: dict | None = None,
        revision: str | None = None,
    ) -> dict:
        if not config.enabled:
            raise ScheduleError("module_disabled")
        if not config.allow_manual_override:
            raise PermissionError("manual_schedule_override_disabled")
        clean = validate_slots(slots, config.max_segments, "manual")
        today = today or local_now(config).date()
        with self._lock:
            existing = self.load()
            self._check_revision(existing, revision)
            if (
                revision is not None
                and existing
                and (
                    existing["date"] != today.isoformat()
                    or existing["timezone"] != config.timezone
                    or not matches_owner(existing, owner)
                )
            ):
                raise ScheduleError("schedule_scope_or_date_changed")
            result = self._record(config, today, clean, owner, True)
            self._save(result)
            return result


def build_schedule_context(
    settings: Settings | None, scope: Scope, store: ScheduleStore, now: datetime | None = None
) -> str:
    from .personality import scope_reason

    if (
        settings is None
        or scope_reason(settings, scope) != "applied"
        or not settings.schedule.enabled
    ):
        return ""
    slot = store.current_slot(settings.schedule, now, owner=owner_identity(settings))
    if not slot:
        return ""

    def safe(value: str) -> str:
        return value.replace("<dlp_schedule_context_v1>", "［日程］").replace(
            "</dlp_schedule_context_v1>", "［日程结束］"
        )

    state = settings.dynamic_state
    manual_active = (
        state.target_session == scope.origin
        and state.target_bot_id == scope.bot_id
        and state.is_active(now)
    )
    lines = [
        SCHEDULE_START.rstrip("\n"),
        "以下为角色生活模拟的当前安排，供本轮在角色语境中参考。它不是现实中已执行或已完成的证据。",
        f"日期：{slot['date']}；时区：{slot['timezone']}；时段：{slot['start']} - {slot['end']}",
    ]
    if not (manual_active and state.activity):
        lines.append("当前计划活动：" + safe(slot["activity"]))
    if slot["location"] and not (manual_active and state.location):
        lines.append("当前计划位置：" + safe(slot["location"]))
    if manual_active:
        lines.append(
            "当前有效人工状态优先；人工已指定的活动或位置不使用日程覆盖，其有效期结束后再恢复日程。"
        )
    if slot["notes"]:
        lines.append("备注：" + safe(slot["notes"]))
    lines.append(
        "话题相关时自然回答活动和位置，不播报整份日程，不把昨天日程当今天事实，不虚构工具执行或现实行动。"
    )
    return "\n".join(lines) + SCHEDULE_END
