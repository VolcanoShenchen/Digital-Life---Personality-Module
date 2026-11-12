"""AstrBot entry point; ordinary chat stays in the host pipeline."""

from copy import deepcopy
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star
from astrbot.api.web import error_response, json_response, request

from .personality import Scope
from .runtime import VERSION, Runtime


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
        self.runtime = Runtime(self.config)
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
            "runtime_applies_on_reload": True,
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
        candidate_runtime = Runtime(candidate)
        if candidate_runtime.settings is None:
            return error_response(
                candidate_runtime.config_error or "invalid configuration", status_code=400
            )
        self.config.clear()
        self.config.update(candidate)
        saver = getattr(self.config, "save_config", None)
        if callable(saver):
            saver()
        self.runtime = candidate_runtime
        return json_response(
            {
                "saved": True,
                "config": self._web_config(self.config),
                "summary": self._web_summary(),
            }
        )

    @filter.on_llm_request()
    async def apply_personality(self, event: AstrMessageEvent, req: ProviderRequest):
        """Append stable character rules only to explicitly permitted private chats."""
        try:
            scope = event_scope(event)
            outcome = self.runtime.apply(req.system_prompt, scope)
            # Runtime returns a fully built value. No partially rewritten request.
            if isinstance(outcome.prompt, str):
                req.system_prompt = outcome.prompt
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
        self.runtime.clear()
