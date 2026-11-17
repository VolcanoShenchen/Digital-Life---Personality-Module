"""Schedule storage keeps models separate from all read paths."""

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
DAY = date(2026, 11, 16)
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
        return parsed_config(
            generation_mode="template",
            template_lines=["00:00-24:00 | EXPLICIT_USER_ACTIVITY | LIBRARY"],
            **changes,
        ).schedule

    def test_disabled_never_creates_storage(self):
        config = self.config(enabled=False)
        self.assertIsNone(self.store.get_or_generate(config, NOON))
        with self.assertRaises(schedule.ScheduleError):
            self.store.generate(config)
        self.assertFalse(self.store.root.exists())

    def test_llm_default_and_old_persona_migration_never_generate_without_model(self):
        for config in (parsed_config().schedule, parsed_config(generation_mode="persona").schedule):
            self.assertEqual(config.generation_mode, "llm")
            self.assertIsNone(self.store.get_or_generate(config, NOON))
            self.assertIsNone(self.store.current_slot(config, NOON))
            with self.assertRaisesRegex(schedule.ScheduleError, "model_generation_required"):
                self.store.generate(config, DAY)
        self.assertFalse(self.store.root.exists())

    def test_legacy_default_rule_migrates_without_overwriting_custom_instructions(self):
        for text in (
            "按模板生成；不凭空添加未配置的现实事件。",
            "根据角色职业、常住地和作息生成；模板为可选固定安排。",
        ):
            parsed = parsed_config(generation_mode="persona", generation_rule=text)
            self.assertEqual(parsed.schedule.generation_rule, schedule.DEFAULT_RULE)
        custom = "每天安排一小时绘画，上午不要外出。"
        self.assertEqual(
            parsed_config(
                generation_mode="persona", generation_rule=custom
            ).schedule.generation_rule,
            custom,
        )

    def test_explicit_template_parses_and_current_slot_has_no_fake_gap_activity(self):
        config = parsed_config(
            generation_mode="template", template_lines=["09:00-10:00 | READING | STUDY"]
        ).schedule
        self.store.generate(config, DAY)
        self.assertIsNone(self.store.current_slot(config, NOON))
        self.assertEqual(
            self.store.current_slot(config, NOON.replace(hour=9))["activity"], "READING"
        )
        self.assertIsNone(self.store.current_slot(config, NOON.replace(hour=10)))

    def test_same_day_reload_keeps_revision_and_manual_plan(self):
        config = self.config()
        plan = self.store.generate(config, DAY, owner=OWNER)
        updated = self.store.update_slots(
            config,
            [{"start": "00:00", "end": "24:00", "activity": "MANUAL"}],
            DAY,
            owner=OWNER,
            revision=plan["revision"],
        )
        self.assertEqual(
            schedule.ScheduleStore(self.store.root).get_or_generate(
                replace(config, wake_time="08:00"), NOON, owner=OWNER
            ),
            updated,
        )

    def test_stale_revision_does_not_overwrite(self):
        config = self.config()
        first = self.store.generate(config, DAY)
        second = self.store.generate(config, DAY)
        with self.assertRaisesRegex(schedule.ScheduleError, "revision_conflict"):
            self.store.update_slots(config, second["slots"], DAY, revision=first["revision"])
        self.assertEqual(self.store.load(), second)

    def test_manual_plan_requires_confirmation_for_explicit_template_regeneration(self):
        config = self.config()
        manual = self.store.update_slots(
            config, [{"start": "00:00", "end": "24:00", "activity": "MANUAL"}], DAY
        )
        with self.assertRaisesRegex(
            schedule.ScheduleError, "manual_schedule_requires_confirmation"
        ):
            self.store.generate(config, DAY, revision=manual["revision"])
        self.assertFalse(
            self.store.generate(config, DAY, revision=manual["revision"], confirm=True)[
                "manual_override"
            ]
        )

    def test_template_daily_rollover_uses_local_date(self):
        config = self.config()
        initial = self.store.get_or_generate(config, NOON, owner=OWNER)
        utc = datetime(2026, 11, 16, 16, 30, tzinfo=UTC)
        later = self.store.get_or_generate(config, utc, owner=OWNER)
        self.assertEqual(later["date"], "2026-11-17")
        self.assertNotEqual(initial["revision"], later["revision"])

    def test_llm_yesterday_never_becomes_today(self):
        config = parsed_config().schedule
        self.store.commit_model(
            config,
            [{"start": "00:00", "end": "24:00", "activity": "MODEL_ACTIVITY"}],
            owner=OWNER,
            expected_revision=None,
            expected_date=DAY,
            provider_id="test-model",
            now=NOON,
        )
        self.assertIsNotNone(self.store.get_or_generate(config, NOON, owner=OWNER))
        self.assertIsNone(self.store.get_or_generate(config, NOON + timedelta(days=1), owner=OWNER))
        self.assertEqual(self.store.load()["date"], DAY.isoformat())

    def test_old_manual_identity_signature_is_preserved_without_model_replacement(self):
        parsed = parsed_config()
        owner = schedule.owner_identity(parsed)
        old_owner = {
            key: owner[key] for key in ("name", "identity", "occupation", "home", "source")
        }
        manual = self.store.update_slots(
            parsed.schedule,
            [{"start": "00:00", "end": "24:00", "activity": "OLD_MANUAL_KEEP"}],
            DAY,
            owner=old_owner,
        )
        self.assertEqual(self.store.get_or_generate(parsed.schedule, NOON, owner=owner), manual)
        changed = dict(owner, name="DIFFERENT_CHARACTER")
        self.assertIsNone(self.store.get_or_generate(parsed.schedule, NOON, owner=changed))

    def test_old_rule_plan_is_not_accepted_as_a_model_plan(self):
        config = parsed_config().schedule
        legacy = self.store._record(
            config,
            DAY,
            [{"start": "00:00", "end": "24:00", "activity": "OLD_RULE", "source": "persona"}],
            OWNER,
            False,
        )
        legacy["generation_mode"] = "persona"
        self.store._save(legacy)
        self.assertIsNone(self.store.get_or_generate(config, NOON, owner=OWNER))
        self.assertEqual(self.store.load()["slots"][0]["activity"], "OLD_RULE")

    def test_no_auto_generation_excludes_yesterday(self):
        config = self.config(auto_generate=False)
        self.store.generate(config, DAY)
        self.assertIsNone(self.store.get_or_generate(config, NOON + timedelta(days=1)))

    def test_changed_character_cannot_inherit_manual_plan(self):
        config = parsed_config().schedule
        self.store.update_slots(
            config, [{"start": "00:00", "end": "24:00", "activity": "PRIVATE"}], DAY, owner=OWNER
        )
        self.assertIsNone(self.store.get_or_generate(config, NOON, owner={"name": "OTHER"}))

    def test_old_revision_cannot_relabel_yesterday_as_today(self):
        config = self.config(auto_generate=False)
        plan = self.store.generate(config, DAY)
        with self.assertRaisesRegex(schedule.ScheduleError, "schedule_scope_or_date_changed"):
            self.store.update_slots(
                config, plan["slots"], DAY + timedelta(days=1), revision=plan["revision"]
            )
        self.assertEqual(self.store.load()["date"], DAY.isoformat())

    def test_bad_slots_are_rejected_not_truncated(self):
        bad = [
            [],
            [None],
            [{"start": "09:00", "end": "08:00", "activity": "x"}],
            [{"start": "09:00:01", "end": "10:00", "activity": "x"}],
            [{"start": "00:00", "end": "24:00", "activity": "x"}] * 33,
            [
                {"start": "09:00", "end": "10:00", "activity": "a"},
                {"start": "09:30", "end": "11:00", "activity": "b"},
            ],
        ]
        for slots in bad:
            with self.subTest(slots=slots), self.assertRaises(schedule.ScheduleError):
                self.store.update_slots(self.config(), slots, DAY)
        self.assertFalse(self.store.path.exists())

    def test_configuration_types_timezones_models_and_constraints(self):
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
            {"model_timeout": 9},
            {"model_timeout": 181},
            {"retry_cooldown": 59},
            {"retry_cooldown": 86401},
            {"provider_id": 3},
        ):
            with self.subTest(changes=changes), self.assertRaises(settings.ConfigError):
                parsed_config(**changes)

    def test_corrupt_storage_preserved_and_persona_still_works(self):
        self.store.root.mkdir()
        self.store.path.write_text("{broken", "utf-8")
        engine = runtime.Runtime(valid_config(schedule={"enabled": True}), self.store)
        self.assertIsNone(engine.schedule_today())
        self.assertEqual(engine.schedule_context(SCOPE), "")
        self.assertIn("测试角色", engine.apply("HOST", SCOPE).prompt)
        self.assertEqual(self.store.path.read_text("utf-8"), "{broken")

    def test_current_context_respects_scope_and_static_separation(self):
        parsed = parsed_config()
        self.store.commit_model(
            parsed.schedule,
            [
                {
                    "start": "00:00",
                    "end": "24:00",
                    "activity": "MODEL_ACTIVITY",
                    "location": "MODEL_PLACE",
                }
            ],
            owner=schedule.owner_identity(parsed),
            expected_revision=None,
            expected_date=DAY,
            provider_id="test-model",
            now=NOON,
        )
        context = schedule.build_schedule_context(parsed, SCOPE, self.store, NOON)
        self.assertIn("MODEL_PLACE", context)
        self.assertNotIn("MODEL_PLACE", personality.build_persona(parsed))
        self.assertIn("不是现实中已执行或已完成", context)
        for scope in (
            replace(SCOPE, bot_id="other"),
            replace(SCOPE, private=False),
            replace(SCOPE, origin="other"),
        ):
            self.assertEqual(schedule.build_schedule_context(parsed, scope, self.store, NOON), "")

    def test_manual_state_overrides_only_supplied_fields(self):
        parsed = settings.Settings.parse(
            valid_config(
                schedule={"enabled": True},
                dynamic_state={
                    "enabled": True,
                    "target_session": SCOPE.origin,
                    "target_bot_id": SCOPE.bot_id,
                    "activity": "MANUAL_ACTIVITY",
                    "updated_at": (NOON - timedelta(minutes=1)).isoformat(),
                    "expires_at": (NOON + timedelta(minutes=30)).isoformat(),
                },
            )
        )
        self.store.commit_model(
            parsed.schedule,
            [
                {
                    "start": "00:00",
                    "end": "24:00",
                    "activity": "MODEL_ACTIVITY",
                    "location": "MODEL_PLACE",
                }
            ],
            owner=schedule.owner_identity(parsed),
            expected_revision=None,
            expected_date=DAY,
            provider_id="test-model",
            now=NOON,
        )
        context = schedule.build_schedule_context(parsed, SCOPE, self.store, NOON)
        self.assertNotIn("当前计划活动", context)
        self.assertIn("MODEL_PLACE", context)
        self.assertIn(
            "当前计划活动",
            schedule.build_schedule_context(parsed, SCOPE, self.store, NOON + timedelta(hours=1)),
        )

    def test_reserved_markers_are_escaped(self):
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
