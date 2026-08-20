/**
 * Encaminhamento de rascunhos (Pacote DM).
 *
 * Os "rascunhos" no Dashboard misturam:
 *  - processos em fase inicial / pré-registo
 *  - rascunhos de email (webmail / auto-drafts)
 *
 * Clicar num rascunho NÃO deve ir sempre para ProcessDetails — isso falha
 * para leads sem processo completo e para emails.
 */

export const PROCESS_DRAFT_STATUSES = new Set([
  "pre_registo",
  "clientes_espera",
  "fase_documental",
]);

/**
 * @param {object} item — processo, lead ou rascunho de email
 * @returns {{ href: string, kind: 'email'|'lead'|'process' }}
 */
export function getDraftNavigationTarget(item) {
  if (!item || typeof item !== "object") {
    return { href: "/rascunhos", kind: "process" };
  }

  const isEmailDraft = Boolean(
    item.is_auto_draft
    || item.folder === "drafts"
    || item.doc_type
    || item.kind === "email"
    || (item.status === "draft" && (item.subject || item.to_emails || item.body))
  );

  if (isEmailDraft) {
    const draftId = item.id || item.email_id;
    const qs = new URLSearchParams({ folder: "drafts" });
    if (draftId) qs.set("id", String(draftId));
    return { href: `/webmail?${qs.toString()}`, kind: "email" };
  }

  const status = item.status;
  const clientId = item.client_id || item.clientId;
  if (status === "pre_registo" || item.is_lead) {
    const qs = new URLSearchParams();
    if (clientId) qs.set("clientId", String(clientId));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return { href: `/registos-clientes${suffix}`, kind: "lead" };
  }

  const processId = item.id || item.process_id;
  if (processId) {
    return { href: `/processo/${processId}`, kind: "process" };
  }

  return { href: "/rascunhos", kind: "process" };
}
