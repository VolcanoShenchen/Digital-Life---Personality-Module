"""Time-bounded state, separate from stable persona and conversation history."""

from datetime import UTC, datetime

from .personality import Scope, scope_reason
from .settings import Settings, parse_state_time

STATE_START = "<dlp_current_state_v1>\n"
STATE_END = "\n</dlp_current_state_v1>"


def state_summary(settings: Settings | None, now: datetime | None = None) -> dict:
    """Content-free diagnostics, evaluated against the clock on every call."""
    now = now or datetime.now(UTC)
    if settings is None:
        return {
            "enabled": False,
            "has_content": False,
            "active": False,
            "reason": "invalid_config",
            "updated_at": "",
            "expires_at": "",
            "source": "manual",
            "remaining_seconds": 0,
        }
    state = settings.dynamic_state
    remaining = 0
    if not settings.enabled:
        reason = "plugin_disabled"
    elif not state.enabled:
        reason = "disabled"
    elif not state.has_content:
        reason = "empty"
    elif now < parse_state_time(state.updated_at, "dynamic_state.updated_at"):
        reason = "not_started"
    else:
        ends = parse_state_time(state.expires_at, "dynamic_state.expires_at")
        remaining = max(0, int((ends - now).total_seconds()))
        reason = "active" if now < ends else "expired"
    return {
        "enabled": state.enabled,
        "has_content": state.has_content,
        "active": reason == "active",
        "reason": reason,
        "updated_at": state.updated_at,
        "expires_at": state.expires_at,
        "source": state.source,
        "remaining_seconds": remaining,
    }


def build_state_context(
    settings: Settings | None, scope: Scope, now: datetime | None = None
) -> str:
    """Return transient context only for the explicitly bound private chat."""
    if settings is None or scope_reason(settings, scope) != "applied":
        return ""
    state = settings.dynamic_state
    if state.target_session != scope.origin or state.target_bot_id != scope.bot_id:
        return ""
    summary = state_summary(settings, now)
    if summary["reason"] in {"disabled", "empty", "plugin_disabled"}:
        return ""
    if not summary["active"]:
        # Do not reintroduce expired content. Even assistant claims retained in
        # previous chat rounds are not proof of the current activity.
        return (
            STATE_START + "当前没有已生效且未过期的状态证据。旧活动已失去时效，"
            "这不代表活动已经完成；不要把历史回复或长期背景当作此刻正在做的事。"
            "不要为每次回答不同而编造新活动。只依据当轮明确上下文自然回应。" + STATE_END
        )
    source = "运营者手动设置" if state.source == "manual" else "运营者已确认的事件"
    lines = [
        STATE_START.rstrip("\n"),
        "以下仅为本轮有效的角色状态，不改变稳定身份和工具权限。",
        f"来源：{source}",
        f"更新时间：{state.updated_at}",
        f"有效截止：{state.expires_at}",
    ]
    for title, value in (
        ("当前活动", state.activity),
        ("当前位置", state.location),
        ("当前情绪", state.mood),
        ("当前精力", state.energy),
    ):
        if value:
            escaped = value.replace("<dlp_current_state_v1>", "［状态］").replace(
                "</dlp_current_state_v1>", "［状态结束］"
            )
            lines.append(f"{title}：{escaped}")
    lines.append(
        "只在与本轮话题相关时使用，不逐条播报，不把未填写状态自动补齐。"
        "情绪是此刻状态；静态的‘生气时如何回应’等规则不证明此刻正在生气。"
    )
    return "\n".join(lines) + STATE_END
