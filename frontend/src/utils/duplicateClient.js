/**
 * duplicateClient — Parsing do erro 409 de cliente duplicado (PACOTE 10).
 *
 * PORQUÊ: o backend devolve agora 409 Conflict com `detail` ESTRUTURADO
 * quando já existe um cliente com o mesmo NIF ou Email:
 *
 *   {
 *     "detail": {
 *       "message": "Já existe um cliente com este NIF ou Email: João Silva",
 *       "existing_client_id": "abc-123",
 *       "existing_client_name": "João Silva",
 *       "matched_fields": ["nif", "email"]
 *     }
 *   }
 *
 * Os formulários de criação usam `parseDuplicateClientError` para decidir
 * se mostram o alerta visual BLOQUEANTE (banner vermelho com a acção
 * "Usar cliente existente") em vez de um toast genérico.
 *
 * PACOTE 12 (Eixo 1) — a `message` devolvida é agora construída no frontend
 * a partir dos `matched_fields` (granular: NIF, Email ou ambos) em vez de
 * reutilizar a string genérica "NIF ou Email" do backend.
 *
 * Compatibilidade: durante o rollout também reconhece o formato LEGACY
 * (400 com string "Já existe um cliente com este NIF ou email"), para
 * não perder o alerta se um backend antigo responder primeiro.
 */

/**
 * Verifica se um erro axios corresponde a "cliente duplicado".
 *
 * @param {*} err - Erro capturado no catch (axios error ou outro)
 * @returns {boolean} true se o erro for de duplicação (409 novo ou 400 legacy)
 */
export function isDuplicateClientError(err) {
  const status = err?.response?.status;
  const detail = err?.response?.data?.detail;
  if (status === 409 && detail && typeof detail === "object") {
    // 409 estruturado do backend (PACOTE 10) — qualquer 409 com detail
    // objecto de criação de cliente é tratado como duplicado.
    return true;
  }
  // Legacy: 400 com a mensagem antiga (string) — robustez de rollout.
  if (status === 400 && typeof detail === "string") {
    return detail.toLowerCase().includes("já existe um cliente");
  }
  return false;
}

/**
 * Extrai a informação de duplicação de um erro de criação de cliente.
 *
 * @param {*} err - Erro capturado no catch
 * @returns {null|object} null se não for duplicado; senão:
 *   {
 *     message: string,                // mensagem legível para o banner
 *     existing_client_id: string|null,
 *     existing_client_name: string|null,
 *     matched_fields: string[],       // ["nif"] | ["email"] | ["nif","email"]
 *   }
 */
export function parseDuplicateClientError(err) {
  if (!isDuplicateClientError(err)) return null;

  const detail = err?.response?.data?.detail;

  if (detail && typeof detail === "object") {
    const matched = Array.isArray(detail.matched_fields)
      ? detail.matched_fields.filter((f) => f === "nif" || f === "email")
      : [];
    // PACOTE 12 (Eixo 1) — mensagem granular: construída a partir dos campos
    // em conflito (em vez da string genérica do backend), para o utilizador
    // saber imediatamente QUE campo duplicou. Com "matched" cru (backend sem
    // matched_fields úteis), o duplicateFieldLabel devolve "NIF ou Email" —
    // sem afirmar que ambos coincidiram.
    const hasBoth = matched.includes("nif") && matched.includes("email");
    const fieldPhrase = hasBoth
      ? "este NIF e este Email"
      : `este ${duplicateFieldLabel(matched)}`;
    const existingName = detail.existing_client_name || null;
    return {
      message: existingName
        ? `Já existe um cliente com ${fieldPhrase}: ${existingName}`
        : `Já existe um cliente com ${fieldPhrase}.`,
      existing_client_id: detail.existing_client_id || null,
      existing_client_name: existingName,
      matched_fields: matched.length > 0 ? matched : ["nif", "email"],
    };
  }

  // Legacy (400 string): extrai o nome após ":" quando existir.
  const text = typeof detail === "string" ? detail : "";
  const nameMatch = text.match(/:\s*(.+)$/);
  return {
    message: text || "Já existe um cliente com este NIF ou Email.",
    existing_client_id: null,
    existing_client_name: nameMatch ? nameMatch[1].trim() : null,
    matched_fields: ["nif", "email"],
  };
}

/**
 * Label amigável dos campos em conflito (para o sub-texto do banner).
 *
 * @param {string[]} matched_fields - Campos devolvidos pelo backend
 * @returns {string} "NIF", "Email" ou "NIF e Email"
 */
export function duplicateFieldLabel(matched_fields) {
  const hasNif = matched_fields?.includes("nif");
  const hasEmail = matched_fields?.includes("email");
  if (hasNif && hasEmail) return "NIF e Email";
  if (hasNif) return "NIF";
  if (hasEmail) return "Email";
  return "NIF ou Email";
}

export default { isDuplicateClientError, parseDuplicateClientError, duplicateFieldLabel };
