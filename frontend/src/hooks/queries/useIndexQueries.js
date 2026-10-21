/**
 * Hooks de leitura do módulo Index (Lote 12, Fase 4).
 *
 * TEMPO REAL: os jobs do Index são `TaskLog` (tipos `INDEX_*`) e o backend publica
 * `task_started/progress/completed/failed` ao dono. O evento é o GATILHO, não o transporte:
 * invalida-se a query e o TanStack vai buscar a verdade. O polling não desaparece — é o recuo
 * quando o WebSocket está em baixo (só corre enquanto há um job activo E não há socket).
 */
import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { queryKeys } from "../../lib/queryClient";
import { getIndexQueue, getIndexWorkstation, searchIndexEmployers } from "../../services/api";
import { TASK_SOURCE, useTaskEvents } from "../useTaskEvents";
import {
  eventoDoIndex,
  haJobActivo,
  listaDoServidor,
  normalizarBancada,
  normalizarFila,
} from "../../utils/indexRevisao";

const INTERVALO_DE_RECUO_MS = 4000;

export function useIndexQueueQuery({ tab = "pending", page = 1, q = "", enabled = true } = {}) {
  const queryClient = useQueryClient();

  const aoEvento = useCallback(
    (payload) => {
      if (!eventoDoIndex(payload)) return;
      queryClient.invalidateQueries({ queryKey: queryKeys.index.queueAll() });
    },
    [queryClient],
  );
  useTaskEvents(aoEvento, { source: TASK_SOURCE.TASK_LOG, enabled });

  const query = useQuery({
    queryKey: queryKeys.index.queue(tab, page, q),
    queryFn: async () => normalizarFila((await getIndexQueue({ tab, page, q: q || undefined })).data),
    enabled,
    placeholderData: (anterior) => anterior,
  });

  return {
    itens: query.data?.itens ?? [],
    total: query.data?.total ?? 0,
    tamanho: query.data?.tamanho ?? 0,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
}

export function useIndexWorkstationQuery(processId, { enabled = true } = {}) {
  const queryClient = useQueryClient();
  const chave = queryKeys.index.workstation(processId);

  const aoEvento = useCallback(
    (payload) => {
      if (!eventoDoIndex(payload, processId)) return;
      queryClient.invalidateQueries({ queryKey: chave });
    },
    // `chave` muda só com o processo
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [queryClient, processId],
  );
  const { isConnected } = useTaskEvents(aoEvento, {
    source: TASK_SOURCE.TASK_LOG,
    enabled: enabled && Boolean(processId),
  });

  const query = useQuery({
    queryKey: chave,
    queryFn: async () => normalizarBancada((await getIndexWorkstation(processId)).data),
    enabled: enabled && Boolean(processId),
    // recuo: só enquanto há um job a correr E o WebSocket não nos avisa
    refetchInterval: (q) => (!isConnected && haJobActivo(q.state.data?.jobsActivos) ? INTERVALO_DE_RECUO_MS : false),
  });

  return {
    bancada: query.data ?? null,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    isRealtime: isConnected,
  };
}

/** Directório global de entidades patronais (NIF + nome). Pesquisa com pelo menos 2 caracteres. */
export function useIndexEmployersQuery(texto, { enabled = true } = {}) {
  const q = String(texto || "").trim();
  const query = useQuery({
    queryKey: queryKeys.index.employers(q),
    queryFn: async () => listaDoServidor((await searchIndexEmployers(q)).data?.items),
    enabled: enabled && q.length >= 2,
    staleTime: 60_000,
  });
  return { entidades: query.data ?? [], isLoading: query.isLoading, isError: query.isError };
}
