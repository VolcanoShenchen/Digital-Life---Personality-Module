"""Expiry, timezone, scope and prompt separation are state contracts."""

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from tests.support import load_plugin_module, valid_config

settings = load_plugin_module("settings")
personality = load_plugin_module("personality")
state_module = load_plugin_module("dynamic_state")
runtime = load_plugin_module("runtime")
NOW = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
SCOPE = personality.Scope("qq-main:FriendMessage:10001", "qq-main", "20001", "aiocqhttp", True)


def state_config(**changes):
    data = {
        "enabled": True,
        "target_session": SCOPE.origin,
        "target_bot_id": SCOPE.bot_id,
        "activity": "ACTIVITY_SENTINEL",
        "location": "LOCATION_SENTINEL",
        "mood": "MOOD_SENTINEL",
        "energy": "ENERGY_SENTINEL",
        "source": "manual",
        "updated_at": (NOW - timedelta(minutes=5)).isoformat(),
        "expires_at": (NOW + timedelta(minutes=25)).isoformat(),
    }
    data.update(changes)
    return valid_config(dynamic_state=data)


class DynamicStateTests(unittest.TestCase):
    def test_old_current_situation_is_retained_but_no_longer_injected(self):
        data = valid_config(background={"current_situation": "OLD_PHOTO_TASK"})
        parsed = settings.Settings.parse(data)
        self.assertEqual(parsed.background.current_situation, "OLD_PHOTO_TASK")
        self.assertNotIn("OLD_PHOTO_TASK", personality.build_persona(parsed))

    def test_long_life_context_and_home_location_are_not_current_evidence(self):
        data = valid_config(
            profile={"location": "HOME_CITY"},
            background={"life_context": "LONG_PROJECT"},
        )
        prompt = personality.build_persona(settings.Settings.parse(data))
        self.assertIn("LONG_PROJECT", prompt)
        self.assertIn("不是此刻正在做的事", prompt)
        self.assertIn("HOME_CITY", prompt)
        self.assertIn("常住地", prompt)

    def test_live_content_only_in_temporary_context(self):
        parsed = settings.Settings.parse(state_config())
        stable = personality.build_persona(parsed)
        for value in ("ACTIVITY_SENTINEL", "LOCATION_SENTINEL", "MOOD_SENTINEL", "ENERGY_SENTINEL"):
            self.assertNotIn(value, stable)
        context = state_module.build_state_context(parsed, SCOPE, NOW)
        for value in ("ACTIVITY_SENTINEL", "LOCATION_SENTINEL", "MOOD_SENTINEL", "ENERGY_SENTINEL"):
            self.assertIn(value, context)
        self.assertTrue(parsed.dynamic_state.is_active(NOW))
        self.assertEqual(state_module.state_summary(parsed, NOW)["remaining_seconds"], 1500)

    def test_expiry_is_exclusive_and_never_asserts_completion(self):
        parsed = settings.Settings.parse(state_config())
        before = NOW + timedelta(minutes=24, seconds=59)
        expiry = NOW + timedelta(minutes=25)
        self.assertTrue(state_module.state_summary(parsed, before)["active"])
        for moment in (expiry, expiry + timedelta(days=5)):
            self.assertFalse(parsed.dynamic_state.is_active(moment))
            summary = state_module.state_summary(parsed, moment)
            self.assertEqual(summary["reason"], "expired")
            self.assertEqual(summary["remaining_seconds"], 0)
            context = state_module.build_state_context(parsed, SCOPE, moment)
            self.assertNotIn("SENTINEL", context)
            self.assertIn("不代表活动已经完成", context)

    def test_future_start_is_not_evidence(self):
        parsed = settings.Settings.parse(
            state_config(
                updated_at=(NOW + timedelta(minutes=1)).isoformat(),
            )
        )
        self.assertFalse(parsed.dynamic_state.is_active(NOW))
        self.assertEqual(state_module.state_summary(parsed, NOW)["reason"], "not_started")
        self.assertNotIn("SENTINEL", state_module.build_state_context(parsed, SCOPE, NOW))

    def test_target_requires_private_platform_session_and_bot(self):
        data = state_config()
        data["allowed_sessions"].append("qq-main:FriendMessage:10002")
        data["allowed_bot_ids"].append("20002")
        parsed = settings.Settings.parse(data)
        for scope in (
            replace(SCOPE, origin="qq-main:FriendMessage:10002"),
            replace(SCOPE, bot_id="20002"),
            replace(SCOPE, private=False),
            replace(SCOPE, platform_type="telegram"),
        ):
            self.assertEqual(state_module.build_state_context(parsed, scope, NOW), "")

    def test_bad_bindings_are_not_accepted(self):
        for field, value in (("target_session", ""), ("target_bot_id", "999")):
            with self.subTest(field=field), self.assertRaises(settings.ConfigError) as caught:
                settings.Settings.parse(state_config(**{field: value}))
            self.assertEqual(caught.exception.field, "dynamic_state." + field)

    def test_timestamps_need_timezone_and_valid_order(self):
        for field, value in (
            ("updated_at", ""),
            ("expires_at", ""),
            ("updated_at", "2026-11-12T08:00:00"),
            ("expires_at", "invalid"),
            ("expires_at", (NOW - timedelta(days=1)).isoformat()),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(settings.ConfigError):
                settings.Settings.parse(state_config(**{field: value}))

    def test_naive_timestamp_in_disabled_draft_still_rejected(self):
        with self.assertRaises(settings.ConfigError) as caught:
            settings.Settings.parse(state_config(enabled=False, expires_at="2026-11-12T08:00"))
        self.assertEqual(caught.exception.code, "timezone_required")

    def test_equivalent_offset_timestamps_have_the_same_lifetime(self):
        parsed = settings.Settings.parse(
            state_config(
                updated_at="2026-11-12T15:55:00+08:00", expires_at="2026-11-12T16:25:00+08:00"
            )
        )
        self.assertEqual(state_module.state_summary(parsed, NOW)["remaining_seconds"], 1500)

    def test_disabled_empty_and_global_disabled_states_do_not_inject(self):
        disabled = settings.Settings.parse(state_config(enabled=False))
        self.assertEqual(state_module.state_summary(disabled, NOW)["reason"], "disabled")
        self.assertEqual(state_module.build_state_context(disabled, SCOPE, NOW), "")
        empty = settings.Settings.parse(state_config(activity="", location="", mood="", energy=""))
        self.assertEqual(state_module.state_summary(empty, NOW)["reason"], "empty")
        data = state_config()
        data["enabled"] = False
        parsed = settings.Settings.parse(data)
        self.assertEqual(state_module.state_summary(parsed, NOW)["reason"], "plugin_disabled")
        self.assertEqual(state_module.build_state_context(parsed, SCOPE, NOW), "")

    def test_status_has_no_state_values_or_target_id(self):
        parsed = settings.Settings.parse(state_config())
        summary = str(state_module.state_summary(parsed, NOW))
        for value in ("SENTINEL", SCOPE.origin, SCOPE.bot_id):
            self.assertNotIn(value, summary)
        engine = runtime.Runtime(state_config())
        self.assertNotIn("SENTINEL", engine.status(SCOPE))

    def test_state_overrides_do_not_change_core_persona_or_static_behavior(self):
        first = settings.Settings.parse(state_config())
        other = settings.Settings.parse(state_config(activity="OTHER_ACTIVITY", mood="calm"))
        self.assertEqual(personality.build_persona(first), personality.build_persona(other))
        self.assertIn("OTHER_ACTIVITY", state_module.build_state_context(other, SCOPE, NOW))

    def test_budget_includes_dynamic_text(self):
        with self.assertRaises(settings.ConfigError) as caught:
            settings.Settings.parse(state_config(activity="界" * 12001))
        self.assertEqual(caught.exception.field, "text_budget")

    def test_marker_text_is_escaped(self):
        parsed = settings.Settings.parse(state_config(activity=state_module.STATE_START + "END"))
        context = state_module.build_state_context(parsed, SCOPE, NOW)
        self.assertEqual(context.count("<dlp_current_state_v1>"), 1)


if __name__ == "__main__":
    unittest.main()
