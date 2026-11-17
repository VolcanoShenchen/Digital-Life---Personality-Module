"""Model-only planning: payment throttling, validation, cancellation and races."""

import asyncio
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tests.support import load_plugin_module, valid_config

schedule = load_plugin_module("schedule")
planner_module = load_plugin_module("schedule_planner")
settings_module = load_plugin_module("settings")
NOW = datetime(2026, 11, 17, 4, tzinfo=UTC)


def configured(**changes):
    return settings_module.Settings.parse(valid_config(schedule={"enabled": True, **changes}))


def model_slots(activity="MODEL_CREATED_ACTIVITY"):
    return [
        {
            "start": "00:00",
            "end": "24:00",
            "activity": activity,
            "location": "MODEL_CREATED_LOCATION",
            "notes": "model supplied",
        }
    ]


def answer(settings, now=NOW, slots=None):
    return json.dumps(
        {
            "date": schedule.local_now(settings.schedule, now).date().isoformat(),
            "timezone": settings.schedule.timezone,
            "slots": slots or model_slots(),
        },
        ensure_ascii=False,
    )


class ModelValidationTests(unittest.TestCase):
    def test_json_fence_and_source_are_accepted(self):
        cfg = configured()
        parsed = schedule.validate_model_response(
            "```json\n" + answer(cfg) + "\n```",
            cfg.schedule,
            schedule.local_now(cfg.schedule, NOW).date(),
        )
        self.assertEqual(parsed[0]["activity"], "MODEL_CREATED_ACTIVITY")
        self.assertEqual(parsed[0]["source"], "llm")

    def test_invalid_json_prose_tools_partial_day_and_unknown_keys_rejected(self):
        cfg = configured()
        valid = json.loads(answer(cfg))
        invalid = [
            answer(cfg) + " explanation",
            "Some text " + answer(cfg),
            "{broken",
            "x" * 65537,
            json.dumps({**valid, "tool_calls": []}),
            json.dumps({**valid, "date": "2000-01-01"}),
            json.dumps({**valid, "timezone": "UTC"}),
            json.dumps({**valid, "slots": [dict(model_slots()[0], start="01:00")]}),
            json.dumps({**valid, "slots": [dict(model_slots()[0], extra="not allowed")]}),
        ]
        for value in invalid:
            with self.subTest(value=value[:60]), self.assertRaises(schedule.ScheduleError):
                schedule.validate_model_response(
                    value, cfg.schedule, schedule.local_now(cfg.schedule, NOW).date()
                )

    def test_fixed_anchor_is_programmatically_protected(self):
        cfg = configured(template_lines=["10:00-11:00 | FIXED_ACTIVITY | FIXED_LOCATION"])
        with self.assertRaisesRegex(schedule.ScheduleError, "model_fixed_anchor_changed"):
            schedule.validate_model_response(
                answer(cfg), cfg.schedule, schedule.local_now(cfg.schedule, NOW).date()
            )
        slots = [
            {"start": "00:00", "end": "10:00", "activity": "MODEL_A", "location": "X", "notes": ""},
            {
                "start": "10:00",
                "end": "11:00",
                "activity": "FIXED_ACTIVITY",
                "location": "FIXED_LOCATION",
                "notes": "",
            },
            {"start": "11:00", "end": "24:00", "activity": "MODEL_B", "location": "Y", "notes": ""},
        ]
        parsed = schedule.validate_model_response(
            answer(cfg, slots=slots), cfg.schedule, schedule.local_now(cfg.schedule, NOW).date()
        )
        self.assertEqual(parsed[1]["activity"], "FIXED_ACTIVITY")

    def test_prompt_contains_persona_but_not_relationship_secrets_or_old_state(self):
        cfg = settings_module.Settings.parse(
            valid_config(
                profile={"occupation": "ARCHIVIST"},
                background={
                    "life_context": "NEW_PROJECT",
                    "secrets": ["PRIVATE_SECRET"],
                    "current_situation": "OLD_STATE",
                },
                personality={"desires": ["LEARN_PAINTING"], "values": ["CAREFUL"]},
                relationship={
                    "role": "PRIVATE_RELATION",
                    "target_session": "qq-main:FriendMessage:10001",
                    "target_bot_id": "20001",
                    "shared_history": ["PRIVATE_USER_HISTORY"],
                },
            )
        )
        prompt = planner_module.planning_prompt(cfg, schedule.local_now(cfg.schedule, NOW).date())
        for text in ("ARCHIVIST", "NEW_PROJECT", "LEARN_PAINTING", "CAREFUL", "00:00", "24:00"):
            self.assertIn(text, prompt)
        for text in (
            "PRIVATE_SECRET",
            "OLD_STATE",
            "PRIVATE_RELATION",
            "PRIVATE_USER_HISTORY",
            "10001",
            "20001",
        ):
            self.assertNotIn(text, prompt)


class PlannerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = schedule.ScheduleStore(Path(self.temp.name) / "daily")
        self.now = NOW
        self.cfg = configured()
        self.live = self.cfg
        self.calls = []

        async def generate(provider, prompt, system, timeout):
            self.calls.append((provider, prompt, system, timeout))
            return answer(self.cfg, self.now), "resolved-model"

        self.generate = generate
        self.planner = planner_module.SchedulePlanner(
            self.store, generate, clock=lambda: self.now, current_settings=lambda: self.live
        )
        self.addAsyncCleanup(self.planner.cancel)

    async def test_singleflight_once_per_day_and_model_metadata(self):
        self.assertEqual(self.planner.start(self.cfg)["reason"], "generating")
        task = self.planner.task
        self.planner.start(self.cfg)
        self.assertIs(self.planner.task, task)
        await task
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.planner.start(self.cfg)["reason"], "enabled")
        self.assertEqual(len(self.calls), 1)
        plan = self.store.load()
        self.assertEqual(plan["generation_mode"], "llm")
        self.assertEqual(plan["provider_id"], "resolved-model")
        self.assertEqual(plan["source"], "llm")
        self.assertTrue(all(slot["source"] == "llm" for slot in plan["slots"]))
        self.assertEqual(plan["slots"][0]["activity"], "MODEL_CREATED_ACTIVITY")

    async def test_failed_cooldown_survives_reload_and_force(self):
        async def broken(*args):
            self.calls.append(args)
            raise RuntimeError("PRIVATE_PROVIDER_DETAIL")

        self.planner.generate = broken
        self.planner.start(self.cfg)
        await self.planner.task
        self.assertFalse(self.store.path.exists())
        self.assertEqual(self.planner.status(self.cfg)["last_error"], "provider_request_failed")
        self.assertNotIn("PRIVATE_PROVIDER_DETAIL", self.store.status_path.read_text())
        replacement = planner_module.SchedulePlanner(self.store, broken, clock=lambda: self.now)
        self.assertEqual(replacement.start(self.cfg, force=True)["reason"], "cooldown")
        self.assertEqual(len(self.calls), 1)
        self.now += timedelta(seconds=self.cfg.schedule.retry_cooldown + 1)
        replacement.start(self.cfg)
        await replacement.task
        self.assertEqual(len(self.calls), 2)

    async def test_three_failures_stop_auto_generation_even_after_reload(self):
        async def failing(*args):
            self.calls.append(args)
            raise RuntimeError("PRIVATE")

        self.planner.generate = failing
        for _ in range(3):
            self.planner.start(self.cfg)
            await self.planner.task
            self.now += timedelta(seconds=self.cfg.schedule.retry_cooldown + 1)
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(self.planner.start(self.cfg)["reason"], "daily_limit")
        self.assertEqual(self.planner.status(self.cfg)["attempt_count"], 3)
        reloaded = planner_module.SchedulePlanner(self.store, failing, clock=lambda: self.now)
        self.assertEqual(reloaded.start(self.cfg)["reason"], "daily_limit")
        self.assertIsNone(reloaded.task)
        self.assertEqual(reloaded.start(self.cfg, force=True)["reason"], "generating")
        await reloaded.task
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(reloaded.status(self.cfg)["reason"], "daily_limit")

    async def test_missing_provider_is_explicit_and_no_rule_fallback(self):
        async def missing(*args):
            raise schedule.ScheduleError("provider_missing")

        self.planner.generate = missing
        self.planner.start(self.cfg)
        await self.planner.task
        self.assertEqual(self.planner.status(self.cfg)["reason"], "provider_missing")
        self.assertFalse(self.store.path.exists())
        self.assertIsNone(
            self.store.current_slot(
                self.cfg.schedule, self.now, owner=schedule.owner_identity(self.cfg)
            )
        )

    async def test_malformed_response_never_commits(self):
        async def malformed(*args):
            return "not JSON", "resolved-model"

        self.planner.generate = malformed
        self.planner.start(self.cfg)
        await self.planner.task
        self.assertEqual(self.planner.status(self.cfg)["last_error"], "invalid_model_json")
        self.assertFalse(self.store.path.exists())

    async def test_timeout_leaves_no_substitute_plan(self):
        async def slow(*args):
            await asyncio.Event().wait()

        tiny = replace(self.cfg, schedule=replace(self.cfg.schedule, model_timeout=0.01))
        self.live = tiny
        self.planner.generate = slow
        self.planner.start(tiny)
        await self.planner.task
        self.assertEqual(self.planner.status(tiny)["last_error"], "model_timeout")
        self.assertFalse(self.store.path.exists())

    async def test_cancel_cancels_provider_and_does_not_retry(self):
        entered = asyncio.Event()
        cancelled = asyncio.Event()

        async def pending(*args):
            self.calls.append(args)
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        self.planner.generate = pending
        self.planner.start(self.cfg)
        await entered.wait()
        await self.planner.cancel()
        self.assertTrue(cancelled.is_set())
        self.assertIsNone(self.planner.task)
        self.assertFalse(self.store.path.exists())
        self.assertEqual(self.planner.start(self.cfg)["reason"], "cooldown")
        self.assertEqual(len(self.calls), 1)

    async def test_revision_race_preserves_manual_edit(self):
        entered = asyncio.Event()
        release = asyncio.Event()

        async def delayed(*args):
            entered.set()
            await release.wait()
            return answer(self.cfg, self.now), "resolved-model"

        self.planner.generate = delayed
        self.planner.start(self.cfg)
        await entered.wait()
        manual = self.store.update_slots(
            self.cfg.schedule,
            model_slots("MANUAL_DURING_REQUEST"),
            schedule.local_now(self.cfg.schedule, self.now).date(),
            owner=schedule.owner_identity(self.cfg),
        )
        release.set()
        await self.planner.task
        self.assertEqual(self.store.load(), manual)
        self.assertEqual(self.planner.status(self.cfg)["last_error"], "revision_conflict")

    async def test_midnight_result_is_discarded(self):
        entered = asyncio.Event()
        release = asyncio.Event()
        response = answer(self.cfg, self.now)

        async def delayed(*args):
            entered.set()
            await release.wait()
            return response, "resolved-model"

        self.planner.generate = delayed
        self.planner.start(self.cfg)
        await entered.wait()
        self.now += timedelta(days=1)
        release.set()
        await self.planner.task
        self.assertFalse(self.store.path.exists())
        self.assertEqual(
            self.store.load_generation_status()["last_error"], "generation_date_changed"
        )

    async def test_configuration_change_during_request_is_discarded(self):
        entered = asyncio.Event()
        release = asyncio.Event()

        async def delayed(*args):
            entered.set()
            await release.wait()
            return answer(self.cfg, self.now), "resolved-model"

        self.planner.generate = delayed
        self.planner.start(self.cfg)
        await entered.wait()
        self.live = replace(self.cfg, schedule=replace(self.cfg.schedule, work_location="CHANGED"))
        release.set()
        await self.planner.task
        self.assertFalse(self.store.path.exists())
        self.assertEqual(
            self.store.load_generation_status()["last_error"], "generation_settings_changed"
        )

    async def test_force_regeneration_is_paid_request_throttled(self):
        self.planner.start(self.cfg)
        await self.planner.task
        old = self.store.load()
        self.assertEqual(
            self.planner.start(self.cfg, force=True, revision=old["revision"])["reason"], "cooldown"
        )
        self.assertEqual(len(self.calls), 1)
        self.now += timedelta(seconds=61)
        self.planner.start(self.cfg, force=True, revision=old["revision"])
        await self.planner.task
        self.assertEqual(len(self.calls), 2)

    async def test_failed_regeneration_preserves_a_valid_existing_day(self):
        self.planner.start(self.cfg)
        await self.planner.task
        old = self.store.load()
        self.now += timedelta(seconds=61)

        async def broken(*args):
            raise OSError("private")

        self.planner.generate = broken
        self.planner.start(self.cfg, force=True, revision=old["revision"])
        await self.planner.task
        self.assertEqual(self.store.load(), old)
        status = self.planner.status(self.cfg)
        self.assertEqual(status["reason"], "enabled")
        self.assertTrue(status["last_error"])

    async def test_stale_revision_raises_before_request(self):
        with self.assertRaisesRegex(schedule.ScheduleError, "revision_conflict"):
            self.planner.start(self.cfg, force=True, revision="wrong")
        self.assertIsNone(self.planner.task)
        self.assertFalse(self.calls)

    async def test_manual_plan_needs_confirmation_and_never_autoreplaced(self):
        manual = self.store.update_slots(
            self.cfg.schedule,
            model_slots("KEEP_MANUAL"),
            schedule.local_now(self.cfg.schedule, self.now).date(),
            owner=schedule.owner_identity(self.cfg),
        )
        self.assertEqual(self.planner.start(self.cfg)["reason"], "enabled")
        with self.assertRaisesRegex(
            schedule.ScheduleError, "manual_schedule_requires_confirmation"
        ):
            self.planner.start(self.cfg, force=True, revision=manual["revision"])
        self.assertFalse(self.calls)

    async def test_disabled_initialization_has_no_io(self):
        disabled = configured(enabled=False)
        self.assertEqual(self.planner.start(disabled)["reason"], "disabled")
        self.assertEqual(self.planner.status(disabled)["reason"], "disabled")
        self.assertFalse(self.store.root.exists())

    async def test_binary_generation_status_fails_closed_without_provider_call(self):
        self.store.root.mkdir()
        self.store.status_path.write_bytes(b"\xff\xfe\x00")
        self.assertEqual(
            self.planner.status(self.cfg)["last_error"], "schedule_storage_unavailable"
        )
        with self.assertRaises(schedule.ScheduleError):
            self.planner.start(self.cfg)
        self.assertFalse(self.calls)
        self.assertFalse(self.store.path.exists())

    async def test_naive_disk_retry_timestamp_fails_closed(self):
        key = self.planner._key(self.cfg)
        self.store.save_generation_status(
            {"date": key[0], "fingerprint": key[1], "next_retry_at": "2026-11-17T12:00:00"}
        )
        self.assertEqual(
            self.planner.status(self.cfg)["last_error"], "schedule_storage_unavailable"
        )
        with self.assertRaises(schedule.ScheduleError):
            self.planner.start(self.cfg)
        self.assertFalse(self.calls)


if __name__ == "__main__":
    unittest.main()
