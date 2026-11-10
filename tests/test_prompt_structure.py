"""Regression tests for malformed blocks adjacent to otherwise valid rules."""

import unittest

from tests.support import load_plugin_module, valid_config

personality = load_plugin_module("personality")
runtime = load_plugin_module("runtime")
settings = load_plugin_module("settings")


class PromptStructureTests(unittest.TestCase):
    def setUp(self):
        self.scope = personality.Scope(
            "qq-main:FriendMessage:10001", "qq-main", "20001", "aiocqhttp", True
        )
        self.engine = runtime.Runtime(valid_config())
        self.rules = personality.build_persona(settings.Settings.parse(valid_config()))

    def test_broken_nested_or_crossed_blocks_never_remove_host_text(self):
        start = personality._start
        end = personality._end
        malformed = (
            start("persona") + "unfinished\nFOREIGN_HOST_RULES" + self.rules,
            start("persona") + self.rules + end("persona"),
            start("persona") + start("relationship") + end("relationship") + end("persona"),
            start("persona") + end("relationship"),
            self.rules + start("relationship") + "unfinished",
            self.rules + "<!-- dlp-personality:persona:v99:begin -->",
        )
        for fragment in malformed:
            prompt = "HOST_START" + fragment + "HOST_END"
            with self.subTest(fragment=fragment):
                with self.assertRaises(personality.PromptError):
                    personality.strip_owned_blocks(prompt)
                outcome = self.engine.apply(prompt, self.scope)
                self.assertEqual(outcome.reason, "malformed_owned_block")
                self.assertEqual(outcome.prompt, prompt)

    def test_multiple_valid_blocks_preserve_every_foreign_separator(self):
        prompt = "HOST" + self.rules + "\nFOREIGN_TEXT\n" + self.rules + "TAIL"
        self.assertEqual(personality.strip_owned_blocks(prompt), "HOST\nFOREIGN_TEXT\nTAIL")
        updated = self.engine.apply(prompt, self.scope)
        self.assertEqual(updated.reason, "applied")
        self.assertEqual(personality.strip_owned_blocks(updated.prompt), "HOST\nFOREIGN_TEXT\nTAIL")


if __name__ == "__main__":
    unittest.main()
