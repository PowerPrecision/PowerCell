/**
 * Pacote EC — listener WebSocket `new_email` → refetch silencioso da lista.
 *
 * Usa React Query `invalidateQueries({ queryKey: ['emails'] })` para que o
 * Webmail actualize em background sem spinners de loading.
 */
import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import useWebSocket from "./useWebSocket";
import { queryKeys } from "../lib/queryClient";

export function invalidateEmailQueries(queryClient) {
  return queryClient.invalidateQueries({ queryKey: queryKeys.emails.all });
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
