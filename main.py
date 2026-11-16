"""AstrBot entry point; ordinary chat stays in the host pipeline."""

import asyncio
from contextlib import suppress
from copy import deepcopy
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star
from astrbot.api.web import error_response, json_response, request
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from .dynamic_state import STATE_END, STATE_START
from .personality import Scope
from .runtime import VERSION, Runtime
from .schedule import (
    SCHEDULE_END,
    SCHEDULE_START,
    ScheduleError,
    ScheduleStore,
    local_now,
    owner_identity,
)


def event_scope(event: AstrMessageEvent) -> Scope:
    """Use public host identities; never infer a bot identity from the UMO."""
    return Scope(
        origin=event.unified_msg_origin,
        platform_id=event.get_platform_id(),
        bot_id=event.get_self_id(),
        platform_type=event.get_platform_name(),
        private=event.is_private_chat(),
    )


class DigitalLifePersonality(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context, config)
        self.config = config if config is not None else {}
        data_root = Path(get_astrbot_plugin_data_path()) / "astrbot_plugin_digital_life_personality"
        self.schedule_store = ScheduleStore(data_root / "schedule")
        self.runtime = Runtime(self.config, self.schedule_store)
        self._schedule_task: asyncio.Task | None = None
        self._last_error = ""
        if self.runtime.config_error:
            logger.warning(f"[DigitalLifePersonality] {self.runtime.config_error}")
        register_web_api = getattr(context, "register_web_api", None)
        if callable(register_web_api):
            register_web_api(
                "/astrbot_plugin_digital_life_personality/settings",
                self.web_get_settings,
                ["GET"],
                "Read personality settings for the dashboard view",
            )
            register_web_api(
                "/astrbot_plugin_digital_life_personality/settings",
                self.web_save_settings,
                ["POST"],
                "Save personality settings from the dashboard view",
            )
            register_web_api(
                "/astrbot_plugin_digital_life_personality/schedule",
                self.web_get_schedule,
                ["GET"],
                "Read today's schedule",
            )
            register_web_api(
                "/astrbot_plugin_digital_life_personality/schedule/generate",
                self.web_generate_schedule,
                ["POST"],
                "Generate today's schedule",
            )
            register_web_api(
                "/astrbot_plugin_digital_life_personality/schedule/update",
                self.web_update_schedule,
                ["POST"],
                "Update today's schedule",
            )

    async def initialize(self):
        await self._restart_schedule_task()

    async def _stop_schedule_task(self):
        task = self._schedule_task
        self._schedule_task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def _restart_schedule_task(self):
        await self._stop_schedule_task()
        if self.runtime.schedule_available() and self.runtime.settings.schedule.auto_generate:
            # Initialize today's plan immediately. No network/model call, no
            # messages sent. Later checks also work when nobody is chatting.
            self.runtime.schedule_today()
            self._schedule_task = asyncio.create_task(self._schedule_loop())

    async def _schedule_loop(self):
        while True:
            await asyncio.sleep(30)
            if self.runtime.schedule_available():
                self.runtime.schedule_today()

    @staticmethod
    def _web_config(config: Any) -> dict[str, Any]:
        """Return a detached JSON-safe copy of the editable configuration."""
        if not isinstance(config, dict):
            return {}
        return deepcopy(dict(config))

    def _web_summary(self) -> dict[str, Any]:
        return {
            "version": VERSION,
            "valid": self.runtime.settings is not None,
            "enabled": bool(self.runtime.settings and self.runtime.settings.enabled),
            "authority_mode": self.runtime.settings.persona_authority.mode
            if self.runtime.settings
            else "overlay",
            "config_error": self.runtime.config_error,
            "dynamic_state": self.runtime.dynamic_summary(),
            "legacy_current_situation_ignored": bool(
                self.runtime.settings and self.runtime.settings.background.current_situation
            ),
            "runtime_applies_on_reload": False,
        }

    async def web_get_settings(self):
        if not request.username:
            return error_response("dashboard authentication required", status_code=401)
        return json_response(
            {
                "config": self._web_config(self.config),
                "summary": self._web_summary(),
            }
        )

    async def web_save_settings(self):
        if not request.username:
            return error_response("dashboard authentication required", status_code=401)
        payload = await request.json(default={})
        if not isinstance(payload, dict):
            return error_response("configuration must be a JSON object", status_code=400)
        candidate = deepcopy(payload)
        candidate_runtime = Runtime(candidate, self.schedule_store)
        if candidate_runtime.settings is None:
            return error_response(
                candidate_runtime.config_error or "invalid configuration", status_code=400
            )
        saver = getattr(self.config, "save_config", None)
        if not callable(saver):
            return error_response("configuration storage unavailable", status_code=503)
        previous = deepcopy(dict(self.config))
        try:
            self.config.clear()
            self.config.update(candidate)
            saver()
        except Exception:
            self.config.clear()
            self.config.update(previous)
            logger.warning("[DigitalLifePersonality] config_save_failed")
            return error_response("configuration could not be saved", status_code=500)
        self.runtime = candidate_runtime
        await self._restart_schedule_task()
        return json_response(
            {
                "saved": True,
                "config": self._web_config(self.config),
                "summary": self._web_summary(),
            }
        )

    def _schedule_payload(self) -> dict:
        today = self.runtime.schedule_today()
        current = self.runtime.schedule_current()
        return {
            "config": self._web_config(self.config).get("schedule", {}),
            "today": today,
            "current": current,
            "status": self.runtime.schedule_status(),
        }

    async def web_get_schedule(self):
        if not request.username:
            return error_response("dashboard authentication required", status_code=401)
        return json_response(self._schedule_payload())

    async def web_generate_schedule(self):
        if not request.username:
            return error_response("dashboard authentication required", status_code=401)
        if not self.runtime.schedule_available():
            return error_response("schedule module is disabled or invalid", status_code=400)
        payload = await request.json(default={})
        if not isinstance(payload, dict):
            return error_response("expected JSON object", status_code=400)
        revision = payload.get("revision")
        if revision is not None and not isinstance(revision, str):
            return error_response("invalid revision", status_code=400)
        if revision is not None and (
            payload.get("date") != local_now(self.runtime.settings.schedule).date().isoformat()
            or payload.get("timezone") != self.runtime.settings.schedule.timezone
        ):
            return error_response(
                "schedule date or timezone changed; reload today", status_code=409
            )
        try:
            self.schedule_store.generate(
                self.runtime.settings.schedule,
                owner=owner_identity(self.runtime.settings),
                revision=revision,
                confirm=payload.get("confirm") is True,
            )
        except ScheduleError as error:
            status = (
                409
                if str(error) in ("revision_conflict", "manual_schedule_requires_confirmation")
                else 400
            )
            return error_response(str(error), status_code=status)
        except OSError:
            return error_response("schedule storage unavailable", status_code=503)
        return json_response({"saved": True, **self._schedule_payload()})

    async def web_update_schedule(self):
        if not request.username:
            return error_response("dashboard authentication required", status_code=401)
        if not self.runtime.schedule_available():
            return error_response("schedule module is disabled or invalid", status_code=400)
        payload = await request.json(default={})
        if not isinstance(payload, dict) or not isinstance(payload.get("slots"), list):
            return error_response("slots must be a list", status_code=400)
        revision = payload.get("revision")
        if not isinstance(revision, str) or not revision:
            return error_response("reload the current schedule before editing", status_code=400)
        if (
            payload.get("date") != local_now(self.runtime.settings.schedule).date().isoformat()
            or payload.get("timezone") != self.runtime.settings.schedule.timezone
        ):
            return error_response(
                "schedule date or timezone changed; reload today", status_code=409
            )
        try:
            self.schedule_store.update_slots(
                self.runtime.settings.schedule,
                payload["slots"],
                owner=owner_identity(self.runtime.settings),
                revision=revision,
            )
        except ScheduleError as error:
            return error_response(
                str(error), status_code=409 if str(error) == "revision_conflict" else 400
            )
        except PermissionError:
            return error_response("manual schedule editing is disabled", status_code=403)
        except OSError:
            return error_response("schedule storage unavailable", status_code=503)
        return json_response({"saved": True, **self._schedule_payload()})

    def _temporary_state_parts(self, req: ProviderRequest, scope: Scope, reason: str):
        parts = getattr(req, "extra_user_content_parts", None)
        contexts = []
        if reason == "applied":
            schedule = self.runtime.schedule_context(scope)
            dynamic = self.runtime.dynamic_context(scope)
            if schedule and self.runtime.dynamic_summary()["reason"] in ("expired", "not_started"):
                # An expired manual override must not negate a valid schedule.
                dynamic = ""
            if dynamic:
                contexts.append((STATE_START, STATE_END, dynamic))
            if schedule:
                contexts.append((SCHEDULE_START, SCHEDULE_END, schedule))
        if not isinstance(parts, list):
            if contexts:
                raise ValueError("temporary_parts_unsupported")
            return None

        def owned(part):
            text = getattr(part, "text", None)
            return (
                getattr(part, "_no_save", False)
                and isinstance(text, str)
                and (
                    text.startswith(STATE_START)
                    and text.endswith(STATE_END)
                    or text.startswith(SCHEDULE_START)
                    and text.endswith(SCHEDULE_END)
                )
            )

        clean = [part for part in parts if not owned(part)]
        if contexts:
            from astrbot.core.agent.message import TextPart

            for _, _, text in contexts:
                clean.append(TextPart(text=text).mark_as_temp())
        if len(clean) == len(parts) and all(a is b for a, b in zip(clean, parts, strict=True)):
            return None
        return clean

    @filter.on_llm_request()
    async def apply_personality(self, event: AstrMessageEvent, req: ProviderRequest):
        """Append stable character rules only to explicitly permitted private chats."""
        try:
            scope = event_scope(event)
            outcome = self.runtime.apply(req.system_prompt, scope)
            # Build both changes before mutating either request field.
            state_parts = self._temporary_state_parts(req, scope, outcome.reason)
            if isinstance(outcome.prompt, str):
                req.system_prompt = outcome.prompt
            if state_parts is not None:
                req.extra_user_content_parts[:] = state_parts
            if outcome.reason in ("malformed_owned_block", "unsupported_system_prompt"):
                if self._last_error != outcome.reason:
                    logger.warning(f"[DigitalLifePersonality] {outcome.reason}")
                self._last_error = outcome.reason
            else:
                self._last_error = ""
        except Exception:
            # asyncio cancellation and process termination are BaseException on
            # the supported Python version and intentionally propagate.
            if self._last_error != "request_adapter_error":
                logger.warning("[DigitalLifePersonality] request_adapter_error")
            self._last_error = "request_adapter_error"

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("人格状态")
    async def personality_status(self, event: AstrMessageEvent):
        """查看当前会话的人格规则注入状态，仅限 AstrBot 管理员私聊。"""
        # Explicitly protect configuration even if host command permissions are
        # changed to allow everyone. True means DISABLE default LLM in v4.29.4.
        event.should_call_llm(True)
        event.stop_event()
        if not event.is_admin():
            return
        if not event.is_private_chat():
            await event.send(event.plain_result("请在私聊中查看人格状态。"))
            return
        try:
            text = self.runtime.status(event_scope(event))
        except Exception:
            text = "人格状态暂不可读取：scope_adapter_error。"
        await event.send(event.plain_result(text))

    async def terminate(self):
        await self._stop_schedule_task()
        self.runtime.clear()
