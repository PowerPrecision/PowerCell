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

const TIME_HH_MM = /^(\d{2}):(\d{2})/;

/** Extract `HH:mm` from an ISO datetime (`2026-08-21T09:30:00`). Date-only → "". */
export function agendaTimeValue(value) {
  if (!value) return "";
  if (value instanceof Date) {
    if (Number.isNaN(value.getTime())) return "";
    const hh = String(value.getHours()).padStart(2, "0");
    const mm = String(value.getMinutes()).padStart(2, "0");
    return `${hh}:${mm}`;
  }
  const raw = String(value);
  const match = /T(\d{2}):(\d{2})/.exec(raw);
  return match ? `${match[1]}:${match[2]}` : "";
}

/** Join a `YYYY-MM-DD` date with `HH:mm` into a local ISO datetime (no Z). */
export function combineDateAndTime(dateStr, timeStr) {
  const date = agendaDateKey(dateStr);
  if (!date) return "";
  const rawTime = String(timeStr || "").trim();
  const match = TIME_HH_MM.exec(rawTime);
  if (!match) return date;
  return `${date}T${match[1]}:${match[2]}:00`;
}

export function eventHasClockTime(event) {
  if (!event || event.all_day) return false;
  return Boolean(agendaTimeValue(event.due_date) || agendaTimeValue(event.end_date));
}

export function formatEventStartTime(event) {
  if (!eventHasClockTime(event)) return "";
  return agendaTimeValue(event.due_date);
}

export function formatEventClockRange(event) {
  if (!eventHasClockTime(event)) return "";
  const start = agendaTimeValue(event.due_date);
  const end = agendaTimeValue(event.end_date);
  if (start && end && start !== end) return `${start}–${end}`;
  return start || end;
}

export const DEFAULT_EVENT_START_TIME = "09:00";
export const DEFAULT_EVENT_END_TIME = "10:00";

/**
 * Join form date + time into ISO strings the API stores on due_date / end_date.
 */
export function buildEventPayload(formData, { currentUserId, isAbsence } = {}) {
  const allDay = isAbsence ? true : !!formData.all_day;
  const startDate = formData.due_date;
  const endDate = formData.end_date || formData.due_date;
  const startTime = formData.start_time || DEFAULT_EVENT_START_TIME;
  const endTime = formData.end_time || DEFAULT_EVENT_END_TIME;
  return {
    title: formData.title,
    description: formData.description,
    priority: formData.priority,
    type: formData.type,
    process_id: isAbsence ? null : (formData.process_id || null),
    assigned_user_ids: (formData.assigned_user_ids || []).length > 0
      ? formData.assigned_user_ids
      : (currentUserId ? [currentUserId] : []),
    visible_to_client: isAbsence ? false : !!formData.visible_to_client,
    all_day: allDay,
    due_date: allDay ? startDate : combineDateAndTime(startDate, startTime),
    end_date: allDay
      ? (endDate || startDate)
      : combineDateAndTime(endDate || startDate, endTime),
  };
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

export function eventConsultorIds(event) {
  const ids = [
    event?.responsible_id,
    event?.assigned_consultor_id,
    event?.user_id,
    ...(Array.isArray(event?.assigned_user_ids) ? event.assigned_user_ids : []),
  ];
  return [...new Set(ids.filter(Boolean).map(String))];
}

export function eventMatchesConsultor(event, consultorId) {
  if (!consultorId || consultorId === "all") return true;
  return eventConsultorIds(event).includes(String(consultorId));
}

export function eventMatchesType(event, eventType) {
  if (!eventType || eventType === "all") return true;
  if (eventType === "absence") return isAbsenceEvent(event);
  const t = String(event?.type || "deadline").toLowerCase();
  return t === String(eventType).toLowerCase();
}

export function filterCalendarEvents(events, { consultorId, eventType } = {}) {
  return (events || []).filter(
    (event) => eventMatchesConsultor(event, consultorId) && eventMatchesType(event, eventType),
  );
}
