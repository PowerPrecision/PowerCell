/**
 * useIniciarTratamento — abrir a bancada é começar a trabalhar (substitui o botão «Reivindicar»).
 *
 * Faz UM pedido por processo quando `activo` (o processo é do utilizador e ainda está por começar):
 * `POST /api/index/processes/{id}/start`, que passa o processo a «em tratamento» e arranca o relógio da
 * estagnação. Quem decide é o servidor (só o indexador atribuído conta); aqui só se evita pedir de mais.
 * É um reforço: uma falha não se mostra (o próximo gesto de trabalho — analisar, editar, carregar — volta a
 * registar), mas refresca a bancada e a fila quando o estado mudou.
 */
import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { queryKeys } from "../lib/queryClient";
import { startIndexWork } from "../services/api";

export function useIniciarTratamento(processId, activo) {
  const queryClient = useQueryClient();
  const jaPedido = useRef(null);

  useEffect(() => {
    if (!activo || !processId || jaPedido.current === processId) return;
    jaPedido.current = processId;
    let cancelado = false;
    startIndexWork(processId)
      .then((resposta) => {
        if (cancelado || resposta?.data?.iniciado !== true) return;
        queryClient.invalidateQueries({ queryKey: queryKeys.index.workstation(processId) });
        queryClient.invalidateQueries({ queryKey: queryKeys.index.queueAll() });
      })
      .catch(() => {
        // best effort: o servidor volta a registar no primeiro gesto de trabalho
        jaPedido.current = null;
      });
    return () => {
      cancelado = true;
    };
  }, [activo, processId, queryClient]);
}

export default useIniciarTratamento;
