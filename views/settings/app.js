const bridge = window.AstrBotPluginView;
const $ = (id) => document.getElementById(id);

const fields = {
  enabled: $("enabled"),
  persona_source: $("persona_source"),
  allowed_sessions: $("allowed_sessions"),
  allowed_bot_ids: $("allowed_bot_ids"),
  character_name: $("character_name"),
  character_identity: $("character_identity"),
  character_personality: $("character_personality"),
  character_boundaries: $("character_boundaries"),
  relationship_target_session: $("relationship_target_session"),
  relationship_target_bot_id: $("relationship_target_bot_id"),
  relationship_background: $("relationship_background"),
  relationship_addressing: $("relationship_addressing"),
  expression_tone: $("expression_tone"),
  expression_length: $("expression_length"),
  expression_actions: $("expression_actions"),
  expression_emoji: $("expression_emoji"),
  expression_reduce_cliches: $("expression_reduce_cliches"),
  expression_habits: $("expression_habits"),
  expression_extra: $("expression_extra"),
  examples: $("examples"),
};

function lines(value) {
  return Array.isArray(value) ? value.join("\n") : "";
}

function setValue(id, value) {
  const input = fields[id];
  if (!input) return;
  if (input.type === "checkbox") input.checked = Boolean(value);
  else input.value = value ?? "";
}

function getLines(id) {
  return fields[id].value.split(/\r?\n/).map((value) => value.trim()).filter(Boolean);
}

function applyConfig(config = {}) {
  const character = config.character || {};
  const relationship = config.relationship || {};
  const expression = config.expression || {};
  setValue("enabled", config.enabled);
  setValue("persona_source", config.persona_source || "plugin");
  setValue("allowed_sessions", lines(config.allowed_sessions));
  setValue("allowed_bot_ids", lines(config.allowed_bot_ids));
  setValue("character_name", character.name);
  setValue("character_identity", character.identity);
  setValue("character_personality", character.personality);
  setValue("character_boundaries", character.boundaries);
  setValue("relationship_target_session", relationship.target_session);
  setValue("relationship_target_bot_id", relationship.target_bot_id);
  setValue("relationship_background", relationship.background);
  setValue("relationship_addressing", relationship.addressing);
  setValue("expression_tone", expression.tone || "follow_character");
  setValue("expression_length", expression.length || "adaptive");
  setValue("expression_actions", expression.actions || "none");
  setValue("expression_emoji", expression.emoji || "occasional");
  setValue("expression_reduce_cliches", expression.reduce_cliches ?? true);
  setValue("expression_habits", expression.habits);
  setValue("expression_extra", expression.extra);
  setValue("examples", config.examples);
}

function readConfig() {
  return {
    enabled: fields.enabled.checked,
    persona_source: fields.persona_source.value,
    allowed_sessions: getLines("allowed_sessions"),
    allowed_bot_ids: getLines("allowed_bot_ids"),
    character: {
      name: fields.character_name.value.trim(),
      identity: fields.character_identity.value.trim(),
      personality: fields.character_personality.value.trim(),
      boundaries: fields.character_boundaries.value.trim(),
    },
    relationship: {
      target_session: fields.relationship_target_session.value.trim(),
      target_bot_id: fields.relationship_target_bot_id.value.trim(),
      background: fields.relationship_background.value.trim(),
      addressing: fields.relationship_addressing.value.trim(),
    },
    expression: {
      tone: fields.expression_tone.value,
      length: fields.expression_length.value,
      actions: fields.expression_actions.value,
      emoji: fields.expression_emoji.value,
      reduce_cliches: fields.expression_reduce_cliches.checked,
      habits: fields.expression_habits.value.trim(),
      extra: fields.expression_extra.value.trim(),
    },
    examples: fields.examples.value.trim(),
  };
}

function showMessage(text, kind = "ok") {
  const node = $("message");
  node.hidden = !text;
  node.className = `message ${kind}`;
  node.textContent = text;
}

function showSummary(summary = {}) {
  $("summary").innerHTML = `
    <strong>${summary.enabled ? "已启用" : "未启用"}</strong>
    <span>配置：${summary.valid ? "有效" : "无效"}</span>
    <span>版本：${summary.version || "—"}</span>
    ${summary.config_error ? `<span class="error-text">${summary.config_error}</span>` : ""}
  `;
}

async function load() {
  try {
    const context = await bridge.ready();
    const result = await bridge.apiGet("settings");
    applyConfig(result.config);
    showSummary(result.summary);
    if (context?.username) $("save-hint").textContent = `当前面板用户：${context.username}。保存后立即应用。`;
  } catch (error) {
    showMessage(`读取配置失败：${error.message || error}`, "error");
  }
}

$("settings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("save");
  button.disabled = true;
  showMessage("正在保存…");
  try {
    const result = await bridge.apiPost("settings", readConfig());
    applyConfig(result.config);
    showSummary(result.summary);
    showMessage("配置已保存并立即应用到新请求。", "ok");
  } catch (error) {
    showMessage(`保存失败：${error.message || error}`, "error");
  } finally {
    button.disabled = false;
  }
});

load();
