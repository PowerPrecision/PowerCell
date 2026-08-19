/**
 * PACOTE DO.2 + DQ — Agrupar eventos da Agenda por dia civil.
 * Datas `YYYY-MM-DD` são interpretadas em local time (evita o salto UTC).
 * Pacote DQ: cores por cliente, prefixo do responsável, ausências multi-dia.
 */
import { addDays, startOfWeek } from "date-fns";

export const TEAM_CALENDAR_ROLES = ["admin", "ceo", "diretor"];

export function parseAgendaDate(value) {
  if (!value) return null;
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }
  const raw = String(value);
  const iso = raw.slice(0, 10);
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (match) {
    return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  }
  const d = new Date(raw);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function agendaDateKey(value) {
  const d = value instanceof Date ? value : parseAgendaDate(value);
  if (!d || Number.isNaN(d.getTime())) return "";
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function eventDateKeys(event) {
  const startKey = agendaDateKey(event?.due_date);
  if (!startKey) return [];
  const endKey = agendaDateKey(event?.end_date) || startKey;
  if (endKey <= startKey) return [startKey];
  const keys = [];
  let cursor = parseAgendaDate(startKey);
  const endDate = parseAgendaDate(endKey);
  while (cursor && endDate && cursor <= endDate) {
    keys.push(agendaDateKey(cursor));
    cursor = addDays(cursor, 1);
    if (keys.length > 366) break;
  }
  return keys;
}

export function groupEventsByDay(events) {
  const map = new Map();
  for (const event of events || []) {
    const keys = eventDateKeys(event);
    for (const key of keys) {
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(event);
    }
  }
  return map;
}

export function weekDaysFrom(anchor) {
  const start = startOfWeek(anchor || new Date(), { weekStartsOn: 1 });
  return Array.from({ length: 7 }, (_, i) => addDays(start, i));
}

export function isAbsenceEvent(event) {
  const t = String(event?.type || "").toLowerCase();
  return t === "absence" || t === "ausencia" || t === "ausência"
    || t === "ferias" || t === "férias";
}

export function eventKindLabel(type) {
  if (isAbsenceEvent({ type })) return "Ausência";
  return type === "event" ? "Evento" : "Prazo";
}

export function firstName(fullName) {
  const text = String(fullName || "").trim();
  if (!text) return "";
  return text.split(/\s+/)[0];
}

export function isTeamCalendarRole(role) {
  return TEAM_CALENDAR_ROLES.includes(String(role || "").toLowerCase());
}

export function formatCalendarEventTitle(event, { viewerId, isTeamView } = {}) {
  const title = event?.title || "Agendamento";
  if (!isTeamView) return title;
  const responsibleId = event?.responsible_id
    || event?.assigned_consultor_id
    || (event?.assigned_user_ids || [])[0];
  if (viewerId && responsibleId && responsibleId === viewerId) return title;
  const name = firstName(event?.responsible_name || event?.assigned_user_name);
  if (!name) return title;
  if (title.startsWith(`[${name}]`)) return title;
  return `[${name}] ${title}`;
}

export function hashString(seed) {
  const s = String(seed ?? "");
  let h = 2166136261;
  for (let i = 0; i < s.length; i += 1) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export function clientEventHue(event) {
  const seed = event?.process_id || event?.client_name || event?.id || event?.title || "";
  return hashString(seed) % 360;
}

export function calendarEventChipStyle(event) {
  if (isAbsenceEvent(event)) {
    return {
      className: "border border-destructive/40 bg-muted text-muted-foreground",
      style: undefined,
    };
  }
  const hue = clientEventHue(event);
  return {
    className: "border",
    style: {
      backgroundColor: `hsl(${hue} 55% 50% / 0.18)`,
      borderColor: `hsl(${hue} 48% 42% / 0.55)`,
      borderLeftWidth: "3px",
      borderLeftColor: `hsl(${hue} 55% 40%)`,
    },
  };
}
