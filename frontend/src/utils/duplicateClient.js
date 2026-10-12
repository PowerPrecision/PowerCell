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
 * D-38 (Out 2026): o TELEMÓVEL também não se repete dentro da rede
 * (`matched_fields` pode trazer "telefone"), e o formulário PÚBLICO responde
 * 409 com um corpo GENÉRICO e anónimo — sem id nem nome do cliente
 * existente:
 *
 *   { "success": false, "code": "DUPLICATE_CLIENT",
 *     "detail": "Já existe um registo associado a este NIF, Email ou Telemóvel." }
 *
 * Esse formato tem o seu próprio reconhecedor (`isPublicDuplicateError`):
 * `detail` é uma STRING, logo `isDuplicateClientError` (409 + detail objecto)
 * não o confunde com o da equipa.
 *
 * Compatibilidade: durante o rollout também reconhece o formato LEGACY
 * (400 com string "Já existe um cliente com este NIF ou email"), para
 * não perder o alerta se um backend antigo responder primeiro.
 */

/** Os campos que o servidor pode devolver em `matched_fields`, pela ordem em que se dizem. */
const CAMPOS_CONHECIDOS = ["nif", "email", "telefone"];
const ROTULOS = { nif: "NIF", email: "Email", telefone: "Telemóvel" };

/**
 * Verifica se um erro axios corresponde a "cliente duplicado".
 *
 * @param {*} err - Erro capturado no catch (axios error ou outro)
 * @returns {boolean} true se o erro for de duplicação (409 novo ou 400 legacy)
 */
/** Código do 409 anónimo do formulário público (espelha `erro_publico_de_duplicado`). */
export const PUBLIC_DUPLICATE_CODE = "DUPLICATE_CLIENT";

/** Mensagem por omissão quando o servidor não a envia. */
export const PUBLIC_DUPLICATE_MESSAGE =
  "Já existe um registo associado a este NIF, Email ou Telemóvel.";

/**
 * O 409 do formulário PÚBLICO (D-38)? Reconhece-se pelo `code` e não só pelo
 * estado: um 409 qualquer não é, necessariamente, "já está registado".
 *
 * @returns {string|null} a mensagem a mostrar, ou null se não for esse erro
 */
export function publicDuplicateMessage(err) {
  const status = err?.response?.status;
  const data = err?.response?.data;
  if (status !== 409 || data?.code !== PUBLIC_DUPLICATE_CODE) return null;
  return typeof data.detail === "string" && data.detail.trim()
    ? data.detail
    : PUBLIC_DUPLICATE_MESSAGE;
}

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
    // Pela ordem em que se dizem ao utilizador (NIF, Email, Telemóvel), não pela do servidor.
    const matched = Array.isArray(detail.matched_fields)
      ? CAMPOS_CONHECIDOS.filter((f) => detail.matched_fields.includes(f))
      : [];
    // PACOTE 12 (Eixo 1) — mensagem granular: construída a partir dos campos
    // em conflito (em vez da string genérica do backend), para o utilizador
    // saber imediatamente QUE campo duplicou. Com "matched" cru (backend sem
    // matched_fields úteis), o duplicateFieldLabel devolve "NIF ou Email" —
    // sem afirmar que ambos coincidiram.
    const fieldPhrase = matched.length > 1
      ? `${matched.map((f) => `este ${ROTULOS[f]}`).slice(0, -1).join(", ")} e este ${ROTULOS[matched[matched.length - 1]]}`
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
 * @returns {string} "NIF", "Email", "Telemóvel", "NIF e Email", "NIF, Email e Telemóvel"…
 */
export function duplicateFieldLabel(matched_fields) {
  const rotulos = CAMPOS_CONHECIDOS.filter((f) => matched_fields?.includes(f)).map((f) => ROTULOS[f]);
  if (rotulos.length === 0) return "NIF ou Email";
  if (rotulos.length === 1) return rotulos[0];
  return `${rotulos.slice(0, -1).join(", ")} e ${rotulos[rotulos.length - 1]}`;
}

export default {
  isDuplicateClientError,
  parseDuplicateClientError,
  duplicateFieldLabel,
  publicDuplicateMessage,
};
