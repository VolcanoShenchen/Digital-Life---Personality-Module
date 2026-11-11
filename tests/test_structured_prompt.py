"""Structured fields must reach the prompt as separated, meaningful sections."""

import unittest

from tests.support import load_plugin_module, valid_config

personality = load_plugin_module("personality")
runtime = load_plugin_module("runtime")
settings = load_plugin_module("settings")

SESSION = "qq-main:FriendMessage:10001"


def structured_config(**overrides):
    config = {
        "enabled": True,
        "persona_source": "plugin",
        "allowed_sessions": [SESSION],
        "allowed_bot_ids": ["20001"],
        "profile": {
            "name": "林晓",
            "nickname": "晓",
            "gender_identity": "女性",
            "age": "24",
            "age_mode": "fixed",
            "occupation": "档案管理员",
        },
        "background": {
            "identity": "在旧城区档案馆工作，熟悉城市变迁。",
            "current_situation": "最近在整理一批没有编号的旧照片。",
            "unknown_facts": "不知道用户童年的具体经历。",
        },
        "personality": {
            "core_traits": ["慢热", "好奇", "有判断力"],
            "flaws": ["被催促时容易敷衍"],
            "contradictions": ["想被理解，但不爱主动解释"],
            "social_temperature": "slow",
        },
        "behavior": {
            "when_angry": "回复会变短，语气变直接，但不会辱骂。",
            "when_praised": "先轻轻带过，再补一句具体回应。",
            "when_disagrees": "先指出不同意的部分，再说明理由。",
        },
        "speech": {
            "first_person": "我",
            "vocabulary": "偶尔会用档案和旧照片作比喻。",
            "sentence_length": "short",
            "humor_style": "熟悉后会轻轻吐槽。",
            "question_frequency": "necessary",
        },
        "roleplay": {"action_style": "occasional"},
        "boundaries": {
            "uncomfortable_topics": ["被追问私人住址"],
            "refusal_level": "clear",
        },
    }
    config.update(overrides)
    return config


class StructuredPromptTests(unittest.TestCase):
    def scope(self, origin=SESSION, bot="20001"):
        return personality.Scope(origin, "qq-main", bot, "aiocqhttp", True)

    def test_identity_facts_are_separated_not_one_blob(self):
        rules = personality.build_persona(settings.Settings.parse(structured_config()))
        for expected in ("林晓", "女性", "24", "档案管理员", "慢热", "好奇"):
            self.assertIn(expected, rules)
        self.assertIn("【基础身份资料】", rules)
        self.assertIn("【核心性格】", rules)
        self.assertIn("【情境行为规则】", rules)

    def test_situational_rules_keep_behavior_text(self):
        rules = personality.build_persona(settings.Settings.parse(structured_config()))
        self.assertIn("生气时：回复会变短", rules)
        self.assertIn("被夸奖时：先轻轻带过", rules)
        self.assertIn("意见不同时：先指出不同意的部分", rules)

    def test_legacy_fields_still_produce_a_valid_persona(self):
        rules = personality.build_persona(settings.Settings.parse(valid_config()))
        self.assertIn("测试角色", rules)
        self.assertIn("【性格补充】", rules)
        self.assertIn("【表达习惯】", rules)

    def test_astrbot_source_omits_structured_identity(self):
        config = structured_config(persona_source="astrbot")
        rules = personality.build_persona(settings.Settings.parse(config))
        self.assertNotIn("林晓", rules)
        self.assertNotIn("档案管理员", rules)
        self.assertIn("沿用宿主当前会话人设", rules)

    def test_relationship_uses_structured_fields(self):
        config = structured_config(
            relationship={
                "target_session": SESSION,
                "target_bot_id": "20001",
                "role": "朋友",
                "stage": "熟悉",
                "addressing": "直接叫名字",
                "shared_history": ["一起整理过旧照片"],
                "conflict_style": "先冷静，再解释",
            }
        )
        relation = personality.build_relationship(settings.Settings.parse(config), self.scope())
        for expected in ("朋友", "熟悉", "直接叫名字", "一起整理过旧照片", "先冷静"):
            self.assertIn(expected, relation)

    def test_structured_relationship_does_not_leak_to_other_bot(self):
        config = structured_config(
            relationship={
                "target_session": SESSION,
                "target_bot_id": "20001",
                "role": "朋友",
            }
        )
        parsed = settings.Settings.parse(config)
        self.assertEqual(personality.build_relationship(parsed, self.scope(bot="20002")), "")

    def test_old_config_migrates_into_structured_sections(self):
        parsed = settings.Settings.parse(valid_config())
        self.assertEqual(parsed.profile.name, "测试角色")
        self.assertEqual(parsed.background.identity, "合成测试中的虚构角色。")
        self.assertEqual(parsed.personality.legacy_summary, "表达克制，有自己的判断。")

    def test_structured_config_reaches_runtime_request(self):
        engine = runtime.Runtime(structured_config())
        outcome = engine.apply("HOST", self.scope())
        self.assertEqual(outcome.reason, "applied")
        self.assertIn("林晓", outcome.prompt)
        self.assertIn("HOST", outcome.prompt)


if __name__ == "__main__":
    unittest.main()
