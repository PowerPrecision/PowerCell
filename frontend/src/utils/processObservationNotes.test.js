/**
 * Pacote DU — feed de observações.
 * Run: node --test src/utils/processObservationNotes.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { resolveProcessObservationNotes } from "./processObservationNotes.js";

describe("resolveProcessObservationNotes", () => {
  it("prefers observation_notes array", () => {
    const notes = resolveProcessObservationNotes({
      observation_notes: [{ id: "n1", text: "nova" }],
      observations: "legado",
    });
    assert.equal(notes.length, 1);
    assert.equal(notes[0].text, "nova");
  });

  it("falls back to observations string", () => {
    const notes = resolveProcessObservationNotes({ observations: "nota livre" });
    assert.equal(notes.length, 1);
    assert.equal(notes[0].id, "legacy");
    assert.equal(notes[0].text, "nota livre");
  });

  it("returns empty when nothing stored", () => {
    assert.deepEqual(resolveProcessObservationNotes({}), []);
  });
});
