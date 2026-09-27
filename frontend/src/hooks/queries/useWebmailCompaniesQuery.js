/**
 * useWebmailCompaniesQuery — as empresas do Webmail (Ponto 8, Fase 3).
 *
 * Alimenta a barra de separadores. A lista vem do backend e não do
 * `user.companies` do AuthContext de propósito: é o mesmo cálculo que
 * autoriza os pedidos (`assert_empresa_no_ambito`, 404), e derivá-la no
 * cliente abria a porta a mostrar um separador que o servidor recusa.
 *
 * `staleTime` longo: a lista de empresas de alguém muda quando muda um
 * UCR, o que não acontece durante uma sessão de leitura de email.
 *
 * Degradação graciosa: erro devolve lista vazia — a página abre com a
 * caixa sem barra, em vez de rebentar por causa dos separadores.
 */
import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "../../lib/queryClient";
import { getWebmailCompanies } from "../../services/api";

/** 10 minutos — os UCRs não mudam a meio de uma leitura de email. */
export const EMPRESAS_STALE_TIME_MS = 10 * 60 * 1000;

const VAZIO = [];

export function useWebmailCompaniesQuery({ enabled = true } = {}) {
  const query = useQuery({
    queryKey: queryKeys.emails.companies(),
    queryFn: async () => {
      try {
        const { data } = await getWebmailCompanies();
        return Array.isArray(data?.companies) ? data.companies : VAZIO;
      } catch {
        return VAZIO;
      }
    },
    enabled,
    staleTime: EMPRESAS_STALE_TIME_MS,
  });

  return {
    empresas: Array.isArray(query.data) ? query.data : VAZIO,
    isLoading: query.isLoading,
    query,
  };
}

export default useWebmailCompaniesQuery;
