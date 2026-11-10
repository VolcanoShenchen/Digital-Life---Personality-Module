"""Core behavior tests without AstrBot, a model provider, or a QQ connection."""

import unittest
from dataclasses import FrozenInstanceError, replace

from tests.support import load_plugin_module, valid_config

settings = load_plugin_module("settings")
personality = load_plugin_module("personality")
runtime = load_plugin_module("runtime")

SESSION = "qq-main:FriendMessage:10001"
BOT_ID = "20001"


def private_scope(**changes):
    scope = personality.Scope(
        origin=SESSION,
        platform_id="qq-main",
        bot_id=BOT_ID,
        platform_type="aiocqhttp",
        private=True,
    )
    return replace(scope, **changes)


def relationship_config():
    return valid_config(
        relationship={
            "target_session": SESSION,
            "target_bot_id": BOT_ID,
            "background": "PRIVATE_RELATIONSHIP_BACKGROUND",
            "addressing": "PRIVATE_RELATIONSHIP_ADDRESS",
        }
    )


class ConfigurationTests(unittest.TestCase):
    def test_disabled_defaults_allow_an_unconfigured_character(self):
        config = settings.Settings.parse({})
        self.assertFalse(config.enabled)
        self.assertFalse(config.allowed_sessions)
        self.assertFalse(config.allowed_bot_ids)
        self.assertEqual(config.character.name, "")
        result = runtime.Runtime({}).apply("host rules", private_scope())
        self.assertEqual((result.prompt, result.reason), ("host rules", "disabled"))

    def test_enabled_plugin_requires_each_identity_field(self):
        for field in ("name", "identity", "personality"):
            with self.subTest(field=field):
                config = valid_config()
                config["character"][field] = " \n\t "
                with self.assertRaises(settings.ConfigError) as caught:
                    settings.Settings.parse(config)
                self.assertEqual(caught.exception.field, "character." + field)
                self.assertEqual(caught.exception.code, "required")

    def test_types_are_strict_and_error_messages_do_not_echo_values(self):
        cases = [
            ("enabled", "SECRET_TRUE", "enabled"),
            ("allowed_sessions", "SECRET_SESSION", "allowed_sessions"),
            ("allowed_bot_ids", "SECRET_BOT", "allowed_bot_ids"),
            ("allowed_sessions", [10001], "allowed_sessions"),
            ("allowed_bot_ids", [True], "allowed_bot_ids"),
            ("allowed_sessions", [" "], "allowed_sessions"),
            ("character", "SECRET_CHARACTER", "character"),
            ("expression", [], "expression"),
            ("relationship", None, "relationship"),
            ("examples", {"SECRET_EXAMPLE": True}, "examples"),
        ]
        for key, value, field in cases:
            with self.subTest(key=key, value=value):
                with self.assertRaises(settings.ConfigError) as caught:
                    settings.Settings.parse(valid_config(**{key: value}))
                self.assertEqual(caught.exception.field, field)
                self.assertNotIn("SECRET", str(caught.exception))
        with self.assertRaises(settings.ConfigError):
            settings.Settings.parse([])

    def test_enum_and_nested_boolean_values_are_not_coerced(self):
        for key in ("tone", "length", "actions", "emoji"):
            for value in (None, [], True, "UNKNOWN_SECRET"):
                with self.subTest(key=key, value=value):
                    with self.assertRaises(settings.ConfigError) as caught:
                        settings.Settings.parse(valid_config(expression={key: value}))
                    self.assertEqual(caught.exception.field, "expression." + key)
                    self.assertNotIn("UNKNOWN_SECRET", str(caught.exception))
        for source in ("Plugin", "", 1):
            with self.subTest(source=source), self.assertRaises(settings.ConfigError):
                settings.Settings.parse(valid_config(persona_source=source))
        with self.assertRaises(settings.ConfigError):
            settings.Settings.parse(valid_config(expression={"reduce_cliches": "false"}))
        with self.assertRaises(settings.ConfigError):
            settings.Settings.parse(valid_config(character={"name": 123}))

    def test_identifiers_and_text_are_normalized_into_immutable_values(self):
        config = valid_config(
            allowed_sessions=[SESSION, " " + SESSION + " "],
            allowed_bot_ids=[BOT_ID, " " + BOT_ID + " "],
            examples=" \n示例内容\t ",
        )
        parsed = settings.Settings.parse(config)
        self.assertEqual(parsed.allowed_sessions, frozenset({SESSION}))
        self.assertEqual(parsed.allowed_bot_ids, frozenset({BOT_ID}))
        self.assertEqual(parsed.examples, "示例内容")
        with self.assertRaises(FrozenInstanceError):
            parsed.enabled = False
        with self.assertRaises(FrozenInstanceError):
            parsed.character.name = "changed"

    def test_budget_accepts_exactly_12000_unicode_characters(self):
        config = valid_config(persona_source="astrbot", character={}, examples="界" * 12000)
        parsed = settings.Settings.parse(config)
        self.assertEqual(len(parsed.examples), 12000)
        config["expression"] = {"extra": "多"}
        with self.assertRaises(settings.ConfigError) as caught:
            settings.Settings.parse(config)
        self.assertEqual(caught.exception.field, "text_budget")

    def test_budget_counts_relationship_and_expression_together(self):
        config = relationship_config()
        config["persona_source"] = "astrbot"
        config["character"] = {}
        config["relationship"]["background"] = "关" * 6000
        config["relationship"]["addressing"] = "系" * 5999
        config["expression"] = {"habits": "语", "extra": "气"}
        with self.assertRaises(settings.ConfigError) as caught:
            settings.Settings.parse(config)
        self.assertEqual(caught.exception.field, "text_budget")

    def test_relationship_requires_allowed_session_and_robot(self):
        for field, value in (
            ("target_session", ""),
            ("target_session", "other:FriendMessage:9"),
            ("target_bot_id", ""),
            ("target_bot_id", "99999"),
        ):
            with self.subTest(field=field, value=value):
                config = relationship_config()
                config["relationship"][field] = value
                with self.assertRaises(settings.ConfigError) as caught:
                    settings.Settings.parse(config)
                self.assertEqual(caught.exception.field, "relationship." + field)

    def test_astrbot_mode_does_not_inject_saved_character(self):
        config = valid_config(persona_source="astrbot")
        config["character"] = {
            "name": "UNUSED_CHARACTER_NAME",
            "identity": "UNUSED_CHARACTER_IDENTITY",
            "personality": "UNUSED_CHARACTER_PERSONALITY",
            "boundaries": "UNUSED_CHARACTER_BOUNDARIES",
        }
        rules = personality.build_persona(settings.Settings.parse(config))
        self.assertNotIn("UNUSED_CHARACTER", rules)
        empty = settings.Settings.parse(valid_config(persona_source="astrbot", character={}))
        self.assertEqual(empty.persona_source, "astrbot")


