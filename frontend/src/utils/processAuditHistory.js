/**
 * PACOTE DS — Histórico de auditoria do processo.
 * Classifica eventos, gera descrições e junta history + activities.
 * Espelha `services/history.py` (classify_history_event / build_history_description).
 */

export const AUDIT_EVENT_TYPES = {
  status_change: { label: "Fase" },
  comment: { label: "Nota" },
  document: { label: "Documento" },
  email: { label: "Email" },
  assignment: { label: "Atribuição" },
  task: { label: "Tarefa" },
  portal_upload: { label: "Portal" },
  created: { label: "Criação" },
  edit: { label: "Edição" },
  other: { label: "Outro" },
};

function stringifyValue(value) {
  if (value == null || value === "") return "—";
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

export function classifyAuditEvent(entry) {
  if (!entry || typeof entry !== "object") return "other";
  if (entry.event_type && AUDIT_EVENT_TYPES[entry.event_type]) return entry.event_type;

  const action = String(entry.action || "").toLowerCase();
  const field = String(entry.field || "").toLowerCase();

  if (entry.type === "status_change" || field === "status" || action.includes("status")
      || action.includes("estado") || action.includes("fase") || action.startsWith("moveu processo")) {
    return "status_change";
  }
  if (entry.type === "comment" || entry.comment || action.includes("coment")
      || action.includes("observaç") || action.includes("observac")
      || field === "observation_notes" || field === "observations") {
    return "comment";
  }
  if (entry.action === "DOCUMENT_UPLOADED_BY_CLIENT") return "portal_upload";
  if (entry.type === "document" || action.includes("document") || action.includes("documento")
      || action.includes("upload") || action.includes("carregou")) {
    return "document";
  }
  if (entry.type === "email" || action.includes("email") || action.includes("e-mail")) return "email";
  if (entry.type === "assignment" || action.includes("atribu")) return "assignment";
  if (entry.type === "task" || action.includes("tarefa") || field === "tarefa") return "task";
  if (action.startsWith("criou processo")) return "created";
  if (field) return "edit";
  return "other";
}

export function describeAuditEvent(entry) {
  if (!entry || typeof entry !== "object") return "Ação registada";
  if (entry.description) return String(entry.description);

  const action = String(entry.action || "").trim() || "Atualização";
  const field = entry.field;
  const oldValue = entry.old_value ?? entry.old_status;
  const newValue = entry.new_value ?? entry.new_status;
  const type = classifyAuditEvent(entry);
  const hasOld = oldValue != null && oldValue !== "";
  const hasNew = newValue != null && newValue !== "";

  if (type === "status_change" && (hasOld || hasNew)) {
    return `Fase alterada de ${stringifyValue(oldValue)} para ${stringifyValue(newValue)}`;
  }
  if (hasOld && hasNew) {
    return `${action}: ${field || "valor"} alterado de ${oldValue} para ${newValue}`;
  }
  if (hasNew && !hasOld) {
    return field ? `${action}: ${field} → ${newValue}` : `${action}: ${newValue}`;
  }
  if (hasOld && !hasNew) {
    return `${action}: ${field || "valor"} removido (era ${oldValue})`;
  }
  if (entry.comment) return String(entry.comment);
  return action || "Ação registada";
}

export function resolveProcessId(processLike) {
  if (!processLike || typeof processLike !== "object") return "";
  return String(processLike.id || processLike.process_id || "").trim();
}

export function findProcessBySelectValue(processes, value) {
  const needle = String(value ?? "").trim();
  if (!needle || !Array.isArray(processes)) return null;
  return processes.find((p) => {
    if (!p) return false;
    return String(p.id) === needle
      || String(p.process_id || "") === needle
      || String(p.client_id || "") === needle;
  }) || null;
}

const ISO_SEM_FUSO = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/;

/**
 * O instante de um evento, em milissegundos (`-Infinity` se não se lê).
 *
 * Ordenar por TEXTO (o que se fazia: `localeCompare` sobre a data) só acerta
 * enquanto todas as datas tiverem a mesma forma. Aqui misturam-se `…+00:00`
 * (Python), `…Z` com milissegundos (JavaScript), fusos diferentes e datas sem
 * fuso: dois eventos do mesmo segundo ficavam trocados e um `+01:00` caía
 * fora de ordem. Uma data sem fuso lê-se como UTC (é como o servidor as grava).
 * Datas ilegíveis valem `-Infinity`: vão para o fim, nunca para o topo.
 */
export function instanteDoEvento(valor) {
  if (valor instanceof Date) {
    const t = valor.getTime();
    return Number.isNaN(t) ? -Infinity : t;
  }
  if (typeof valor === "number") {
    if (!Number.isFinite(valor)) return -Infinity;
    return valor < 1e11 ? valor * 1000 : valor; // segundos vs milissegundos
  }
  if (typeof valor !== "string" || !valor.trim()) return -Infinity;
  const texto = valor.trim();
  const t = Date.parse(ISO_SEM_FUSO.test(texto) ? `${texto.replace(" ", "T")}Z` : texto);
  return Number.isNaN(t) ? -Infinity : t;
}

/**
 * A data com que um evento se ORDENA e se MOSTRA. Um só critério: a lista
 * ordenava por `created_at || timestamp` e o ecrã mostrava `timestamp ||
 * created_at` — um evento com as duas aparecia com uma data e estava
 * posicionado pela outra.
 */
export function dataDoEvento(evento) {
  return evento?.created_at || evento?.timestamp || "";
}

/**
 * Junta history + activities, mais recentes primeiro, sem duplicar ids.
 */
export function mergeAuditEvents(history = [], activities = []) {
  const events = [];
  const historyList = Array.isArray(history) ? history : [];
  const activityList = Array.isArray(activities) ? activities : [];
  const historyIds = new Set(historyList.map((h) => h?.id).filter(Boolean));

  historyList.forEach((h) => {
    if (!h || typeof h !== "object") return;
    events.push({
      ...h,
      event_type: classifyAuditEvent(h),
      description: describeAuditEvent(h),
      _sortDate: dataDoEvento(h),
    });
  });

  activityList.forEach((a) => {
    if (!a || typeof a !== "object") return;
    if (a.id && historyIds.has(a.id)) return;
    events.push({
      ...a,
      type: a.type || "comment",
      event_type: classifyAuditEvent({ ...a, type: a.type || "comment" }),
      description: describeAuditEvent({ ...a, type: a.type || "comment" }),
      _sortDate: dataDoEvento(a),
    });
  });

  // Mais recentes primeiro. Empates e datas ilegíveis mantêm a ordem de
  // chegada (a ordenação é estável) — e as ilegíveis ficam no fim.
  const instantes = new Map(events.map((e) => [e, instanteDoEvento(e._sortDate)]));
  events.sort((a, b) => {
    const ia = instantes.get(a);
    const ib = instantes.get(b);
    if (ia === ib) return 0;
    return ib > ia ? 1 : -1;
  });
  return events;
}
