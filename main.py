"""AstrBot entry point and asynchronous daily planning integration."""

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
from .personality import Scope, scope_reason
from .runtime import VERSION, Runtime
from .schedule import (
    SCHEDULE_END,
    SCHEDULE_START,
    ScheduleError,
    ScheduleStore,
    local_now,
    owner_identity,
    signature,
)
from .schedule_planner import SchedulePlanner


def event_scope(event: AstrMessageEvent) -> Scope:
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
        root = Path(get_astrbot_plugin_data_path()) / "astrbot_plugin_digital_life_personality"
        self.schedule_store = ScheduleStore(root / "schedule")
        self.runtime = Runtime(self.config, self.schedule_store)
        self.planner = SchedulePlanner(
            self.schedule_store,
            self._generate_schedule_text,
            current_settings=lambda: self.runtime.settings,
        )
        self._schedule_task: asyncio.Task | None = None
        self._schedule_generation_key = ""
        self._last_error = ""
        if self.runtime.config_error:
            logger.warning(f"[DigitalLifePersonality] {self.runtime.config_error}")
        register = getattr(context, "register_web_api", None)
        if callable(register):
            for suffix, handler, methods, description in (
                ("settings", self.web_get_settings, ["GET"], "Read personality settings"),
                ("settings", self.web_save_settings, ["POST"], "Save personality settings"),
                ("schedule", self.web_get_schedule, ["GET"], "Read today's schedule"),
                (
                    "schedule/providers",
                    self.web_schedule_providers,
                    ["GET"],
                    "List chat model identifiers",
                ),
                (
                    "schedule/generate",
                    self.web_generate_schedule,
                    ["POST"],
                    "Generate today's schedule",
                ),
                ("schedule/update", self.web_update_schedule, ["POST"], "Edit today's schedule"),
            ):
                register(
                    "/astrbot_plugin_digital_life_personality/" + suffix,
                    handler,
                    methods,
                    description,
                )

    async def _default_schedule_provider(self):
        resolver = getattr(self.context, "get_using_provider_async", None)
        if not callable(resolver):
            raise ScheduleError("provider_missing")
        provider = await resolver()
        if provider is None:
            raise ScheduleError("provider_missing")
        meta = provider.meta()
        identifier = getattr(meta, "id", None)
        if not isinstance(identifier, str) or not identifier:
            raise ScheduleError("provider_missing")
        return identifier

    async def _generate_schedule_text(
        self, provider_id: str, prompt: str, system_prompt: str, timeout: int
    ):
        identifier = provider_id or await self._default_schedule_provider()
        providers = getattr(self.context, "get_all_providers", None)
        if not callable(providers):
            raise ScheduleError("provider_missing")
        valid_ids = {getattr(provider.meta(), "id", "") for provider in providers()}
        if identifier not in valid_ids:
            raise ScheduleError("provider_missing")
        generate = getattr(self.context, "llm_generate", None)
        if not callable(generate):
            raise ScheduleError("provider_missing")
        # SDK text-only call: no ordinary chat history, tool execution, hooks,
        # message sending or additional credentials in the planning request.
        response = await asyncio.wait_for(
            generate(
                chat_provider_id=identifier,
                prompt=prompt,
                system_prompt=system_prompt,
                contexts=[],
                tools=None,
                max_tokens=6000,
            ),
            timeout=timeout,
        )
        if getattr(response, "role", "assistant") != "assistant":
            raise ScheduleError("invalid_model_response")
        if getattr(response, "tools_call_name", None) or getattr(response, "tools_call_args", None):
            raise ScheduleError("unexpected_tool_calls")
        text = getattr(response, "completion_text", None)
        if not isinstance(text, str) or not text.strip():
            raise ScheduleError("empty_model_response")
        return text, identifier

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
        settings = self.runtime.settings
        enabled = self.runtime.schedule_available()
        generation_key = signature(settings.schedule, owner_identity(settings)) if enabled else ""
        if generation_key != self._schedule_generation_key:
            await self.planner.cancel()
        self._schedule_generation_key = generation_key
        if enabled and settings.schedule.auto_generate:
            self._start_automatic_plan()
            self._schedule_task = asyncio.create_task(self._schedule_loop())

    def _start_automatic_plan(self):
        if (
            not self.runtime.schedule_available()
            or not self.runtime.settings.schedule.auto_generate
        ):
            return
        try:
            self.planner.start(self.runtime.settings)
        except (ScheduleError, OSError):
            self.runtime.schedule_error = "schedule_unavailable"

    async def _schedule_loop(self):
        while True:
            await asyncio.sleep(30)
            self._start_automatic_plan()

    @staticmethod
    def _web_config(config: Any) -> dict[str, Any]:
        return deepcopy(dict(config)) if isinstance(config, dict) else {}

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
            {"config": self._web_config(self.config), "summary": self._web_summary()}
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
            {"saved": True, "config": self._web_config(self.config), "summary": self._web_summary()}
        )

    async def web_schedule_providers(self):
        if not request.username:
            return error_response("dashboard authentication required", status_code=401)
        result = []
        try:
            for provider in self.context.get_all_providers():
                meta = provider.meta()
                identifier = getattr(meta, "id", "")
                model = getattr(meta, "model", "")
                if isinstance(identifier, str) and identifier:
                    result.append(
                        {
                            "id": identifier,
                            "label": identifier
                            + (" · " + model if isinstance(model, str) and model else ""),
                        }
                    )
            default_id = await self._default_schedule_provider()
        except Exception:
            default_id = ""
        return json_response({"providers": result, "default_id": default_id})

    def _schedule_payload(self) -> dict:
        today = self.runtime.schedule_today()
        current = self.runtime.schedule_current()
        status = self.runtime.schedule_status()
        if self.runtime.schedule_available() and not self.runtime.schedule_error:
            try:
                status = self.planner.status(self.runtime.settings)
            except (ScheduleError, OSError):
                status = {"enabled": True, "reason": "schedule_unavailable"}
        return {
            "config": self._web_config(self.config).get("schedule", {}),
            "today": today,
            "current": current,
            "status": status,
        }

    async def web_get_schedule(self):
        if not request.username:
            return error_response("dashboard authentication required", status_code=401)
        # Read-only: polling never triggers another paid generation request.
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
        settings = self.runtime.settings
        if revision is not None and (
            payload.get("date") != local_now(settings.schedule).date().isoformat()
            or payload.get("timezone") != settings.schedule.timezone
        ):
            return error_response(
                "schedule date or timezone changed; reload today", status_code=409
            )
        try:
            status = self.planner.start(
                settings, force=True, revision=revision, confirm=payload.get("confirm") is True
            )
        except ScheduleError as error:
            code = str(error)
            return error_response(
                code,
                status_code=409
                if code in ("revision_conflict", "manual_schedule_requires_confirmation")
                else 400,
            )
        except OSError:
            return error_response("schedule storage unavailable", status_code=503)
        return json_response(
            {
                "accepted": status.get("reason") == "generating",
                "saved": settings.schedule.generation_mode == "template"
                and status.get("reason") == "enabled",
                **self._schedule_payload(),
                "status": status,
            }
        )

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
        settings = self.runtime.settings
        if (
            payload.get("date") != local_now(settings.schedule).date().isoformat()
            or payload.get("timezone") != settings.schedule.timezone
        ):
            return error_response(
                "schedule date or timezone changed; reload today", status_code=409
            )
        try:
            self.schedule_store.update_slots(
                settings.schedule,
                payload["slots"],
                owner=owner_identity(settings),
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
        try:
            scope = event_scope(event)
            outcome = self.runtime.apply(req.system_prompt, scope)
            if self.runtime.settings and scope_reason(self.runtime.settings, scope) == "applied":
                self._start_automatic_plan()
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
            if self._last_error != "request_adapter_error":
                logger.warning("[DigitalLifePersonality] request_adapter_error")
            self._last_error = "request_adapter_error"

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("人格状态")
    async def personality_status(self, event: AstrMessageEvent):
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
        await self.planner.cancel()
        self.runtime.clear()
