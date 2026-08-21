/**
 * Pacote DU + FA — filtros e horários do calendário.
 * Run: node --test src/utils/agendaCalendar.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  agendaDateKey,
  agendaTimeValue,
  buildEventPayload,
  combineDateAndTime,
  eventHasClockTime,
  eventMatchesConsultor,
  eventMatchesType,
  filterCalendarEvents,
  formatEventClockRange,
} from "./agendaCalendar.js";

describe("calendar filters", () => {
  const events = [
    { id: "1", type: "deadline", assigned_user_ids: ["c1"], title: "Prazo" },
    { id: "2", type: "event", assigned_consultor_id: "c2", title: "Marcação" },
    { id: "3", type: "absence", assigned_user_ids: ["c1"], title: "Férias" },
  ];

  it("filters by consultor", () => {
    assert.equal(eventMatchesConsultor(events[0], "c1"), true);
    assert.equal(eventMatchesConsultor(events[1], "c1"), false);
    assert.equal(filterCalendarEvents(events, { consultorId: "c1" }).map((e) => e.id).join(), "1,3");
  });

  it("filters by event type", () => {
    assert.equal(eventMatchesType(events[2], "absence"), true);
    assert.equal(filterCalendarEvents(events, { eventType: "event" }).map((e) => e.id).join(), "2");
  });
});

describe("calendar date+time (Pacote FA)", () => {
  it("extracts clock time from ISO datetimes and ignores date-only", () => {
    assert.equal(agendaTimeValue("2026-08-21T09:30:00"), "09:30");
    assert.equal(agendaTimeValue("2026-08-21T14:05:00.000Z"), "14:05");
    assert.equal(agendaTimeValue("2026-08-21"), "");
    assert.equal(agendaDateKey("2026-08-21T09:30:00"), "2026-08-21");
  });

  it("combines date and time into local ISO", () => {
    assert.equal(combineDateAndTime("2026-08-21", "09:00"), "2026-08-21T09:00:00");
    assert.equal(combineDateAndTime("2026-08-21", "10:30"), "2026-08-21T10:30:00");
    assert.equal(combineDateAndTime("2026-08-21", ""), "2026-08-21");
  });

  it("builds a timed payload with ISO due_date and end_date", () => {
    const payload = buildEventPayload({
      title: "Reunião",
      description: "Banco",
      due_date: "2026-08-21",
      end_date: "2026-08-21",
      start_time: "09:00",
      end_time: "10:30",
      priority: "high",
      type: "event",
      process_id: "p1",
      assigned_user_ids: ["u1"],
      all_day: false,
      visible_to_client: false,
    }, { currentUserId: "u1", isAbsence: false });
    assert.equal(payload.due_date, "2026-08-21T09:00:00");
    assert.equal(payload.end_date, "2026-08-21T10:30:00");
    assert.equal(payload.all_day, false);
    assert.equal(payload.process_id, "p1");
  });

  it("keeps date-only ISO for all-day events", () => {
    const payload = buildEventPayload({
      title: "Férias",
      description: "",
      due_date: "2026-08-10",
      end_date: "2026-08-20",
      start_time: "09:00",
      end_time: "10:00",
      priority: "medium",
      type: "absence",
      process_id: "p1",
      assigned_user_ids: ["u1"],
      all_day: true,
      visible_to_client: true,
    }, { currentUserId: "u1", isAbsence: true });
    assert.equal(payload.due_date, "2026-08-10");
    assert.equal(payload.end_date, "2026-08-20");
    assert.equal(payload.all_day, true);
    assert.equal(payload.process_id, null);
    assert.equal(payload.visible_to_client, false);
  });

  it("formats clock range and ignores all-day events", () => {
    const timed = {
      due_date: "2026-08-21T09:00:00",
      end_date: "2026-08-21T10:30:00",
      all_day: false,
    };
    assert.equal(eventHasClockTime(timed), true);
    assert.equal(formatEventClockRange(timed), "09:00–10:30");
    assert.equal(eventHasClockTime({ due_date: "2026-08-21", all_day: true }), false);
  });
});