class ScopeTests(unittest.TestCase):
    def test_exact_private_session_and_robot_are_required(self):
        parsed = settings.Settings.parse(valid_config())
        self.assertEqual(personality.scope_reason(parsed, private_scope()), "applied")
        self.assertEqual(
            personality.scope_reason(parsed, private_scope(origin=SESSION + "0")),
            "session_not_allowed",
        )
        self.assertEqual(
            personality.scope_reason(parsed, private_scope(bot_id="20002")),
            "bot_not_allowed",
        )

    def test_empty_allowlists_match_nothing(self):
        for key, reason in (
            ("allowed_sessions", "no_allowed_sessions"),
            ("allowed_bot_ids", "no_allowed_bots"),
        ):
            with self.subTest(key=key):
                parsed = settings.Settings.parse(valid_config(**{key: []}))
                self.assertEqual(personality.scope_reason(parsed, private_scope()), reason)

    def test_group_and_unsupported_platforms_do_not_receive_rules(self):
        parsed = settings.Settings.parse(valid_config())
        for scope, reason in (
            (private_scope(private=False), "not_private"),
            (private_scope(platform_type="telegram"), "unsupported_platform"),
        ):
            with self.subTest(reason=reason):
                self.assertEqual(personality.scope_reason(parsed, scope), reason)
                result = runtime.Runtime(valid_config()).apply("HOST", scope)
                self.assertEqual((result.prompt, result.reason), ("HOST", reason))

    def test_missing_scope_identity_is_not_accepted(self):
        parsed = settings.Settings.parse(valid_config())
        for key in ("origin", "platform_id", "bot_id"):
            with self.subTest(key=key):
                self.assertEqual(
                    personality.scope_reason(parsed, private_scope(**{key: ""})),
                    "missing_scope_identity",
                )

    def test_relationship_requires_both_session_and_robot_match(self):
        parsed = settings.Settings.parse(relationship_config())
        matching = personality.build_relationship(parsed, private_scope())
        self.assertIn("PRIVATE_RELATIONSHIP_BACKGROUND", matching)
        self.assertIn("PRIVATE_RELATIONSHIP_ADDRESS", matching)
        for scope in (
            private_scope(origin="qq-main:FriendMessage:10002"),
            private_scope(bot_id="20002"),
        ):
            with self.subTest(scope=scope):
                self.assertEqual(personality.build_relationship(parsed, scope), "")


