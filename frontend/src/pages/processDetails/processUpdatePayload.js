/**
 * Payload builders / sanitizers for ProcessDetails → PUT /processes/:id.
 *
 * CRITICAL: never ship accidental empty arrays (or unrelated list fields like
 * documents/onedrive_links) that would $set-wipe data on the backend.
 */

/** Top-level keys that must never be sent from the ProcessDetails form save. */
export const FORBIDDEN_PROCESS_UPDATE_KEYS = Object.freeze([
  "id",
  "documents",
  "documentos",
  "attachments",
  "anexos",
  "onedrive_links",
  "files",
  "history",
  "activities",
  "client_ids",
  "assigned_consultor_ids",
  "assigned_mediador_ids",
  "assigned_consultor_id",
  "assigned_mediador_id",
  "assigned_indexacao_id",
  "assigned_parceiro_id",
  "consultor_names",
  "mediador_names",
  "second_client_data",
  "created_at",
  "updated_at",
  "process_number",
]);

/**
 * Arrays that wipe server state when sent as [].
 * Only include when non-empty unless explicitly allowlisted.
 */
export const WIPE_SENSITIVE_ARRAY_KEYS = Object.freeze([
  "monitored_emails",
  "co_buyers",
  "co_applicants",
  "onedrive_links",
  "documents",
  "attachments",
  "client_ids",
]);

/**
 * Deep-merge nested process sections for optimistic cache updates.
 * Arrays from `incoming` replace only when defined (including empty when allowed).
 */
export function mergeProcessOptimistic(existing, incoming) {
  if (!existing || typeof existing !== "object") {
    return { ...(incoming || {}) };
  }
  if (!incoming || typeof incoming !== "object") {
    return existing;
  }

  const nestedObjectKeys = new Set([
    "personal_data",
    "financial_data",
    "real_estate_data",
    "credit_data",
    "titular2_data",
    "field_metadata",
    "vendedor",
    "mediador",
  ]);

  const out = { ...existing };
  for (const [key, value] of Object.entries(incoming)) {
    if (value === undefined) continue;
    if (
      nestedObjectKeys.has(key) &&
      value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      existing[key] &&
      typeof existing[key] === "object" &&
      !Array.isArray(existing[key])
    ) {
      out[key] = { ...existing[key], ...value };
    } else {
      out[key] = value;
    }
  }
  return out;
}

/**
 * Sanitize a process update body before PUT.
 *
 * @param {object} raw
 * @param {object} [options]
 * @param {string[]} [options.allowEmptyArrays] - keys allowed as []
 * @returns {object}
 */
export function sanitizeProcessUpdatePayload(raw, options = {}) {
  const allowEmpty = new Set(options.allowEmptyArrays || []);
  const cleaned = {};

  if (!raw || typeof raw !== "object") return cleaned;

  for (const [key, value] of Object.entries(raw)) {
    if (FORBIDDEN_PROCESS_UPDATE_KEYS.includes(key)) continue;
    if (value === undefined) continue;

    if (Array.isArray(value)) {
      if (value.length === 0) {
        if (allowEmpty.has(key)) {
          cleaned[key] = [];
        }
        // else: omit empty wipe-sensitive / accidental arrays
        continue;
      }
      cleaned[key] = value;
      continue;
    }

    cleaned[key] = value;
  }

  return cleaned;
}

/**
 * Sanitize client update body — drop empty strings that would wipe contactos.
 */
export function sanitizeClientUpdatePayload(raw) {
  const cleaned = {};
  if (!raw || typeof raw !== "object") return cleaned;

  for (const [key, value] of Object.entries(raw)) {
    if (value === undefined) continue;
    if (key === "contacto" && value && typeof value === "object") {
      const contacto = {};
      if (value.email && String(value.email).trim()) {
        contacto.email = String(value.email).trim();
      }
      if (value.telefone && String(value.telefone).trim()) {
        contacto.telefone = String(value.telefone).trim();
      }
      if (Object.keys(contacto).length > 0) cleaned.contacto = contacto;
      continue;
    }
    if (value === "") continue;
    if (Array.isArray(value) && value.length === 0) continue;
    cleaned[key] = value;
  }
  return cleaned;
}
