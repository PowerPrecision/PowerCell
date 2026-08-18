/**
 * PACOTE DO.2 — Agrupar eventos da Agenda (Pacote DH) por dia civil.
 * Datas `YYYY-MM-DD` são interpretadas em local time (evita o salto UTC).
 */
import { addDays, startOfWeek } from "date-fns";

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

export function groupEventsByDay(events) {
  const map = new Map();
  for (const event of events || []) {
    const key = agendaDateKey(event?.due_date);
    if (!key) continue;
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(event);
  }
  return map;
}

export function weekDaysFrom(anchor) {
  const start = startOfWeek(anchor || new Date(), { weekStartsOn: 1 });
  return Array.from({ length: 7 }, (_, i) => addDays(start, i));
}

export function eventKindLabel(type) {
  return type === "event" ? "Evento" : "Prazo";
}
