/**
 * useNewEmailRealtime — `new_email` (WebSocket) → lista do Webmail.
 *
 * ANTES (Pacote EC): o evento disparava `invalidateQueries`, ou seja, um
 * GET completo à lista só para mostrar uma linha que o próprio evento já
 * transportava. Um round-trip por email recebido, e a lista a saltar para
 * a página 1.
 *
 * AGORA (Épico 5): quando o email pertence à lista que está aberta, a
 * linha entra directamente na cache — sem rede. O refetch continua a
 * existir para tudo o resto (outras pastas, pesquisa activa, páginas
 * seguintes), onde só o servidor sabe se e onde o email encaixa.
 *
 * A decisão e o merge vivem em `utils/webmailRealtime.js`, testados à
 * parte; aqui fica só a ligação ao React Query.
 */
import { useCallback, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import useWebSocket from "./useWebSocket";
import { queryKeys } from "../lib/queryClient";
import { insertEmailIntoList, shouldInsertEmail } from "../utils/webmailRealtime";

export function invalidateEmailQueries(queryClient) {
  return queryClient.invalidateQueries({ queryKey: queryKeys.emails.webmailAll() });
}

/**
 * @param {object} [options]
 * @param {(payload: object, inserted: boolean) => void} [options.onReceived]
 *   Chamado depois de tratar o evento. `inserted` diz se a linha entrou na
 *   lista aberta (permite ao ecrã actualizar contadores locais).
 * @param {object} [options.view] — Estado da lista: `{folder, page, search, mailbox}`.
 * @param {Array} [options.queryKey] — Chave exacta da lista aberta.
 * @param {boolean} [options.autoConnect=true]
 * @returns {{isConnected: boolean}} — use-o para suspender o polling.
 */
export function useNewEmailRealtime({
  onReceived,
  view,
  queryKey,
  autoConnect = true,
} = {}) {
  const queryClient = useQueryClient();

  // O ecrã re-renderiza a cada tecla na pesquisa; guardar em ref evita
  // re-subscrever o WebSocket a cada render.
  const viewRef = useRef(view);
  viewRef.current = view;
  const queryKeyRef = useRef(queryKey);
  queryKeyRef.current = queryKey;
  const onReceivedRef = useRef(onReceived);
  onReceivedRef.current = onReceived;

  const onNewEmail = useCallback(
    (payload) => {
      const currentView = viewRef.current;
      const currentKey = queryKeyRef.current;
      let inserted = false;

      if (currentKey && shouldInsertEmail(payload, currentView || {})) {
        const before = queryClient.getQueryData(currentKey);
        const after = insertEmailIntoList(before, payload);
        if (after && after !== before) {
          queryClient.setQueryData(currentKey, after);
          inserted = true;
        }
      }

      if (!inserted) {
        // Não pertence à lista aberta (outra pasta, pesquisa activa) ou já
        // lá estava. Marcar as listas como velhas chega: refazem-se quando
        // o utilizador lá for, sem um GET agora.
        queryClient.invalidateQueries({
          queryKey: queryKeys.emails.webmailAll(),
          refetchType: "none",
        });
      }

      const handler = onReceivedRef.current;
      if (handler) handler(payload, inserted);
    },
    [queryClient],
  );

  const { isConnected } = useWebSocket({
    autoConnect,
    onNewEmail,
  });

  return { isConnected };
}

export default useNewEmailRealtime;
