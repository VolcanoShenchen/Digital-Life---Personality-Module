"""Adapter tests against API-shaped doubles, not a running AstrBot instance."""

import asyncio
import importlib
import json
import sys
import types
import unittest
from unittest.mock import Mock, patch

from tests.support import PACKAGE, ROOT, load_plugin_module, valid_config


class EventDouble:
    def __init__(self, *, admin=True, private=True, bot="20001", origin=None):
        self.admin = admin
        self.private = private
        self.bot = bot
        self.unified_msg_origin = origin or "qq-main:FriendMessage:10001"
        self.stopped = False
        self.call_llm = False
        self.sent = []

    def get_platform_id(self):
        return "qq-main"

    def get_platform_name(self):
        return "aiocqhttp"

    def get_self_id(self):
        return self.bot

    def is_private_chat(self):
        return self.private

    def is_admin(self):
        return self.admin

    def should_call_llm(self, value):
        self.call_llm = value

    def stop_event(self):
        self.stopped = True

    def plain_result(self, text):
        return text

    async def send(self, result):
        self.sent.append(result)


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        load_plugin_module("runtime")
        self.module_name = f"{PACKAGE}.main"
        sys.modules.pop(self.module_name, None)
        modules = {
            key: types.ModuleType(key)
            for key in (
                "astrbot",
                "astrbot.api",
                "astrbot.api.event",
                "astrbot.api.provider",
                "astrbot.api.star",
            )
        }
        self.logger = Mock()
        modules["astrbot.api"].AstrBotConfig = dict
        modules["astrbot.api"].logger = self.logger
        modules["astrbot.api.event"].AstrMessageEvent = EventDouble

        def tagged(tag, value):
            def decorate(method):
                setattr(method, tag, value)
                return method

            return decorate

        modules["astrbot.api.event"].filter = types.SimpleNamespace(
            PermissionType=types.SimpleNamespace(ADMIN="ADMIN"),
            on_llm_request=lambda: tagged("request_hook", True),
            command=lambda value: tagged("command_name", value),
            permission_type=lambda value: tagged("permission", value),
        )
        modules["astrbot.api.provider"].ProviderRequest = object

        class Star:
            def __init__(self, context, config=None):
                self.context = context

        modules["astrbot.api.star"].Star = Star
        modules["astrbot.api.star"].Context = object
        self.module_patch = patch.dict(sys.modules, modules)
        self.module_patch.start()
        self.entry = importlib.import_module(self.module_name)
        self.plugin_type = self.entry.DigitalLifePersonality

    def tearDown(self):
        sys.modules.pop(self.module_name, None)
        self.module_patch.stop()

    @staticmethod
    def request():
        return types.SimpleNamespace(
            system_prompt="HOST_PERSONA\nTOOL_INSTRUCTIONS",
            prompt="USER_INPUT",
            contexts=[{"role": "user", "content": "HISTORY"}],
            image_urls=["IMAGE"],
            audio_urls=["AUDIO"],
            extra_user_content_parts=[{"type": "text", "text": "DYNAMIC_CONTEXT"}],
            model="HOST_MODEL",
            func_tool=object(),
            tool_calls_result=["TOOL_RESULT"],
            conversation=object(),
        )

    async def test_request_changes_only_system_prompt_and_does_not_send(self):
        plugin = self.plugin_type(object(), valid_config())
        event = EventDouble()
        req = self.request()
        before = vars(req).copy()
        await plugin.apply_personality(event, req)
        self.assertTrue(req.system_prompt.startswith(before.pop("system_prompt")))
        self.assertIn("测试角色", req.system_prompt)
        for key, value in before.items():
            self.assertIs(getattr(req, key), value)
        self.assertEqual(event.sent, [])
        self.assertFalse(event.stopped)
        self.assertFalse(event.call_llm)

    async def test_scope_comes_from_host_identity_and_requires_bot(self):
        plugin = self.plugin_type(object(), valid_config())
        for event in (EventDouble(bot="other-bot"), EventDouble(private=False)):
            req = self.request()
            original = req.system_prompt
            await plugin.apply_personality(event, req)
            self.assertEqual(req.system_prompt, original)

    async def test_retries_are_idempotent(self):
        plugin = self.plugin_type(object(), valid_config())
        event = EventDouble()
        req = self.request()
        await plugin.apply_personality(event, req)
        first = req.system_prompt
        await plugin.apply_personality(event, req)
        self.assertEqual(req.system_prompt, first)

    async def test_unsupported_request_is_unchanged_and_warns_once(self):
        plugin = self.plugin_type(object(), valid_config())
        req = self.request()
        req.system_prompt = None
        for _ in range(2):
            await plugin.apply_personality(EventDouble(), req)
        self.assertIsNone(req.system_prompt)
        self.logger.warning.assert_called_once_with(
            "[DigitalLifePersonality] unsupported_system_prompt"
        )

    async def test_bad_scope_is_isolated_without_logging_user_data(self):
        plugin = self.plugin_type(object(), valid_config())
        event = EventDouble()
        event.get_self_id = Mock(side_effect=RuntimeError("SECRET_RAW_EVENT"))
        req = self.request()
        original = req.system_prompt
        await plugin.apply_personality(event, req)
        await plugin.apply_personality(event, req)
        self.assertEqual(req.system_prompt, original)
        self.logger.warning.assert_called_once_with(
            "[DigitalLifePersonality] request_adapter_error"
        )
        self.assertNotIn("SECRET", str(self.logger.mock_calls))

    async def test_cancellation_propagates(self):
        plugin = self.plugin_type(object(), valid_config())
        plugin.runtime.apply = Mock(side_effect=asyncio.CancelledError)
        with self.assertRaises(asyncio.CancelledError):
            await plugin.apply_personality(EventDouble(), self.request())

    async def test_admin_command_sends_once_and_disables_default_llm(self):
        plugin = self.plugin_type(object(), valid_config())
        event = EventDouble()
        await plugin.personality_status(event)
        self.assertTrue(event.stopped)
        self.assertTrue(event.call_llm)
        self.assertEqual(len(event.sent), 1)
        self.assertIn("人格模块 0.1.0", event.sent[0])
        for private_text in ("测试角色", event.unified_msg_origin, "20001"):
            self.assertNotIn(private_text, event.sent[0])
        self.assertEqual(plugin.personality_status.permission, "ADMIN")
        self.assertEqual(plugin.personality_status.command_name, "人格状态")

    async def test_non_admin_cannot_read_status_even_if_filter_is_bypassed(self):
        plugin = self.plugin_type(object(), valid_config())
        event = EventDouble(admin=False)
        await plugin.personality_status(event)
        self.assertTrue(event.stopped)
        self.assertTrue(event.call_llm)
        self.assertEqual(event.sent, [])

    async def test_group_command_has_no_configuration_details(self):
        plugin = self.plugin_type(object(), valid_config())
        event = EventDouble(private=False)
        await plugin.personality_status(event)
        self.assertEqual(event.sent, ["请在私聊中查看人格状态。"])

    async def test_scope_error_in_admin_command_is_content_free(self):
        plugin = self.plugin_type(object(), valid_config())
        event = EventDouble()
        event.get_self_id = Mock(side_effect=RuntimeError("SECRET_EVENT"))
        await plugin.personality_status(event)
        self.assertEqual(len(event.sent), 1)
        self.assertNotIn("SECRET", event.sent[0])
        self.assertIn("scope_adapter_error", event.sent[0])

    async def test_default_constructor_does_not_enable_persona(self):
        plugin = self.plugin_type(object())
        req = self.request()
        original = req.system_prompt
        await plugin.apply_personality(EventDouble(), req)
        self.assertEqual(req.system_prompt, original)
        self.assertFalse(plugin.runtime.settings.enabled)

    async def test_invalid_config_warns_without_echoing_values(self):
        plugin = self.plugin_type(object(), valid_config(expression={"tone": "SECRET"}))
        self.logger.warning.assert_called_once()
        self.assertNotIn("SECRET", str(self.logger.mock_calls))
        req = self.request()
        original = req.system_prompt
        await plugin.apply_personality(EventDouble(), req)
        self.assertEqual(req.system_prompt, original)

    async def test_terminate_releases_diagnostic_records(self):
        plugin = self.plugin_type(object(), valid_config())
        event = EventDouble()
        await plugin.apply_personality(event, self.request())
        await plugin.terminate()
        self.assertIn("not_observed", plugin.runtime.status(self.entry.event_scope(event)))


class SchemaTests(unittest.TestCase):
    def test_schema_defaults_match_runtime_and_all_documented_choices_parse(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text("utf-8"))

        def defaults(fields):
            return {
                key: defaults(spec["items"]) if spec["type"] == "object" else spec["default"]
                for key, spec in fields.items()
            }

        config = defaults(schema)
        settings = load_plugin_module("settings")
        self.assertEqual(settings.Settings.parse(config), settings.Settings.parse({}))
        for key, spec in schema["expression"]["items"].items():
            for choice in spec.get("options", []):
                with self.subTest(key=key, choice=choice):
                    settings.Settings.parse(valid_config(expression={key: choice}))
        self.assertEqual(schema["allowed_sessions"]["_special"], "umo")
        self.assertFalse(config["enabled"])
        self.assertEqual(config["allowed_bot_ids"], [])


if __name__ == "__main__":
    unittest.main()
