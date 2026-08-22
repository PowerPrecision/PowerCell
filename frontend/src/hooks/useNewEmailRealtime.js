/**
 * Pacote EC — listener WebSocket `new_email` → refetch silencioso da lista.
 *
 * Usa React Query `invalidateQueries` na key `emails.webmailAll()` para que
 * só a lista do Webmail actualize em background — não a cache global de emails.
 */
import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import useWebSocket from "./useWebSocket";
import { queryKeys } from "../lib/queryClient";

export function invalidateEmailQueries(queryClient) {
  return queryClient.invalidateQueries({ queryKey: queryKeys.emails.webmailAll() });
}

export function useNewEmailRealtime({ onReceived, autoConnect = true } = {}) {
  const queryClient = useQueryClient();

  const onNewEmail = useCallback(
    (payload) => {
      invalidateEmailQueries(queryClient);
      if (onReceived) onReceived(payload);
    },
    [queryClient, onReceived],
  );

  useWebSocket({
    autoConnect,
    onNewEmail,
  });
}

export default useNewEmailRealtime;
