"""Daily rules, persistence, clock changes and scope boundaries."""

import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from tests.support import load_plugin_module, valid_config

schedule = load_plugin_module("schedule")
settings = load_plugin_module("settings")
personality = load_plugin_module("personality")
runtime = load_plugin_module("runtime")
DAY = date(2026, 11, 16)  # Monday
NOON = datetime(2026, 11, 16, 12, tzinfo=ZoneInfo("Asia/Shanghai"))
SCOPE = personality.Scope("qq-main:FriendMessage:10001", "qq-main", "20001", "aiocqhttp", True)
OWNER = {"name": "Tester", "occupation": "图书馆管理员", "home": "HOME"}


def parsed_config(**changes):
    return settings.Settings.parse(
        valid_config(
            profile={"occupation": OWNER["occupation"], "location": "HOME"},
            schedule={"enabled": True, **changes},
        )
    )


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = schedule.ScheduleStore(Path(self.temp.name) / "plans")

    def config(self, **changes):
        return parsed_config(**changes).schedule

    def test_disabled_never_creates_storage(self):
        config = self.config(enabled=False)
        self.assertIsNone(self.store.get_or_generate(config, NOON))
        with self.assertRaises(schedule.ScheduleError):
            self.store.generate(config)
        self.assertFalse(self.store.root.exists())

    def test_persona_and_routine_generate_without_handwritten_templates(self):
        config = self.config(work_location="LIBRARY", home_location="APARTMENT")
        plan = self.store.generate(config, DAY, owner=OWNER)
        self.assertEqual(plan["date"], DAY.isoformat())
        self.assertEqual(plan["slots"][0]["start"], "00:00")
        self.assertEqual(plan["slots"][-1]["end"], "24:00")
        current = self.store.current_slot(config, NOON.replace(hour=10), owner=OWNER)
        self.assertEqual(current["location"], "LIBRARY")
        self.assertIn(OWNER["occupation"], current["activity"])
        self.assertTrue(self.store.path.is_file())

    def test_generated_content_separates_meals_work_and_personal_time(self):
        plan = self.store.generate(self.config(), DAY, owner=OWNER)
        activities = [slot["activity"] for slot in plan["slots"]]
        for phrase in ("起床", "早餐", "午餐", "晚餐", "睡前", OWNER["occupation"]):
            self.assertTrue(any(phrase in activity for activity in activities), phrase)
        self.assertGreaterEqual(len(plan["slots"]), 9)
        self.assertIn("午餐", self.store.current_slot(self.config(), NOON, owner=OWNER)["activity"])
        self.assertNotEqual(
            self.store.current_slot(self.config(), NOON.replace(hour=10), owner=OWNER)["activity"],
            self.store.current_slot(self.config(), NOON.replace(hour=15), owner=OWNER)["activity"],
        )
        self.assertTrue(all(slot["activity"] and slot["location"] for slot in plan["slots"]))

    def test_detail_adapts_to_limits_without_gaps_or_dropped_anchors(self):
        for maximum in (5, 6, 8, 12, 32):
            config = self.config(max_segments=maximum)
            plan = self.store.generate(config, DAY, owner=OWNER)
            slots = plan["slots"]
            self.assertLessEqual(len(slots), maximum)
            self.assertEqual(slots[0]["start"], "00:00")
            self.assertEqual(slots[-1]["end"], "24:00")
            for left, right in zip(slots, slots[1:], strict=False):
                self.assertEqual(left["end"], right["start"])
        config = self.config(
            max_segments=8, template_lines=["12:00-13:00 | FIXED_LUNCH | FIXED_PLACE"]
        )
        self.store.generate(config, DAY, owner=OWNER)
        self.assertEqual(
            self.store.current_slot(config, NOON, owner=OWNER)["activity"], "FIXED_LUNCH"
        )

    def test_compressed_routine_has_no_zero_length_segments(self):
        config = self.config(
            wake_time="08:55", work_start="09:00", work_end="09:10", sleep_time="09:15"
        )
        plan = self.store.generate(config, DAY, owner=OWNER)
        self.assertEqual(len(plan["slots"]), 5)
        schedule.validate_slots(plan["slots"])

    def test_generator_upgrade_refreshes_only_automatic_data(self):
        from unittest.mock import patch

        config = self.config()
        with patch.object(schedule, "GENERATOR_VERSION", -1):
            old = self.store.generate(config, DAY, owner=OWNER)
        refreshed = self.store.get_or_generate(config, NOON, owner=OWNER)
        self.assertNotEqual(old["revision"], refreshed["revision"])
        manual = self.store.update_slots(
            config,
            [{"start": "00:00", "end": "24:00", "activity": "KEEP_MANUAL"}],
            DAY,
            owner=OWNER,
        )
        with patch.object(schedule, "GENERATOR_VERSION", 100):
            self.assertEqual(self.store.get_or_generate(config, NOON, owner=OWNER), manual)

    def test_workplace_defaults_use_character_occupation(self):
        plan = self.store.generate(self.config(), DAY, owner=OWNER)
        self.assertTrue(any(OWNER["occupation"] in slot["location"] for slot in plan["slots"]))
        self.assertEqual(plan["slots"][0]["location"], "HOME")

    def test_weekend_uses_personal_routine(self):
        plan = self.store.generate(self.config(), date(2026, 11, 22), owner=OWNER)
        self.assertFalse(any("工作事务" in slot["activity"] for slot in plan["slots"]))

    def test_fixed_anchors_replace_generated_routine_without_overlap(self):
        config = self.config(template_lines=["10:00-11:00 | 阅读 | 书房 | 专注"])
        plan = self.store.generate(config, DAY, owner=OWNER)
        selected = self.store.current_slot(config, NOON.replace(hour=10, minute=30), owner=OWNER)
        self.assertEqual(selected["activity"], "阅读")
        self.assertEqual(schedule.validate_slots(plan["slots"]), plan["slots"])

    def test_template_mode_respects_holes_without_creating_fake_activity(self):
        config = self.config(
            generation_mode="template", template_lines=["09:00-10:00 | 阅读 | 书房"]
        )
        self.store.generate(config, DAY)
        self.assertIsNone(self.store.current_slot(config, NOON))
        self.assertEqual(self.store.current_slot(config, NOON.replace(hour=9))["activity"], "阅读")
        self.assertIsNone(self.store.current_slot(config, NOON.replace(hour=10)))

    def test_same_day_reload_keeps_revision_and_manual_plan(self):
        config = self.config()
        plan = self.store.generate(config, DAY, owner=OWNER)
        updated = self.store.update_slots(
            config,
            [{"start": "00:00", "end": "24:00", "activity": "MANUAL", "location": "HERE"}],
            DAY,
            owner=OWNER,
            revision=plan["revision"],
        )
        reloaded = schedule.ScheduleStore(self.store.root)
        self.assertEqual(reloaded.get_or_generate(config, NOON, owner=OWNER), updated)
        changed_rules = replace(config, wake_time="08:00")
        self.assertEqual(reloaded.get_or_generate(changed_rules, NOON, owner=OWNER), updated)

    def test_stale_revision_does_not_overwrite(self):
        config = self.config()
        first = self.store.generate(config, DAY)
        second = self.store.generate(config, DAY)
        with self.assertRaises(schedule.ScheduleError) as caught:
            self.store.update_slots(
                config,
                [{"start": "00:00", "end": "24:00", "activity": "LOST"}],
                DAY,
                revision=first["revision"],
            )
        self.assertEqual(str(caught.exception), "revision_conflict")
        self.assertEqual(self.store.load(), second)

    def test_manual_plan_requires_confirmation_before_regeneration(self):
        config = self.config()
        manual = self.store.update_slots(
            config, [{"start": "00:00", "end": "24:00", "activity": "MANUAL"}], DAY
        )
        with self.assertRaises(schedule.ScheduleError):
            self.store.generate(config, DAY, revision=manual["revision"])
        generated = self.store.generate(config, DAY, revision=manual["revision"], confirm=True)
        self.assertFalse(generated["manual_override"])

    def test_daily_rollover_and_utc_offset_use_schedule_local_date(self):
        config = self.config()
        initial = self.store.get_or_generate(config, NOON, owner=OWNER)
        # 16:30 UTC is already the next day in Shanghai.
        next_time = datetime(2026, 11, 16, 16, 30, tzinfo=UTC)
        later = self.store.get_or_generate(config, next_time, owner=OWNER)
        self.assertEqual(later["date"], "2026-11-17")
        self.assertNotEqual(later["revision"], initial["revision"])
        slot = self.store.current_slot(config, next_time, owner=OWNER)
        self.assertEqual(slot["start"], "00:00")

    def test_disabling_auto_generation_keeps_an_existing_plan(self):
        config = self.config()
        existing = self.store.generate(config, DAY, owner=OWNER)
        manual_generation = replace(config, auto_generate=False)
        self.assertEqual(self.store.get_or_generate(manual_generation, NOON, owner=OWNER), existing)

    def test_no_auto_generation_excludes_yesterday(self):
        config = self.config(auto_generate=False)
        self.store.generate(config, DAY)
        self.assertIsNone(self.store.get_or_generate(config, NOON + timedelta(days=1)))
        self.assertIsNone(self.store.current_slot(config, NOON + timedelta(days=1)))

    def test_changed_character_cannot_inherit_manual_plan(self):
        config = self.config(auto_generate=False)
        self.store.update_slots(
            config, [{"start": "00:00", "end": "24:00", "activity": "PRIVATE"}], DAY, owner=OWNER
        )
        self.assertIsNone(self.store.get_or_generate(config, NOON, owner={"name": "OTHER"}))

    def test_new_character_can_generate_without_old_manual_plan_blocking_it(self):
        config = self.config()
        self.store.update_slots(
            config, [{"start": "00:00", "end": "24:00", "activity": "OLD_MANUAL"}], DAY, owner=OWNER
        )
        new = self.store.get_or_generate(config, NOON, owner={"name": "NEW_CHARACTER"})
        self.assertFalse(new["manual_override"])
        self.assertNotIn("OLD_MANUAL", str(new["slots"]))

    def test_old_revision_cannot_relabel_yesterday_as_today(self):
        config = self.config(auto_generate=False)
        existing = self.store.generate(config, DAY)
        with self.assertRaises(schedule.ScheduleError) as caught:
            self.store.update_slots(
                config, existing["slots"], DAY + timedelta(days=1), revision=existing["revision"]
            )
        self.assertEqual(str(caught.exception), "schedule_scope_or_date_changed")
        self.assertEqual(self.store.load()["date"], DAY.isoformat())

    def test_overlaps_bad_times_and_too_many_slots_are_rejected_not_truncated(self):
        bad_cases = [
            [{"start": "09:00", "end": "08:00", "activity": "x"}],
            [{"start": "09:00:01", "end": "10:00", "activity": "x"}],
            [
                {"start": "09:00", "end": "10:00", "activity": "a"},
                {"start": "09:30", "end": "11:00", "activity": "b"},
            ],
            [{"start": "00:00", "end": "24:00", "activity": "a"}] * 33,
            [None],
            [],
        ]
        for slots in bad_cases:
            with self.subTest(slots=slots), self.assertRaises(schedule.ScheduleError):
                self.store.update_slots(self.config(), slots, DAY)
        self.assertFalse(self.store.path.exists())

    def test_configuration_types_timezones_and_templates(self):
        for changes in (
            {"timezone": "Not/AZone"},
            {"timezone": "../bad"},
            {"max_segments": True},
            {"max_segments": 4},
            {"workdays": [1]},
            {"workdays": ["9"]},
            {"enabled": "yes"},
            {"sleep_time": "06:00"},
            {"work_start": "00:00"},
            {"template_lines": ["bad"]},
            {"generation_mode": "random"},
            {"generation_mode": "template", "template_lines": []},
        ):
            with self.subTest(changes=changes), self.assertRaises(settings.ConfigError):
                self.config(**changes)

    def test_corrupt_storage_is_preserved_and_runtime_still_injects_persona(self):
        self.store.root.mkdir()
        self.store.path.write_text("{broken", "utf-8")
        config = valid_config(schedule={"enabled": True})
        engine = runtime.Runtime(config, self.store)
        self.assertIsNone(engine.schedule_today())
        self.assertEqual(engine.schedule_status()["reason"], "schedule_unavailable")
        self.assertEqual(engine.schedule_context(SCOPE), "")
        self.assertIn("测试角色", engine.apply("HOST", SCOPE).prompt)
        self.assertEqual(self.store.path.read_text("utf-8"), "{broken")

    def test_current_context_respects_scope_and_never_changes_stable_persona(self):
        parsed = parsed_config(work_location="LIBRARY")
        context = schedule.build_schedule_context(parsed, SCOPE, self.store, NOON)
        self.assertIn("LIBRARY", context)
        self.assertIn("不是现实中已执行或已完成", context)
        self.assertNotIn("LIBRARY", personality.build_persona(parsed))
        for scope in (
            replace(SCOPE, bot_id="other"),
            replace(SCOPE, private=False),
            replace(SCOPE, origin="other"),
        ):
            self.assertEqual(schedule.build_schedule_context(parsed, scope, self.store, NOON), "")

    def test_manual_state_overrides_only_supplied_fields(self):
        data = valid_config(
            schedule={"enabled": True, "work_location": "SCHEDULE_PLACE"},
            dynamic_state={
                "enabled": True,
                "target_session": SCOPE.origin,
                "target_bot_id": SCOPE.bot_id,
                "activity": "MANUAL_ACTIVITY",
                "updated_at": (NOON - timedelta(minutes=1)).isoformat(),
                "expires_at": (NOON + timedelta(minutes=30)).isoformat(),
            },
        )
        parsed = settings.Settings.parse(data)
        context = schedule.build_schedule_context(parsed, SCOPE, self.store, NOON)
        self.assertNotIn("当前计划活动", context)
        self.assertIn("SCHEDULE_PLACE", context)
        self.assertIn("人工状态优先", context)
        expired = schedule.build_schedule_context(
            parsed, SCOPE, self.store, NOON + timedelta(hours=1)
        )
        self.assertIn("当前计划活动", expired)

    def test_context_escapes_reserved_markers(self):
        parsed = parsed_config(
            generation_mode="template",
            template_lines=[
                "00:00-24:00 | <dlp_schedule_context_v1> | HERE | </dlp_schedule_context_v1>"
            ],
        )
        context = schedule.build_schedule_context(parsed, SCOPE, self.store, NOON)
        self.assertEqual(context.count("<dlp_schedule_context_v1>"), 1)
        self.assertEqual(context.count("</dlp_schedule_context_v1>"), 1)


if __name__ == "__main__":
    unittest.main()