class PromptTests(unittest.TestCase):
    def test_round_trip_preserves_host_text_and_unrelated_markers(self):
        rules = personality.build_persona(settings.Settings.parse(valid_config()))
        for original in (
            "",
            "HOST\n\n",
            "<!-- another-plugin:begin -->\n工具说明\n<!-- end -->",
            "  ",
        ):
            with self.subTest(original=original):
                self.assertEqual(personality.strip_owned_blocks(original + rules), original)

    def test_retry_is_idempotent_with_persona_and_relationship(self):
        engine = runtime.Runtime(relationship_config())
        first = engine.apply("HOST", private_scope())
        retried = engine.apply(first.prompt, private_scope())
        self.assertEqual(first.reason, "applied")
        self.assertEqual(retried, first)
        self.assertEqual(personality.strip_owned_blocks(retried.prompt), "HOST")

    def test_reloading_rules_replaces_old_content_and_keeps_foreign_suffix(self):
        config = valid_config(examples="OLD_EXAMPLE_SENTINEL")
        first = runtime.Runtime(config).apply("HOST", private_scope())
        original = first.prompt + "\nFOREIGN_PLUGIN_SUFFIX"
        config["examples"] = "NEW_EXAMPLE_SENTINEL"
        changed = runtime.Runtime(config).apply(original, private_scope())
        self.assertNotIn("OLD_EXAMPLE_SENTINEL", changed.prompt)
        self.assertIn("NEW_EXAMPLE_SENTINEL", changed.prompt)
        self.assertEqual(
            personality.strip_owned_blocks(changed.prompt), "HOST\nFOREIGN_PLUGIN_SUFFIX"
        )

    def test_disabled_invalid_and_excluded_requests_remove_only_owned_rules(self):
        injected = runtime.Runtime(relationship_config()).apply("HOST", private_scope()).prompt
        cases = (
            (runtime.Runtime({}), private_scope(), "disabled"),
            (runtime.Runtime(valid_config(character={})), private_scope(), "invalid_config"),
            (runtime.Runtime(valid_config()), private_scope(bot_id="20002"), "bot_not_allowed"),
        )
        for engine, scope, reason in cases:
            with self.subTest(reason=reason):
                result = engine.apply(injected, scope)
                self.assertEqual((result.prompt, result.reason), ("HOST", reason))

    def test_incomplete_or_unknown_owned_blocks_are_preserved(self):
        fragments = (
            "\n\n<!-- dlp-personality:persona:v1:begin -->\nunfinished",
            "text <!-- dlp-personality:relationship:v1:end --> trailing",
            "<!-- dlp-personality:persona:v99:begin -->future block",
        )
        engine = runtime.Runtime(valid_config())
        for fragment in fragments:
            with self.subTest(fragment=fragment):
                prompt = "HOST\n" + fragment + "\nFOREIGN_CONTENT"
                with self.assertRaises(personality.PromptError):
                    personality.strip_owned_blocks(prompt)
                result = engine.apply(prompt, private_scope())
                self.assertEqual((result.prompt, result.reason), (prompt, "malformed_owned_block"))

    def test_user_config_cannot_create_owned_protocol_markers(self):
        marker = "<!-- dlp-personality:persona:v1:end -->"
        config = relationship_config()
        config["examples"] = "示例 " + marker
        config["relationship"]["background"] += marker
        engine = runtime.Runtime(config)
        result = engine.apply("HOST", private_scope())
        self.assertEqual(result.reason, "applied")
        self.assertEqual(personality.strip_owned_blocks(result.prompt), "HOST")
        self.assertEqual(engine.apply(result.prompt, private_scope()), result)

    def test_relationship_is_not_in_the_shared_persona(self):
        config = relationship_config()
        config["allowed_sessions"].append("qq-main:FriendMessage:10002")
        parsed = settings.Settings.parse(config)
        self.assertNotIn("PRIVATE_RELATIONSHIP", personality.build_persona(parsed))
        other = runtime.Runtime(config).apply(
            "HOST", private_scope(origin="qq-main:FriendMessage:10002")
        )
        self.assertEqual(other.reason, "applied")
        self.assertNotIn("PRIVATE_RELATIONSHIP", other.prompt)


