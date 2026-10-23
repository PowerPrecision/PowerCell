/**
 * Mutações do módulo Index (Lote 12, Fase 4).
 *
 * REGRAS
 *  * Cada acção invalida a bancada E a fila (o estado do processo muda nas duas).
 *  * Uma recusa esperada (403/422) mostra o MOTIVO do servidor num toast; nunca o texto de
 *    uma excepção. As chamadas levam `skipErrorToast` para o aviso ser um só.
 *  * «Marcar como Indexado» devolve JÁ: o fecho (análise do que falta, PDF limpo) corre em
 *    background e a notificação chega no fim.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { queryKeys } from "../../lib/queryClient";
import {
  analyzeIndexProcess,
  dismissIndexAlert,
  editIndexJob,
  extractIndexProcess,
  markIndexProcessIndexed,
  sanitizeIndexProcess,
} from "../../services/api";
import { mensagemDeErro } from "../../utils/indexRevisao";

export function useIndexMutations(processId) {
  const queryClient = useQueryClient();

  const refrescar = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.index.workstation(processId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.index.queueAll() }),
    ]);
  const falhou = (erro) => toast.error(mensagemDeErro(erro));

  const analisar = useMutation({
    mutationFn: ({ force = false } = {}) => analyzeIndexProcess(processId, force),
    onSuccess: (resposta) => {
      const d = resposta?.data || {};
      toast.info(d.message || "A análise está a correr em segundo plano.");
      return refrescar();
    },
    onError: falhou,
  });
  const extrair = useMutation({
    mutationFn: () => extractIndexProcess(processId),
    onSuccess: (resposta) => {
      toast.info(resposta?.data?.message || "A extracção está a correr em segundo plano.");
      return refrescar();
    },
    onError: falhou,
  });
  const sanitizar = useMutation({
    mutationFn: () => sanitizeIndexProcess(processId),
    onSuccess: (resposta) => {
      toast.info(resposta?.data?.message || "Os PDFs limpos estão a ser gerados em segundo plano.");
      return refrescar();
    },
    onError: falhou,
  });
  const editar = useMutation({
    mutationFn: ({ jobId, fields }) => editIndexJob(processId, jobId, fields),
    onSuccess: () => {
      toast.success("Alteração guardada.");
      return refrescar();
    },
    onError: falhou,
  });
  const dispensar = useMutation({
    mutationFn: (alertId) => dismissIndexAlert(processId, alertId),
    onSuccess: refrescar,
    onError: falhou,
  });
  const marcarIndexado = useMutation({
    mutationFn: ({ employers = [] } = {}) => markIndexProcessIndexed(processId, employers),
    onSuccess: (resposta) => {
      const recusados = resposta?.data?.employers?.rejected;
      toast.success("Processo marcado como indexado.");
      if (Array.isArray(recusados) && recusados.length > 0) {
        toast.info(`${recusados.length} NIF não foi aplicado; pode corrigi-lo na bancada.`);
      }
      return refrescar();
    },
    onError: falhou,
  });

  return { analisar, extrair, sanitizar, editar, dispensar, marcarIndexado };
}
