/**
 * extractErrorMessage — Safely extracts a string message from any error response.
 * Handles Pydantic validation errors [{type, loc, msg, input}], plain strings, and objects.
 * Prevents React Error #31 when passing errors to toast.error() or setError().
 *
 * @param {*} detail - The error detail (string, array of Pydantic errors, or object)
 * @param {string} fallback - Default message if extraction fails
 * @returns {string} A safe string message
 */
export function extractErrorMessage(detail, fallback = "Ocorreu um erro") {
  if (!detail) return fallback;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map(e => {
        if (typeof e === 'string') return e;
        if (e && typeof e === 'object' && e.msg) return e.msg;
        try { return JSON.stringify(e); } catch { return ''; }
      })
      .filter(Boolean)
      .join(' • ') || fallback;
  }
  if (typeof detail === 'object') {
    if (detail.msg) return detail.msg;
    if (detail.message) return detail.message;
    try { return JSON.stringify(detail); } catch { return fallback; }
  }
  return String(detail);
}

export default extractErrorMessage;
