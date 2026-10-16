/**
 * Pesquisa global (Ctrl+K) — a excepção ao contexto estrito de empresa (Lote 7.1).
 *
 * Monta o modal REAL. Falseia só o cliente da API, o `useAuth` e o router (para ver a navegação).
 * Os valores do fixture NÃO são os da omissão: um resultado sem `empresa` tem de aparecer sem etiqueta.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../services/api", () => ({ default: api }));

const sessao = vi.hoisted(() => ({ switchActiveCompany: vi.fn() }));
vi.mock("../contexts/AuthContext", () => ({ useAuth: () => sessao }));

const navegar = vi.hoisted(() => vi.fn());
vi.mock("react-router-dom", async (original) => ({ ...(await original()), useNavigate: () => navegar }));

import GlobalSearchModal from "./GlobalSearchModal";

const RESPOSTA = {
  processes: [],
  clients: [
    {
      id: "c-precision", client_name: "Silva da Precision", has_process: false, process_count: 0, status: "novo",
      empresa: { company_id: "cmp-precision", company_name: "Precision Crédito", network_id: "rede-p", e_de_outra_rede: true },
    },
    {
      id: "c-domus", client_name: "Silva da Domus", has_process: false, process_count: 0, status: "novo",
      empresa: { company_id: "cmp-domus", company_name: "Domus", network_id: "rede-d", e_de_outra_rede: false },
    },
    { id: "c-sem", client_name: "Silva sem carimbo", has_process: false, process_count: 0, status: "novo", empresa: null },
  ],
  tasks: [],
};

async function pesquisar(u) {
  render(
    <MemoryRouter>
      <GlobalSearchModal open onOpenChange={() => {}} />
    </MemoryRouter>,
  );
  await u.type(screen.getByTestId("global-search-input"), "Silva");
  await screen.findByTestId("global-search-result-client-c-domus");
}

beforeEach(() => {
  api.get.mockReset();
  api.get.mockResolvedValue({ data: RESPOSTA });
  navegar.mockReset();
  sessao.switchActiveCompany.mockReset();
  window.history.replaceState(null, "", "/");
});

describe("GlobalSearchModal — selo de empresa", () => {
  it("cada resultado traz o selo da empresa dona", async () => {
    await pesquisar(userEvent.setup());
    expect(screen.getByTestId("global-search-empresa-client-c-precision")).toHaveTextContent("Precision Crédito");
    expect(screen.getByTestId("global-search-empresa-client-c-domus")).toHaveTextContent("Domus");
  });

  it("um resultado sem empresa aparece sem selo (nunca inventa um)", async () => {
    await pesquisar(userEvent.setup());
    expect(screen.queryByTestId("global-search-empresa-client-c-sem")).not.toBeInTheDocument();
  });
});

describe("GlobalSearchModal — abrir um resultado", () => {
  it("da empresa activa: navega, sem trocar de empresa", async () => {
    const u = userEvent.setup();
    await pesquisar(u);
    await u.click(screen.getByTestId("global-search-result-client-c-domus"));

    expect(navegar).toHaveBeenCalledWith("/cliente/c-domus");
    expect(sessao.switchActiveCompany).not.toHaveBeenCalled();
  });

  it("de OUTRA empresa: põe o destino no URL e troca de empresa, sem passar pelo router", async () => {
    const u = userEvent.setup();
    await pesquisar(u);
    await u.click(screen.getByTestId("global-search-result-client-c-precision"));

    await waitFor(() => expect(sessao.switchActiveCompany).toHaveBeenCalledWith("cmp-precision"));
    // O router renderizaria a ficha com a empresa errada (404): o destino vai para o URL e o
    // `reload` que a troca faz abre-o já com a empresa certa.
    expect(navegar).not.toHaveBeenCalled();
    expect(window.location.pathname).toBe("/cliente/c-precision");
  });

  it("um resultado sem empresa abre como sempre", async () => {
    const u = userEvent.setup();
    await pesquisar(u);
    await u.click(screen.getByTestId("global-search-result-client-c-sem"));

    expect(navegar).toHaveBeenCalledWith("/cliente/c-sem");
    expect(sessao.switchActiveCompany).not.toHaveBeenCalled();
  });
});
