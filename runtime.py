"""Small runtime with bounded, content-free per-session diagnostics."""

from collections import OrderedDict
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .personality import (
    PromptError,
    Scope,
    build_persona,
    build_relationship,
    scope_reason,
    strip_owned_blocks,
)
from .settings import ConfigError, Settings

VERSION = "0.2.1"
DIAGNOSTIC_CAPACITY = 128


@dataclass(frozen=True)
class Outcome:
    prompt: Any
    reason: str


class Runtime:
    """One immutable configuration snapshot per plugin load; no model calls."""

    def __init__(self, config: Mapping[str, Any]):
        self.settings: Settings | None = None
        self.config_error = ""
        self._persona = ""
        self._records: OrderedDict[tuple[str, str, str], str] = OrderedDict()
        try:
            snapshot = deepcopy(dict(config))
            self.settings = Settings.parse(snapshot)
            self._persona = build_persona(self.settings)
        except ConfigError as error:
            self.config_error = str(error)
        except Exception:
            # No raw configuration or exception message is retained.
            self.settings = None
            self.config_error = "config: snapshot_failed"

    def record(self, scope: Scope, reason: str) -> None:
        key = scope.diagnostic_key
        self._records[key] = reason
        self._records.move_to_end(key)
        while len(self._records) > DIAGNOSTIC_CAPACITY:
            self._records.popitem(last=False)

    def apply(self, prompt: Any, scope: Scope) -> Outcome:
        if not isinstance(prompt, str):
            reason = "unsupported_system_prompt"
            updated = prompt
        else:
            try:
                original = strip_owned_blocks(prompt)
            except PromptError:
                reason = "malformed_owned_block"
                updated = prompt
            else:
                if self.settings is None:
                    reason = "invalid_config"
                    updated = original
                else:
                    reason = scope_reason(self.settings, scope)
                    updated = original
                    if reason == "applied":
                        updated += self._persona + build_relationship(self.settings, scope)
        self.record(scope, reason)
        return Outcome(updated, reason)

    def status(self, scope: Scope) -> str:
        settings = self.settings
        source = settings.persona_source if settings else "不可用"
        enabled = "是" if settings and settings.enabled else "否"
        valid = "有效" if settings else "无效"
        current = scope_reason(settings, scope) if settings else "invalid_config"
        previous = self._records.get(scope.diagnostic_key, "not_observed")
        lines = [
            f"人格模块 {VERSION}",
            f"已启用：{enabled}",
            f"人格来源：{source}",
            f"配置：{valid}",
            f"当前会话判定：{current}",
            f"最近请求结果：{previous}",
        ]
        if self.config_error:
            lines.append(f"配置字段错误：{self.config_error}")
        if source == "astrbot":
            lines.append("插件中的角色身份资料未使用，沿用 AstrBot 人格。")
        lines.append("以上仅表示规则注入状态，不代表模型遵从或消息送达。")
        return "\n".join(lines)

    def clear(self) -> None:
        self._records.clear()
