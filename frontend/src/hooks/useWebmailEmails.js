/**
 * Pacote EC — React Query para a lista do Webmail.
 *
 * staleTime de 1 minuto: ao reabrir a aba, a cache aparece de imediato
 * enquanto um refetch em background valida novidades (sem skeleton).
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { queryKeys } from "../lib/queryClient";

const API_URL = process.env.REACT_APP_BACKEND_URL;

/** 1 minuto — cache instantânea ao abrir o Webmail, validação em fundo. */
export const WEBMAIL_STALE_TIME_MS = 60 * 1000;

export function buildWebmailQueryKey(filters = {}) {
  return queryKeys.emails.webmail(filters);
}

export async function fetchWebmailEmails({
  headers,
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
  const actualFolder = customFolderId ? "custom" : folder;
  const params = new URLSearchParams({
    folder: actualFolder,
    page: String(page || 1),
    limit: "30",
    account: account || "",
  });
  if (search && String(search).trim()) {
    params.append("search", String(search).trim());
  }
  if (label) {
    params.append("label", label);
  }
  if (customFolderId) {
    params.append("custom_folder", customFolderId);
  }
  if (box) {
    params.append("box", box);
  }
  if (companyId) {
    params.append("company_id", companyId);
  }
  if (mailbox) {
    params.append("mailbox", mailbox);
  }

  const response = await fetch(`${API_URL}/api/emails/webmail?${params.toString()}`, {
    headers,
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Erro ${response.status} ao carregar emails`);
  }
  return response.json();
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
  headers,
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
    queryFn: () => fetchWebmailEmails({ headers, ...filters }),
    enabled: Boolean(token) && enabled !== false,
    staleTime: WEBMAIL_STALE_TIME_MS,
    placeholderData: keepPreviousData,
  });
}

export default useWebmailEmails;
