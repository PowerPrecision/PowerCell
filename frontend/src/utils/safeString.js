/**
 * safeString — Extracts a plain string from any value, handling objects like {value, label}.
 * Prevents React Error #31 when rendering values that might be objects.
 */
export function safeString(val, fallback = "") {
  if (val === null || val === undefined) return fallback;
  if (typeof val === "string") return val;
  if (typeof val === "number" || typeof val === "boolean") return String(val);
  if (typeof val === "object") {
    // Handle {value, label} pattern from MongoDB
    if (val.value && typeof val.value === "string") return val.value;
    if (val.label && typeof val.label === "string") return val.label;
    // Try common keys
    if (val.name && typeof val.name === "string") return val.name;
    // Last resort: JSON stringify
    try { return JSON.stringify(val); } catch { return fallback; }
  }
  return String(val);
}

/**
 * safeStringArray — Maps an array of values through safeString.
 * Ensures all elements are renderable strings.
 */
export function safeStringArray(arr, fallback = "") {
  if (!Array.isArray(arr)) return [];
  return arr.map(item => safeString(item, fallback));
}
