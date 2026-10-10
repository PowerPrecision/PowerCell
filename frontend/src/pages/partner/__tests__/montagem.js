/**
 * Montagem comum dos testes de PÁGINA do Portal do Parceiro.
 *
 * Monta a árvore REAL (`PartnerPortalRoutes`, o contexto de sessão, os
 * componentes e as páginas); só o cliente HTTP é substituído. As respostas
 * são as FIXTURES geradas pelos serviços do servidor — nunca a mão.
 */
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

import casoDeLead from "@/test/fixtures/parceiro/caso_lead.json";
import casoDeProcesso from "@/test/fixtures/parceiro/caso_processo.json";
import casos from "@/test/fixtures/parceiro/casos.json";
import painel from "@/test/fixtures/parceiro/painel.json";
import perfil from "@/test/fixtures/parceiro/perfil.json";
import PartnerPortalRoutes from "@/pages/partner/PartnerPortalRoutes";
import * as api from "@/services/partnerApi";
import { guardarSessao } from "@/utils/partnerSession";

export const FIXTURES = { casoDeLead, casoDeProcesso, casos, painel, perfil };

/** Um 404 como o Axios o levanta. */
export const erroHttp = (status, detail) => ({ response: { status, data: { detail } } });

/** Os valores por omissão de cada chamada — um teste sobrepõe só o que lhe interessa. */
export function prepararApi() {
  vi.clearAllMocks();
  api.obterPerfil.mockResolvedValue(perfil);
  api.obterPainel.mockResolvedValue(painel);
  api.listarCasos.mockResolvedValue(casos);
  api.obterCaso.mockImplementation(async (id) => {
    if (id === "a-novo") return structuredClone(casoDeProcesso);
    if (id === "lead-1") return structuredClone(casoDeLead);
    throw erroHttp(404, "Caso não encontrado.");
  });
}

/**
 * @param {string} rota - a rota inicial (completa, `/parceiro/...`).
 * @param {{ autenticado?: boolean }} opcoes
 */
export function montar(rota = "/parceiro", { autenticado = true } = {}) {
  sessionStorage.clear();
  if (autenticado) guardarSessao("tok-de-teste", 3600);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0, gcTime: 0 } },
  });
  const ui = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[rota]}>
        <Routes>
          <Route path="/parceiro/*" element={<PartnerPortalRoutes />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
  return { queryClient, ...ui };
}
