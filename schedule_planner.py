"""Asynchronous daily model planning, independent of AstrBot APIs."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

from .schedule import (
    ScheduleError,
    ScheduleStore,
    local_now,
    owner_identity,
    owner_signature,
    parse_template_line,
    signature,
    validate_model_response,
)

if TYPE_CHECKING:
    from .settings import Settings

Generate = Callable[[str, str, str, int], Awaitable[tuple[str, str]]]
MAX_AUTO_ATTEMPTS = 3

SYSTEM_PROMPT = (
    "你是虚构角色的日程规划器。根据提供的稳定人格和约束创作今日具体生活安排，"
    "活动内容必须由你规划，不要输出占位文本，不要照搬相同工作/休闲标题填满全天。"
    "不执行任何工具或现实动作，不声称安排已经发生。不要使用聊天历史、用户关系或秘密。"
    "只返回一个JSON对象，不输出解释，不发起tool_calls。"
)


def planning_prompt(settings: Settings, today: date, previous: dict | None = None) -> str:
    config = settings.schedule
    persona = owner_identity(settings)
    anchors = [asdict(parse_template_line(line)) for line in config.template_lines]
    constraints = {
        "date": today.isoformat(),
        "timezone": config.timezone,
        "wake_time": config.wake_time,
        "sleep_time": config.sleep_time,
        "work_start": config.work_start,
        "work_end": config.work_end,
        "workdays": config.workdays,
        "is_workday": str(today.isoweekday()) in config.workdays,
        "home_location": config.home_location,
        "work_location": config.work_location,
        "fixed_slots": anchors,
        "max_segments": config.max_segments,
        "instructions": config.generation_rule,
    }
    reference = None
    if (
        previous
        and previous.get("owner_signature") == owner_signature(persona)
        and not previous.get("manual_override")
        and previous.get("generation_mode") == "llm"
        and all(slot.get("source") == "llm" for slot in previous.get("slots", []))
    ):
        reference = {"date": previous.get("date"), "slots": previous.get("slots", [])}
    payload = {
        "stable_character": persona,
        "constraints": constraints,
        "previous_automatic_plan_reference_only_not_history": reference,
        "output_schema": {
            "date": "YYYY-MM-DD，必须等于constraints.date",
            "timezone": "必须等于constraints.timezone",
            "slots": [
                {
                    "start": "HH:MM",
                    "end": "HH:MM或24:00",
                    "activity": "你生成的具体活动内容",
                    "location": "你生成的合理场景位置",
                    "notes": "必要补充，可空字符串",
                }
            ],
        },
    }
    return (
        "请为下面的角色生成今日动态日程。综合身份、性格、偏好、动机和近期背景，"
        "在保持连贯的同时变化具体活动，不只填通用标签。遵守清醒/休息时间和工作日约束，"
        "固定安排必须原样保留开始、结束、活动及地点。全日从00:00至24:00连续覆盖，"
        "不能重叠或留空档，不能超过max_segments。地点移动要合理安排过渡，不能瞬移。"
        "上一份自动安排只是避免机械重复的参考，不是已经执行的历史，不要据此声称真实经历。"
        "仅输出date、timezone、slots三个顶层键，每段只含start/end/activity/location/notes五个字符串键。\n"
        + json.dumps(payload, ensure_ascii=False)
    )


class SchedulePlanner:
    """Single-flight planner with persisted cooldown and optimistic commits.

    `generate(provider_id, prompt, system_prompt, timeout)` must resolve the host
    provider and return `(completion_text, actual_provider_id)`. Missing provider
    raises `ScheduleError('provider_missing')`; no provider internals are logged.
    Both automatic and manual failures obey retry_cooldown. Successful force
    requests also wait at least 60s before another paid generation attempt.
    """

    def __init__(
        self,
        store: ScheduleStore,
        generate: Generate,
        clock: Callable[[], datetime] | None = None,
        current_settings: Callable[[], Settings | None] | None = None,
    ):
        self.store = store
        self.generate = generate
        self.clock = clock or (lambda: datetime.now(UTC))
        self.current_settings = current_settings
        self.task: asyncio.Task | None = None
        self._active_key: tuple[str, str] | None = None
        self._state: dict | None = None
        self._latest_settings: Settings | None = None

    @staticmethod
    def _enabled(settings: Settings | None) -> bool:
        return bool(settings and settings.enabled and settings.schedule.enabled)

    def _key(self, settings: Settings) -> tuple[str, str]:
        return (
            local_now(settings.schedule, self.clock()).date().isoformat(),
            signature(settings.schedule, owner_identity(settings)),
        )

    def _read_state(self, settings: Settings) -> dict | None:
        record = self.store.load_generation_status()
        if not record:
            return None
        key = self._key(settings)
        if record.get("date") != key[0] or record.get("fingerprint") != key[1]:
            return None
        if (
            isinstance(record.get("attempt_count", 0), bool)
            or not isinstance(record.get("attempt_count", 0), int)
            or record.get("attempt_count", 0) < 0
        ):
            raise ScheduleError("stored_generation_status_invalid")
        try:
            if record.get("next_retry_at"):
                retry = datetime.fromisoformat(record["next_retry_at"])
                if retry.tzinfo is None:
                    raise ValueError
        except (ValueError, TypeError) as error:
            raise ScheduleError("stored_generation_status_invalid") from error
        return record

    def status(self, settings: Settings | None) -> dict:
        result = {
            "enabled": self._enabled(settings),
            "reason": "disabled",
            "last_error": "",
            "next_retry_at": "",
            "provider_id": "",
            "attempt_count": 0,
        }
        if not self._enabled(settings):
            return result
        result["provider_id"] = settings.schedule.provider_id
        if self.task and not self.task.done() and self._active_key == self._key(settings):
            return {**result, "reason": "generating"}
        try:
            current = self.store.get_or_generate(
                settings.schedule, self.clock(), owner=owner_identity(settings)
            )
            state = self._read_state(settings)
        except (ScheduleError, OSError):
            return {
                **result,
                "reason": "generation_failed",
                "last_error": "schedule_storage_unavailable",
            }
        if current:
            return {
                **result,
                "reason": "enabled",
                "provider_id": current.get("provider_id", ""),
                "last_error": (state or {}).get("last_error", ""),
                "next_retry_at": (state or {}).get("next_retry_at", ""),
                "attempt_count": (state or {}).get("attempt_count", 0),
            }
        if state:
            result.update(
                {key: state.get(key, "") for key in ("last_error", "next_retry_at", "provider_id")}
            )
            retry_at = (
                datetime.fromisoformat(state["next_retry_at"])
                if state.get("next_retry_at")
                else None
            )
            cooling = retry_at is not None and self.clock().astimezone(UTC) < retry_at
            result["attempt_count"] = state.get("attempt_count", 0)
            reason = (
                "daily_limit"
                if state.get("attempt_count", 0) >= MAX_AUTO_ATTEMPTS and state.get("last_error")
                else "provider_missing"
                if state.get("last_error") == "provider_missing"
                else "cooldown"
                if cooling
                else "generation_failed"
                if state.get("last_error")
                else "not_generated"
            )
            return {**result, "reason": reason}
        return {**result, "reason": "not_generated"}

    def start(
        self,
        settings: Settings,
        force: bool = False,
        revision: str | None = None,
        confirm: bool = False,
    ) -> dict:
        self._latest_settings = settings
        if not self._enabled(settings):
            return self.status(settings)
        if self.task and not self.task.done():
            return {**self.status(settings), "reason": "generating"}
        config = settings.schedule
        owner = owner_identity(settings)
        existing = self.store.load()
        if revision is not None and (existing or {}).get("revision") != revision:
            raise ScheduleError("revision_conflict")
        now = self.clock().astimezone(UTC)
        today = local_now(config, now).date()
        current = self.store.get_or_generate(config, now, owner=owner)
        if current and not force:
            return self.status(settings)
        if not force and not config.auto_generate:
            return self.status(settings)
        if current and current.get("manual_override") and force and not confirm:
            raise ScheduleError("manual_schedule_requires_confirmation")
        if config.generation_mode == "template":
            self.store.generate(config, today, owner=owner, revision=revision, confirm=confirm)
            return self.status(settings)
        record = self._read_state(settings)
        if not force and record and record.get("attempt_count", 0) >= MAX_AUTO_ATTEMPTS:
            return {**self.status(settings), "reason": "daily_limit"}
        if (
            record
            and record.get("next_retry_at")
            and now < datetime.fromisoformat(record["next_retry_at"])
        ):
            return {**self.status(settings), "reason": "cooldown"}
        key = self._key(settings)
        self._active_key = key
        # Persist before starting the paid request; reload during an in-flight
        # request must not immediately charge again.
        self._state = {
            "date": key[0],
            "fingerprint": key[1],
            "reason": "generating",
            "last_error": "",
            "provider_id": config.provider_id,
            "attempted_at": now.isoformat(),
            "attempt_count": (record or {}).get("attempt_count", 0) + 1,
            "next_retry_at": (
                now + timedelta(seconds=config.model_timeout + config.retry_cooldown)
            ).isoformat(),
        }
        self.store.save_generation_status(self._state)
        expected_revision = (existing or {}).get("revision")
        prompt = planning_prompt(settings, today, existing)
        self.task = asyncio.create_task(self._run(settings, prompt, today, expected_revision, now))
        return self.status(settings)

    async def _run(
        self,
        settings: Settings,
        prompt: str,
        today: date,
        expected_revision: str | None,
        attempted_at: datetime,
    ) -> None:
        config = settings.schedule
        code = ""
        provider = config.provider_id
        try:
            answer = await asyncio.wait_for(
                self.generate(config.provider_id, prompt, SYSTEM_PROMPT, config.model_timeout),
                timeout=config.model_timeout,
            )
            if (
                not isinstance(answer, tuple)
                or len(answer) != 2
                or not isinstance(answer[0], str)
                or not isinstance(answer[1], str)
                or not answer[1].strip()
            ):
                raise ScheduleError("invalid_provider_response")
            text, provider = answer
            slots = validate_model_response(text, config, today)
            live = self.current_settings() if self.current_settings else self._latest_settings
            if not self._enabled(live) or signature(
                live.schedule, owner_identity(live)
            ) != signature(config, owner_identity(settings)):
                raise ScheduleError("generation_settings_changed")
            if local_now(config, self.clock()).date() != today:
                raise ScheduleError("generation_date_changed")
            self.store.commit_model(
                config,
                slots,
                owner=owner_identity(settings),
                expected_revision=expected_revision,
                expected_date=today,
                provider_id=provider,
                now=self.clock(),
            )
        except asyncio.CancelledError:
            self._persist_outcome("cancelled", "", provider, attempted_at + timedelta(seconds=60))
            raise
        except TimeoutError:
            code = "model_timeout"
        except ScheduleError as error:
            allowed = {
                "provider_missing",
                "unexpected_tool_calls",
                "empty_model_response",
                "invalid_provider_response",
                "invalid_model_response",
                "invalid_model_json",
                "invalid_model_document",
                "invalid_model_slot_schema",
                "model_date_or_timezone_mismatch",
                "model_incomplete_day",
                "model_fixed_anchor_changed",
                "invalid_slot_count",
                "invalid_slot_object",
                "invalid_slot_text",
                "invalid_slot_text_length",
                "expected_HH_MM",
                "slot_time_order",
                "overlapping_slots",
                "revision_conflict",
                "generation_settings_changed",
                "generation_date_changed",
            }
            code = str(error) if str(error) in allowed else "model_response_invalid"
        except OSError:
            code = "schedule_storage_unavailable"
        except Exception:
            code = "provider_request_failed"
        if code:
            self._persist_outcome(
                "generation_failed",
                code,
                provider,
                self.clock().astimezone(UTC) + timedelta(seconds=config.retry_cooldown),
            )
        else:
            self._persist_outcome("enabled", "", provider, attempted_at + timedelta(seconds=60))

    def _persist_outcome(self, reason: str, code: str, provider: str, retry_at: datetime) -> None:
        record = {
            **(self._state or {}),
            "reason": reason,
            "last_error": code,
            "provider_id": provider,
            "next_retry_at": retry_at.isoformat(),
        }
        self._state = record
        try:
            self.store.save_generation_status(record)
        except (OSError, ScheduleError):
            # The earlier persisted reservation still prevents reload storms.
            pass

    async def cancel(self) -> None:
        task = self.task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.task = None
        self._active_key = None
