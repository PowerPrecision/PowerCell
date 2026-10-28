/**
 * Pedidos de alteração de atribuição do Index (Out 2026).
 *
 * O Index não muda atribuições: pede à chefia, com um motivo opcional. A chefia vê os pedidos da sua
 * rede na «Supervisão do Index», trata a atribuição pelo «Gerir» do processo e fecha o pedido.
 * O servidor decide o que cada um vê (o Index só os seus); aqui só se pede e se invalida.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { queryKeys } from "../lib/queryClient";
import { getPedidosDeAtribuicao, pedirAlteracaoDeAtribuicao, resolverPedidoDeAtribuicao } from "../services/api";
import { extractErrorMessage } from "../utils/extractErrorMessage";

const mensagemDe = (erro, recuo) => extractErrorMessage(erro?.response?.data?.detail, recuo);

export function usePedidosDeAtribuicao({ processId = "", estado = "pendente", enabled = true } = {}) {
  const query = useQuery({
    queryKey: queryKeys.index.pedidos(estado, processId),
    queryFn: async () => {
      const params = { estado };
      if (processId) params.process_id = processId;
      const { data } = await getPedidosDeAtribuicao(params);
      return Array.isArray(data?.itens) ? data.itens : [];
    },
    enabled,
  });
  return {
    pedidos: query.data ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    refetch: query.refetch,
  };
}

export function usePedirAlteracaoDeAtribuicao(processId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (motivo) => pedirAlteracaoDeAtribuicao(processId, motivo),
    onSuccess: () => {
      toast.success("Pedido enviado. A chefia foi avisada.");
      return queryClient.invalidateQueries({ queryKey: queryKeys.index.pedidosAll() });
    },
    onError: (erro) => toast.error(mensagemDe(erro, "Não foi possível enviar o pedido.")),
  });
}

export function useResolverPedidoDeAtribuicao() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ pedidoId, decisao, nota }) => resolverPedidoDeAtribuicao(pedidoId, decisao, nota),
    onSuccess: (_resposta, { decisao }) => {
      toast.success(decisao === "recusado" ? "Pedido recusado." : "Pedido marcado como tratado.");
      return queryClient.invalidateQueries({ queryKey: queryKeys.index.pedidosAll() });
    },
    onError: (erro) => toast.error(mensagemDe(erro, "Não foi possível actualizar o pedido.")),
  });
}
