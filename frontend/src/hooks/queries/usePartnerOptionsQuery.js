/**
 * P4 — parceiros para os filtros «Por Parceiro» (Clientes, Processos, Quadro).
 * GET /partners/options → `[{id, name}]`.
 *
 * Os dropdowns liam-nos da lista de utilizadores (`role === "parceiro"`), que não os traz: os
 * parceiros do Portal vivem noutra colecção. A forma da resposta lê-se do servidor
 * (`{partners, total}`), e qualquer outra coisa vale lista vazia — um filtro vazio diz-se, não
 * rebenta o ecrã.
 */
import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "../../lib/queryClient";
import { getPartnerOptions } from "../../services/api";

const EMPTY_LIST = Object.freeze([]);

export function usePartnerOptionsQuery(options = {}) {
  const { enabled = true } = options;
  const query = useQuery({
    queryKey: queryKeys.partners.options(),
    queryFn: async () => {
      const res = await getPartnerOptions();
      const lista = res?.data?.partners;
      return Array.isArray(lista) ? lista : EMPTY_LIST;
    },
    enabled,
    staleTime: 5 * 60 * 1000,
  });

  return {
    parceiros: Array.isArray(query.data) ? query.data : EMPTY_LIST,
    isLoading: query.isLoading,
    isError: query.isError,
    query,
  };
}
