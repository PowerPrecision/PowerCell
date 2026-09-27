/**
 * Pacote EC — React Query para a lista do Webmail.
 *
 * staleTime de 1 minuto: ao reabrir a aba, a cache aparece de imediato
 * enquanto um refetch em background valida novidades (sem skeleton).
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { queryKeys } from "../lib/queryClient";
// Ponto 8, Fase 2 — pelo cliente Axios, nunca por `fetch` cru. É o
// interceptor que injecta `X-Company-Id` e `X-Active-Role`, e sem eles a
// caixa mostrada passa a ser a de outro perfil (incidente 2026-09-21).
import { getWebmailEmails } from "../services/api";

/** 1 minuto — cache instantânea ao abrir o Webmail, validação em fundo. */
export const WEBMAIL_STALE_TIME_MS = 60 * 1000;

export function buildWebmailQueryKey(filters = {}) {
  return queryKeys.emails.webmail(filters);
}

export async function fetchWebmailEmails({
  folder = "inbox",
  page = 1,
  search = "",
  label = null,
  customFolderId = null,
  account = "",
  box = "",
  companyId = "",
  mailbox = "",
} = {}) {
  const params = {
    folder: customFolderId ? "custom" : folder,
    page: page || 1,
    limit: 30,
    account: account || "",
  };
  if (search && String(search).trim()) params.search = String(search).trim();
  if (label) params.label = label;
  if (customFolderId) params.custom_folder = customFolderId;
  if (box) params.box = box;
  // Ponto 8, Fase 1 — o separador manda. Vai como parâmetro e não como
  // header: o âmbito da caixa deixa de depender do Context Switcher.
  if (companyId) params.company_id = companyId;
  if (mailbox) params.mailbox = mailbox;

  try {
    const { data } = await getWebmailEmails(params);
    return data;
  } catch (error) {
    // A mensagem do servidor é a que diz "empresa não encontrada" (404
    // do âmbito) ou "acesso à caixa não permitido" — perdê-la deixaria o
    // utilizador com um "Erro" mudo.
    const detalhe = error?.response?.data?.detail;
    throw new Error(detalhe || error?.message || "Erro ao carregar emails");
  }
}

export function patchWebmailEmail(queryClient, emailId, patch, unreadDelta = 0) {
  queryClient.setQueriesData({ queryKey: queryKeys.emails.webmailAll() }, (old) => {
    if (!old || !Array.isArray(old.emails)) return old;
    const next = {
      ...old,
      emails: old.emails.map((item) => (item.id === emailId ? { ...item, ...patch } : item)),
    };
    if (unreadDelta && typeof old.unread_count === "number") {
      next.unread_count = Math.max(0, old.unread_count + unreadDelta);
    }
    return next;
  });
}

export function useWebmailEmails({
  token,
  folder,
  page,
  search,
  label,
  customFolderId,
  account,
  box,
  companyId,
  mailbox,
  enabled = true,
} = {}) {
  const filters = {
    folder: customFolderId ? "custom" : folder,
    page: page || 1,
    search: search || "",
    label: label || null,
    customFolderId: customFolderId || null,
    account: account || "",
    box: box || "",
    companyId: companyId || "",
    mailbox: mailbox || "",
  };

  return useQuery({
    queryKey: buildWebmailQueryKey(filters),
    queryFn: () => fetchWebmailEmails(filters),
    enabled: Boolean(token) && enabled !== false,
    staleTime: WEBMAIL_STALE_TIME_MS,
    placeholderData: keepPreviousData,
  });
}

export default useWebmailEmails;
