"""Guard the Vue component shape that previously broke the settings view."""

import json
import re
import unittest

from tests.support import ROOT

SOURCE = (ROOT / "frontend/src/main.js").read_text("utf-8")
BUILT_INDEX = (ROOT / "views/settings/index.html").read_text("utf-8")


class WebUISourceTests(unittest.TestCase):
    def test_tab_state_is_not_returned_through_component_this(self):
        # Returning the state object from setup() exposes it through the
        # component proxy, which unwraps refs and breaks active.value.
        self.assertNotIn("return renderApp(this)", SOURCE)
        self.assertIn("return () => renderApp(state)", SOURCE)

    def test_render_function_destructures_every_value_it_uses(self):
        start = SOURCE.index("function renderApp(state) {")
        body = SOURCE[start:]
        destructure = body[: body.index("} = state;")]
        for name in ("config", "summary", "active", "busy", "message", "sections", "save"):
            with self.subTest(name=name):
                self.assertIn(name, destructure)

    def test_view_assets_are_relative_for_iframe_loading(self):
        for attribute in ('src="./assets/', 'href="./assets/'):
            self.assertIn(attribute, BUILT_INDEX)
        self.assertNotIn('src="/assets/', BUILT_INDEX)
        self.assertNotIn('href="/assets/', BUILT_INDEX)

    def test_built_page_references_an_existing_hashed_asset(self):
        assets = re.findall(r'\./assets/([^"]+)', BUILT_INDEX)
        self.assertTrue(assets)
        for name in assets:
            with self.subTest(asset=name):
                self.assertTrue((ROOT / "views/settings/assets" / name).is_file())

    def test_schema_sections_match_frontend_groups(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text("utf-8"))
        groups = set(re.findall(r"^\s{2}(\w+): \[", SOURCE, re.MULTILINE))
        for section in (
            "profile",
            "background",
            "personality",
            "behavior",
            "relationship",
            "speech",
            "response",
            "roleplay",
            "boundaries",
        ):
            with self.subTest(section=section):
                self.assertIn(section, schema)
                self.assertIn(section, groups)


if __name__ == "__main__":
    unittest.main()