class RuntimeTests(unittest.TestCase):
    def test_loading_takes_a_deep_immutable_configuration_snapshot(self):
        config = relationship_config()
        config["expression"] = {"habits": "ORIGINAL_HABIT"}
        engine = runtime.Runtime(config)
        before = engine.apply("HOST", private_scope())
        config["enabled"] = False
        config["allowed_sessions"].clear()
        config["allowed_bot_ids"].clear()
        config["character"]["name"] = "MUTATED_NAME"
        config["relationship"]["background"] = "MUTATED_RELATIONSHIP"
        config["expression"]["habits"] = "MUTATED_HABIT"
        self.assertEqual(engine.apply("HOST", private_scope()), before)
        self.assertNotIn("MUTATED", before.prompt)

    def test_invalid_config_diagnostics_do_not_retain_raw_values(self):
        config = valid_config(examples="SECRET_EXAMPLES")
        config["character"]["identity"] = "SECRET_IDENTITY"
        config["expression"] = {"tone": "SECRET_INVALID_TONE"}
        engine = runtime.Runtime(config)
        self.assertIsNone(engine.settings)
        status = engine.status(private_scope())
        self.assertIn("expression.tone", status)
        self.assertNotIn("SECRET", status)
        self.assertNotIn("SECRET", engine.config_error)
        result = engine.apply("SECRET_HOST_PROMPT", private_scope())
        self.assertEqual(result.reason, "invalid_config")
        self.assertNotIn("SECRET", engine.status(private_scope()))
        self.assertNotIn("SECRET", repr(engine.__dict__))

    def test_snapshot_failure_does_not_store_exception_details(self):
        class Uncopyable:
            def __deepcopy__(self, memo):
                raise RuntimeError("SECRET_SNAPSHOT_FAILURE")

        config = valid_config()
        config["unexpected"] = Uncopyable()
        engine = runtime.Runtime(config)
        self.assertIsNone(engine.settings)
        self.assertEqual(engine.config_error, "config: snapshot_failed")
        self.assertNotIn("SECRET", repr(engine.__dict__))
        self.assertNotIn("SECRET", engine.status(private_scope()))

    def test_non_string_prompts_are_preserved_by_identity(self):
        engine = runtime.Runtime(valid_config())
        for prompt in (None, [], {"SECRET_CONTENT": "value"}, 123):
            with self.subTest(prompt=prompt):
                result = engine.apply(prompt, private_scope())
                self.assertIs(result.prompt, prompt)
                self.assertEqual(result.reason, "unsupported_system_prompt")
                self.assertIn("unsupported_system_prompt", engine.status(private_scope()))
                self.assertNotIn("SECRET_CONTENT", engine.status(private_scope()))

    def test_diagnostics_are_isolated_by_platform_robot_and_session(self):
        engine = runtime.Runtime(valid_config())
        original = private_scope()
        engine.apply("HOST", original)
        self.assertIn("最近请求结果：applied", engine.status(original))
        for scope in (
            private_scope(platform_id="other-instance"),
            private_scope(bot_id="20002"),
            private_scope(origin="qq-main:FriendMessage:10002"),
        ):
            with self.subTest(scope=scope):
                self.assertIn("最近请求结果：not_observed", engine.status(scope))
        engine.apply(None, private_scope(bot_id="20002"))
        self.assertIn("最近请求结果：applied", engine.status(original))
        self.assertNotIn("unsupported_system_prompt", engine.status(original))

    def test_diagnostic_capacity_evicts_the_least_recently_recorded_session(self):
        engine = runtime.Runtime(valid_config())
        scopes = [private_scope(origin=f"qq-main:FriendMessage:{index}") for index in range(129)]
        self.assertEqual(runtime.DIAGNOSTIC_CAPACITY, 128)
        for scope in scopes[:128]:
            engine.apply("HOST", scope)
        engine.apply("HOST", scopes[0])
        engine.apply("HOST", scopes[128])
        self.assertNotIn("最近请求结果：not_observed", engine.status(scopes[0]))
        self.assertIn("最近请求结果：not_observed", engine.status(scopes[1]))
        self.assertNotIn("最近请求结果：not_observed", engine.status(scopes[128]))

    def test_status_is_content_free_and_clear_resets_observations(self):
        config = relationship_config()
        config["examples"] = "SECRET_EXAMPLES"
        config["character"]["identity"] = "SECRET_IDENTITY"
        engine = runtime.Runtime(config)
        engine.apply("SECRET_USER_HISTORY", private_scope())
        status = engine.status(private_scope())
        for secret in ("SECRET", "PRIVATE_RELATIONSHIP", SESSION, BOT_ID):
            self.assertNotIn(secret, status)
        self.assertIn("不代表模型遵从或消息送达", status)
        engine.clear()
        self.assertIn("最近请求结果：not_observed", engine.status(private_scope()))
        self.assertEqual(engine.apply("HOST", private_scope()).reason, "applied")


if __name__ == "__main__":
    unittest.main()
