"""Local daily plans: validated rules, atomic persistence and timed lookup.

Generated entries describe the fictional character's planned scene. They are
never evidence of real-world actions or tool completion.
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
DEFAULT_RULE = "根据角色职业、常住地和作息生成；模板为可选固定安排。"


@dataclass(frozen=True)
class ScheduleConfig:
    enabled: bool = False
    auto_generate: bool = True
    timezone: str = "Asia/Shanghai"
    generation_rule: str = DEFAULT_RULE
    template_lines: tuple[str, ...] = ()
    allow_manual_override: bool = True
    max_segments: int = 12
    generation_mode: str = "persona"
    wake_time: str = "07:30"
    sleep_time: str = "23:00"
    work_start: str = "09:00"
    work_end: str = "17:30"
    workdays: tuple[str, ...] = ("1", "2", "3", "4", "5")
    work_location: str = ""
    home_location: str = ""


@dataclass(frozen=True)
class ScheduleSlot:
    start: str
    end: str
    activity: str
    location: str = ""
    notes: str = ""
    source: str = "template"


class ScheduleError(ValueError):
    """Fixed public error code, never containing raw configuration."""


# Kept for first implementation callers.
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
        if record["source"] not in ("manual", "template", "persona"):
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
    ):
        value = raw.get(key, getattr(defaults, key))
        if not isinstance(value, str):
            raise ConfigError("schedule." + key, "expected_text")
        values[key] = value.strip()
    if values["generation_mode"] not in ("persona", "template"):
        raise ConfigError("schedule.generation_mode", "invalid_choice")
    try:
        ZoneInfo(values["timezone"])
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ConfigError("schedule.timezone", "unknown_timezone") from error
    maximum = raw.get("max_segments", 12)
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 32:
        raise ConfigError("schedule.max_segments", "invalid_range")
    values["max_segments"] = maximum
    for key in ("template_lines", "workdays"):
        value = raw.get(key, list(getattr(defaults, key)))
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ConfigError("schedule." + key, "expected_text_list")
        values[key] = tuple(item.strip() for item in value if item.strip())
    if any(day not in {str(n) for n in range(1, 8)} for day in values["workdays"]):
        raise ConfigError("schedule.workdays", "expected_ISO_weekdays_1_to_7")
    if sum(len(line) for line in values["template_lines"]) + len(values["generation_rule"]) > 6000:
        raise ConfigError("schedule", "rules_text_budget_exceeded")
    try:
        wake, sleep, start, end = (
            minutes(values[key]) for key in ("wake_time", "sleep_time", "work_start", "work_end")
        )
        if not wake < sleep or not start < end:
            raise ScheduleError("invalid_routine_order")
        if values["generation_mode"] == "persona" and not wake < start < end < sleep:
            raise ScheduleError("work_must_fit_awake_window")
        if values["template_lines"]:
            validate_slots(
                [asdict(parse_template_line(line)) for line in values["template_lines"]], maximum
            )
        elif values["enabled"] and values["generation_mode"] == "template":
            raise ScheduleError("template_required")
        if values["enabled"] and values["generation_mode"] == "persona" and maximum < 5:
            raise ScheduleError("persona_mode_needs_at_least_5_slots")
    except ScheduleError as error:
        raise ConfigError("schedule", str(error)) from error
    return ScheduleConfig(**values)


def local_now(config: ScheduleConfig, now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ScheduleError("timezone_required")
    return now.astimezone(ZoneInfo(config.timezone))


def owner_identity(settings: Settings) -> dict:
    # Relationship/user history never enters the daily generation seed.
    return {
        "name": settings.profile.name or settings.character.name,
        "identity": settings.background.identity or settings.character.identity,
        "occupation": settings.profile.occupation,
        "home": settings.profile.location,
        "source": settings.persona_source,
    }


def signature(config: ScheduleConfig, owner: dict | None = None) -> str:
    rules = asdict(config)
    for control in ("enabled", "auto_generate", "allow_manual_override"):
        rules.pop(control)
    payload = {"owner": owner or {}, "rules": rules}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def owner_signature(owner: dict | None = None) -> str:
    return hashlib.sha256(
        json.dumps(owner or {}, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def generate_slots(config: ScheduleConfig, today: date, owner: dict | None = None) -> list[dict]:
    anchors = [asdict(parse_template_line(line)) for line in config.template_lines]
    if config.generation_mode == "template":
        return validate_slots(anchors, config.max_segments, "template")
    owner = owner or {}
    home = config.home_location or owner.get("home") or "家中"
    workplace = config.work_location or (
        f"{owner['occupation']}的工作场所" if owner.get("occupation") else home
    )
    wake, sleep, start, end = (
        minutes(getattr(config, key))
        for key in ("wake_time", "sleep_time", "work_start", "work_end")
    )
    working = str(today.isoweekday()) in config.workdays and bool(
        owner.get("occupation") or config.work_location
    )
    middle = ("处理工作事务", workplace) if working else ("安排个人事务与休闲", home)
    base = [
        (0, wake, "睡眠与休息", home),
        (wake, start, "起床、早餐和准备", home),
        (start, end, *middle),
        (end, sleep, "晚餐与个人时间", home),
        (sleep, 1440, "睡眠与休息", home),
    ]
    # Optional fixed anchors cut the generated routine, never overlap it.
    boundaries = {0, 1440, wake, sleep, start, end}
    for slot in anchors:
        boundaries.update((minutes(slot["start"]), minutes(slot["end"], end=True)))
    result = []
    points = sorted(boundaries)
    for left, right in zip(points, points[1:], strict=False):
        chosen = next(
            (s for s in anchors if minutes(s["start"]) <= left < minutes(s["end"], end=True)), None
        )
        if chosen:
            item = {**chosen, "start": clock(left), "end": clock(right), "source": "template"}
        else:
            _, _, activity, location = next(row for row in base if row[0] <= left < row[1])
            item = asdict(
                ScheduleSlot(
                    clock(left),
                    clock(right),
                    activity,
                    location,
                    "角色生活安排，非现实执行记录",
                    "persona",
                )
            )
        if result and all(
            result[-1][key] == item[key] for key in ("activity", "location", "notes", "source")
        ):
            result[-1]["end"] = item["end"]
        else:
            result.append(item)
    return validate_slots(result, config.max_segments)


class ScheduleStore:
    """Lazy, atomic workspace data storage; no I/O when the module is disabled."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / "today_schedule.json"
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

    def _save(self, value: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.root / (".schedule-" + uuid.uuid4().hex + ".tmp")
        try:
            temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")
            temporary.replace(self.path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _record(
        self, config: ScheduleConfig, today: date, slots: list, owner: dict | None, manual: bool
    ) -> dict:
        return {
            "schema_version": 1,
            "revision": uuid.uuid4().hex,
            "date": today.isoformat(),
            "timezone": config.timezone,
            "generated_at": datetime.now(UTC).isoformat(),
            "generation_mode": config.generation_mode,
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
        today = today or local_now(config).date()
        with self._lock:
            existing = self.load()
            self._check_revision(existing, revision)
            if (
                existing
                and existing.get("date") == today.isoformat()
                and existing.get("timezone") == config.timezone
                and existing.get("owner_signature") == owner_signature(owner)
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
                and current.get("owner_signature") == owner_signature(owner)
                and current.get("timezone") == config.timezone
            )
            if same_owner and current.get("date") == today.isoformat():
                # Manual edits survive rule changes and restarts for this character/day.
                if current.get("manual_override") or current.get("rules_signature") == signature(
                    config, owner
                ):
                    return current
            if not config.auto_generate:
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
                    or existing["owner_signature"] != owner_signature(owner)
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
    if settings.schedule.generation_rule:
        lines.append(
            "运营者日程补充说明（不改变固定时间规则）：" + safe(settings.schedule.generation_rule)
        )
    lines.append(
        "话题相关时自然回答活动和位置，不播报整份日程，不把昨天日程当今天事实，不虚构工具执行或现实行动。"
    )
    return "\n".join(lines) + SCHEDULE_END
