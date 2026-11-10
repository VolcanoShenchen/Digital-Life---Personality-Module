"""AstrBot entry point; ordinary chat stays in the host pipeline."""

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star

from .personality import Scope
from .runtime import Runtime


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
        self.runtime = Runtime(config if config is not None else {})
        self._last_error = ""
        if self.runtime.config_error:
            logger.warning(f"[DigitalLifePersonality] {self.runtime.config_error}")

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
