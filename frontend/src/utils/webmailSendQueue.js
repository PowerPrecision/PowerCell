/**
 * PACOTE 9 — Undo Send (Webmail): helpers puros do fluxo de envio
 * com janela de "Desfazer" (10s por defeito).
 *
 * O backend (POST /api/emails/send) devolve:
 *   { success, queued: true, send_id, undo_window_seconds, message }
 *
 * O frontend mostra um toast "Email a ser enviado..." com botão
 * "Desfazer" durante a janela; o cancelamento chama
 * POST /api/emails/{send_id}/cancel-send e repõe o modo de edição do
 * rascunho (composer reaberto com o snapshot intacto).
 *
 * Testável com: node --test src/utils/webmailSendQueue.test.js
 */

/**
 * Normaliza a resposta do endpoint de envio.
 *
 * @param {any} data Corpo JSON da resposta (pode ser null/undefined).
 * @returns {{queued: boolean, sendId: string|null, undoWindowMs: number}}
 */
export function parseSendResponse(data) {
  if (!data || typeof data !== "object") {
    return { queued: false, sendId: null, undoWindowMs: 0 };
  }
  const windowSeconds = Number(data.undo_window_seconds);
  const safeWindow = Number.isFinite(windowSeconds) && windowSeconds > 0
    ? windowSeconds
    : 0;
  return {
    queued: data.queued === true,
    sendId: typeof data.send_id === "string" && data.send_id ? data.send_id : null,
    undoWindowMs: Math.round(safeWindow * 1000),
  };
}

/**
 * Snapshot do estado do composer para repor a edição caso o utilizador
 * clique em "Desfazer" (o composer fecha no clique de "Enviar", estilo
 * Gmail — o undo devolve o utilizador ao rascunho exacto).
 *
 * @param {{composerData: object, uploadAttachments: Array}} state
 * @returns {object} snapshot imutável ({composerData, uploadAttachments})
 */
export function buildComposerSnapshot({ composerData, uploadAttachments }) {
  return {
    composerData: { ...(composerData || {}) },
    uploadAttachments: Array.isArray(uploadAttachments)
      ? uploadAttachments.map((a) => ({ ...a }))
      : [],
  };
}

/**
 * Constrói o corpo do pedido de cancelamento a partir do draft devolvido
 * pelo backend (cancel devolve {draft: {...}}) — repõe os campos do
 * composer no formato de edição (strings separadas por vírgula).
 *
 * @param {any} draft Campo `draft` da resposta do cancel-send.
 * @returns {{to_emails: string, cc_emails: string, subject: string,
 *            body: string, process_id: (string|null)}} payload do composer.
 */
export function draftToComposerFields(draft) {
  if (!draft || typeof draft !== "object") {
    return {
      to_emails: "",
      cc_emails: "",
      subject: "",
      body: "",
      process_id: null,
    };
  }
  const join = (v) =>
    Array.isArray(v) ? v.join(", ") : (typeof v === "string" ? v : "");
  return {
    to_emails: join(draft.to_emails),
    cc_emails: join(draft.cc_emails),
    subject: typeof draft.subject === "string" ? draft.subject : "",
    body: typeof draft.body === "string" ? draft.body : "",
    process_id: draft.process_id || null,
  };
}
