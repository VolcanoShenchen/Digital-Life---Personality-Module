"""Enumerations must never leak English codes into the prompt."""

import json
import unittest
from pathlib import Path

from tests.support import ROOT, load_plugin_module

personality = load_plugin_module("personality")
settings = load_plugin_module("settings")

PERSONA = Path(r"E:\LinXiaozhi\Memory\local-test\personas\lin-wan.json")

RAW_CODES = (
    "fixed",
    "growing",
    "timeline",
    "stable",
    "influenced",
    "adaptive",
    "slow",
    "moderate",
    "outgoing",
    "short",
    "medium",
    "long",
    "never",
    "necessary",
    "often",
    "clear",
    "gentle",
    "firm",
    "parentheses",
    "natural",
    "when_requested",
    "relevant",
    "default",
)


class EnumRenderingTests(unittest.TestCase):
    def build(self, **sections):
        config = {
            "enabled": True,
            "persona_source": "plugin",
            "profile": {"name": "测试角色"},
            "background": {"identity": "测试背景"},
            "personality": {"core_traits": ["慢热"]},
            **sections,
        }
        return personality.build_persona(settings.Settings.parse(config))

    def test_default_enum_values_render_as_chinese(self):
        prompt = self.build()
        for code in RAW_CODES:
            with self.subTest(code=code):
                self.assertNotIn(f"：{code}\n", prompt)

    def test_every_dropdown_option_has_a_chinese_label(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text("utf-8"))
        key_to_map = {
            "age_mode": personality._AGE_MODES,
            "changeability": personality._CHANGEABILITY,
            "social_temperature": personality._SOCIAL_TEMPERATURE,
            "sentence_length": personality._SENTENCE_LENGTH,
            "question_frequency": personality._QUESTION_FREQUENCY,
            "offer_advice": personality._ADVICE_POLICY,
            "refusal_level": personality._REFUSAL_LEVEL,
            "action_format": personality._ACTION_FORMAT,
            "environment_detail": personality._ENVIRONMENT_DETAIL,
        }
        found = {}
        for section in schema.values():
            if section.get("type") != "object":
                continue
            for key, field in section["items"].items():
                if field.get("options") and key in key_to_map:
                    found[key] = field["options"]
        self.assertTrue(found, "no mapped enum fields located in schema")
        for key, options in found.items():
            mapping = key_to_map[key]
            for option in options:
                with self.subTest(key=key, option=option):
                    self.assertIn(option, mapping)
                    self.assertTrue(mapping[option].strip())

    @unittest.skipUnless(PERSONA.is_file(), "sample persona not present")
    def test_sample_persona_parses_and_hides_codes(self):
        data = json.loads(PERSONA.read_text("utf-8"))
        prompt = personality.build_persona(settings.Settings.parse(data))
        self.assertIn("林晚", prompt)
        for code in RAW_CODES:
            with self.subTest(code=code):
                self.assertNotIn(f"：{code}\n", prompt)


if __name__ == "__main__":
    unittest.main()
