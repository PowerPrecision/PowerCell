/**
 * PACOTE DU — Feed de notas do processo (observation_notes).
 */

export function resolveProcessObservationNotes(process) {
  if (!process || typeof process !== "object") return [];
  const notes = process.observation_notes;
  if (Array.isArray(notes) && notes.length > 0) {
    return notes.filter((n) => n && (n.text || n.text === ""));
  }
  const legacy = process.observations ?? process.notes;
  if (legacy != null && String(legacy).trim().length > 0) {
    return [{
      id: "legacy",
      text: String(legacy),
      created_at: process.updated_at || process.created_at || null,
      user_id: null,
      user_name: null,
    }];
  }
  return [];
}
