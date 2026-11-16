"""Adapter tests against API-shaped doubles, not a running AstrBot instance."""

import asyncio
import importlib
import json
import sys
import tempfile
import types
import unittest
from datetime import UTC
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
                "astrbot.api.web",
                "astrbot.core.utils.astrbot_path",
            )
        }
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        modules["astrbot.core.utils.astrbot_path"].get_astrbot_plugin_data_path = (
            lambda: self.temp_directory.name
        )
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
        self.web_request = types.SimpleNamespace(username="test-admin")
        modules["astrbot.api.web"].request = self.web_request
        modules["astrbot.api.web"].json_response = lambda payload: payload
        modules["astrbot.api.web"].error_response = lambda message, status_code=400: {
            "error": message,
            "status_code": status_code,
        }

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
        self.assertIn("人格模块 0.4.0", event.sent[0])
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

    async def test_webui_reads_and_saves_configuration_without_model_calls(self):
        class StoredConfig(dict):
            def save_config(self):
                self.saved = True

        config = StoredConfig(valid_config())
        plugin = self.plugin_type(object(), config)
        loaded = await plugin.web_get_settings()
        self.assertEqual(loaded["config"]["character"]["name"], "测试角色")
        updated = valid_config()
        updated["character"]["name"] = "网页角色"

        async def body(default=None):
            return updated

        self.web_request.json = body
        saved = await plugin.web_save_settings()
        self.assertTrue(saved["saved"])
        self.assertEqual(plugin.runtime.settings.character.name, "网页角色")
        self.assertEqual(saved["config"]["character"]["name"], "网页角色")

    async def test_webui_rejects_invalid_configuration_without_mutating_runtime(self):
        plugin = self.plugin_type(object(), valid_config())

        async def body(default=None):
            return valid_config(character={})

        self.web_request.json = body
        result = await plugin.web_save_settings()
        self.assertEqual(result["status_code"], 400)
        self.assertEqual(plugin.runtime.settings.character.name, "测试角色")

    async def test_dynamic_part_is_temporary_and_replaced_on_retry_or_expiry(self):
        from datetime import datetime, timedelta

        class TextPart:
            def __init__(self, *, text):
                self.text = text
                self._no_save = False

            def mark_as_temp(self):
                self._no_save = True
                return self

        module = types.ModuleType("astrbot.core.agent.message")
        module.TextPart = TextPart
        now = datetime.now(UTC)
        config = valid_config(
            dynamic_state={
                "enabled": True,
                "target_session": "qq-main:FriendMessage:10001",
                "target_bot_id": "20001",
                "activity": "ACTIVE_SENTINEL",
                "updated_at": (now - timedelta(minutes=1)).isoformat(),
                "expires_at": (now + timedelta(minutes=30)).isoformat(),
            }
        )
        plugin = self.plugin_type(object(), config)
        req = self.request()
        foreign = req.extra_user_content_parts[0]
        with patch.dict(sys.modules, {"astrbot.core.agent.message": module}):
            await plugin.apply_personality(EventDouble(), req)
            self.assertEqual(len(req.extra_user_content_parts), 2)
            part = req.extra_user_content_parts[-1]
            self.assertTrue(part._no_save)
            self.assertIn("ACTIVE_SENTINEL", part.text)
            self.assertNotIn("ACTIVE_SENTINEL", req.system_prompt)
            await plugin.apply_personality(EventDouble(), req)
            self.assertEqual(len(req.extra_user_content_parts), 2)
            self.assertIs(req.extra_user_content_parts[0], foreign)
            config["dynamic_state"]["expires_at"] = now.isoformat()
            plugin.runtime = load_plugin_module("runtime").Runtime(config)
            await plugin.apply_personality(EventDouble(), req)
            self.assertEqual(len(req.extra_user_content_parts), 2)
            self.assertNotIn("ACTIVE_SENTINEL", req.extra_user_content_parts[-1].text)
            self.assertIn("不代表活动已经完成", req.extra_user_content_parts[-1].text)
            # An excluded request must also drop any existing owned temp part.
            await plugin.apply_personality(EventDouble(bot="other"), req)
            self.assertEqual(req.extra_user_content_parts, [foreign])

    async def test_state_injection_failure_leaves_original_request_unchanged(self):
        from datetime import datetime, timedelta

        now = datetime.now(UTC)
        config = valid_config(
            dynamic_state={
                "enabled": True,
                "target_session": "qq-main:FriendMessage:10001",
                "target_bot_id": "20001",
                "activity": "NOT_SAVED",
                "updated_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=30)).isoformat(),
            }
        )
        plugin = self.plugin_type(object(), config)
        req = self.request()
        req.extra_user_content_parts = None
        original = req.system_prompt
        await plugin.apply_personality(EventDouble(), req)
        self.assertEqual(req.system_prompt, original)
        self.assertIsNone(req.extra_user_content_parts)

    async def test_webui_save_failure_retains_previous_config_and_runtime(self):
        class BrokenStore(dict):
            def save_config(self):
                raise OSError("PRIVATE_DISK_ERROR")

        config = BrokenStore(valid_config())
        plugin = self.plugin_type(object(), config)
        previous = plugin.runtime

        async def body(default=None):
            return valid_config(enabled=False)

        self.web_request.json = body
        result = await plugin.web_save_settings()
        self.assertEqual(result["status_code"], 500)
        self.assertTrue(config["enabled"])
        self.assertIs(plugin.runtime, previous)
        self.assertNotIn("PRIVATE_DISK_ERROR", str(result))

    async def test_schedule_enabling_creates_today_and_disable_cancels_background_task(self):
        class StoredConfig(dict):
            def save_config(self):
                pass

        plugin = self.plugin_type(object(), StoredConfig(valid_config()))
        await plugin.initialize()
        self.assertIsNone(plugin._schedule_task)
        self.assertFalse(plugin.schedule_store.path.exists())
        candidate = valid_config(schedule={"enabled": True, "work_location": "LIBRARY"})

        async def body(default=None):
            return candidate

        self.web_request.json = body
        try:
            result = await plugin.web_save_settings()
            self.assertTrue(result["saved"])
            self.assertTrue(plugin.schedule_store.path.exists())
            task = plugin._schedule_task
            self.assertIsNotNone(task)
            candidate = valid_config(schedule={"enabled": False})
            result = await plugin.web_save_settings()
            self.assertTrue(result["saved"])
            self.assertIsNone(plugin._schedule_task)
            self.assertTrue(task.cancelled())
        finally:
            await plugin.terminate()

    async def test_schedule_api_disabled_and_unauthed_requests_cannot_write(self):
        plugin = self.plugin_type(object(), valid_config())
        result = await plugin.web_generate_schedule()
        self.assertEqual(result["status_code"], 400)
        self.assertFalse(plugin.schedule_store.path.exists())
        self.web_request.username = None
        for method in (
            plugin.web_get_schedule,
            plugin.web_generate_schedule,
            plugin.web_update_schedule,
        ):
            result = await method()
            self.assertEqual(result["status_code"], 401)

    async def test_schedule_edit_revision_conflict_and_manual_lock(self):
        config = valid_config(schedule={"enabled": True})
        plugin = self.plugin_type(object(), config)
        plan = plugin.runtime.schedule_today()
        payload = {
            "revision": plan["revision"],
            "date": plan["date"],
            "timezone": plan["timezone"],
            "slots": [
                {
                    "start": "00:00",
                    "end": "24:00",
                    "activity": "EDITED",
                    "location": "HERE",
                    "notes": "",
                }
            ],
        }

        async def body(default=None):
            return payload

        self.web_request.json = body
        edited = await plugin.web_update_schedule()
        self.assertTrue(edited["saved"])
        self.assertEqual(edited["today"]["slots"][0]["activity"], "EDITED")
        stale = await plugin.web_update_schedule()
        self.assertEqual(stale["status_code"], 409)
        payload = {
            "revision": edited["today"]["revision"],
            "date": plan["date"],
            "timezone": plan["timezone"],
        }
        denied = await plugin.web_generate_schedule()
        self.assertEqual(denied["status_code"], 409)
        payload["confirm"] = True
        regenerated = await plugin.web_generate_schedule()
        self.assertTrue(regenerated["saved"])
        self.assertFalse(regenerated["today"]["manual_override"])

    async def test_yesterday_editor_is_rejected_even_with_current_revision(self):
        plugin = self.plugin_type(object(), valid_config(schedule={"enabled": True}))
        plan = plugin.runtime.schedule_today()

        async def body(default=None):
            return {
                "date": "2000-01-01",
                "timezone": plan["timezone"],
                "revision": plan["revision"],
                "slots": plan["slots"],
            }

        self.web_request.json = body
        result = await plugin.web_update_schedule()
        self.assertEqual(result["status_code"], 409)
        self.assertEqual(plugin.schedule_store.load()["revision"], plan["revision"])

    async def test_invalid_stored_schedule_does_not_prevent_personality_request(self):
        plugin = self.plugin_type(object(), valid_config(schedule={"enabled": True}))
        plugin.schedule_store.root.mkdir(parents=True)
        plugin.schedule_store.path.write_text("{broken", "utf-8")
        req = self.request()
        await plugin.apply_personality(EventDouble(), req)
        self.assertIn("测试角色", req.system_prompt)
        self.assertEqual(plugin.runtime.schedule_status()["reason"], "schedule_unavailable")

    async def test_webui_requires_dashboard_authentication(self):
        plugin = self.plugin_type(object(), valid_config())
        self.web_request.username = None
        result = await plugin.web_get_settings()
        self.assertEqual(result["status_code"], 401)

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
        for section, spec in schema.items():
            if spec.get("type") != "object":
                continue
            for key, field in spec["items"].items():
                for choice in field.get("options", []):
                    with self.subTest(section=section, key=key, choice=choice):
                        option_config = valid_config()
                        option_config.setdefault(section, {})[key] = choice
                        settings.Settings.parse(option_config)
        self.assertFalse(config["enabled"])
        self.assertEqual(config["allowed_bot_ids"], [])


if __name__ == "__main__":
    unittest.main()
