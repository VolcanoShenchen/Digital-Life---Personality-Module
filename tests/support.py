"""Load the plugin independently of its checkout directory name."""

import importlib
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "_dlp_test_plugin"


def load_plugin_module(name: str):
    if PACKAGE not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            PACKAGE, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("Cannot load plugin test package")
        module = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = module
        spec.loader.exec_module(module)
    return importlib.import_module(f"{PACKAGE}.{name}")


def valid_config(**overrides):
    config = {
        "enabled": True,
        "allowed_sessions": ["qq-main:FriendMessage:10001"],
        "allowed_bot_ids": ["20001"],
        "character": {
            "name": "测试角色",
            "identity": "合成测试中的虚构角色。",
            "personality": "表达克制，有自己的判断。",
        },
    }
    config.update(overrides)
    return config
