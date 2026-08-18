/**
 * PACOTE DO.1 — Timeline compacta para o Resumo do Processo.
 * Espelha `services/process_timeline.py` (criação + histórico GET /history).
 */

function isCreatedAction(action) {
  return String(action || "").trim().toLowerCase().startsWith("criou processo");
}

function kindForHistoryItem(item) {
  const action = item?.action || "";
  const field = String(item?.field || "").toLowerCase();
  if (isCreatedAction(action)) return "created";
  if (field === "status" || /estado|fase/i.test(action)) return "status";
  return "event";
}

function descriptionForHistoryItem(item) {
  const field = item?.field;
  const oldValue = item?.old_value;
  const newValue = item?.new_value;
  if (!field && oldValue == null && newValue == null) return null;
  const parts = [];
  if (field) parts.push(String(field));
  if (oldValue != null && oldValue !== "" && newValue != null && newValue !== "") {
    parts.push(`${oldValue} → ${newValue}`);
  } else if (newValue != null && newValue !== "") {
    parts.push(String(newValue));
  }
  return parts.length ? parts.join(" · ") : null;
}

/**
 * @param {object|null} process
 * @param {Array} history
 * @param {{ limit?: number }} [options]
 * @returns {Array<{ id, kind, title, description, actor, at }>}
 */
export function buildSummaryTimeline(process, history, options = {}) {
  const limit = Math.max(Number(options.limit) || 40, 1);
  const events = [];
  const list = Array.isArray(history) ? history : [];
  const createdAt = process?.created_at;
  const hasCreated = list.some((h) => isCreatedAction(h?.action));

  if (createdAt && !hasCreated) {
    events.push({
      id: `created-${process?.id || "process"}`,
      kind: "created",
      title: "Processo criado",
      description: null,
      actor: null,
      at: createdAt,
    });
  }

  for (const item of list) {
    events.push({
      id: item.id,
      kind: kindForHistoryItem(item),
      title: item.action || "Atualização",
      description: descriptionForHistoryItem(item),
      actor: item.user_name,
      at: item.created_at,
    });
  }

  events.sort((a, b) => String(b.at || "").localeCompare(String(a.at || "")));
  return events.slice(0, limit);
}

export function resolveProcessObservations(process) {
  if (!process || typeof process !== "object") return "";
  const obs = process.observations;
  if (obs != null && String(obs).length > 0) return String(obs);
  if (process.notes != null) return String(process.notes);
  return "";
}
