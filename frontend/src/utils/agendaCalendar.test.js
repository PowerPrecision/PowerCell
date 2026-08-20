/**
 * Pacote DU — filtros do calendário.
 * Run: node --test src/utils/agendaCalendar.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { eventMatchesConsultor, eventMatchesType, filterCalendarEvents } from "./agendaCalendar.js";

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
