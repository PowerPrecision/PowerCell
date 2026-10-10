/**
 * Portal do Parceiro MONTADO — o «olho» das palavras-passe e a vista noturna.
 *
 * Monta a árvore REAL com o `ThemeProvider` real: o botão tem de chegar à
 * classe `dark` do `<html>` e à preferência guardada, e não apenas existir.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import convite from "@/test/fixtures/parceiro/convite.json";

vi.mock("@/services/partnerApi", () => ({
  entrar: vi.fn(),
  obterPerfil: vi.fn(),
  lerConvite: vi.fn(),
  aceitarConvite: vi.fn(),
  mudarPalavraPasse: vi.fn(),
  obterPainel: vi.fn(),
  listarCasos: vi.fn(),
  obterCaso: vi.fn(),
  submeterLead: vi.fn(),
  obterUrlDeDescarga: vi.fn(),
  enviarFicheiro: vi.fn(),
  obterFormularioDoCliente: vi.fn(),
  guardarFormularioDoCliente: vi.fn(),
}));

import * as api from "@/services/partnerApi";
import PartnerPortalRoutes from "@/pages/partner/PartnerPortalRoutes";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { guardarSessao } from "@/utils/partnerSession";
import { prepararApi } from "./montagem";

const raiz = () => document.documentElement;

function montarComTema(rota, { autenticado = false } = {}) {
  sessionStorage.clear();
  if (autenticado) guardarSessao("tok-de-teste", 3600);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0, gcTime: 0 } } });
  return render(
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[rota]}>
          <Routes>
            <Route path="/parceiro/*" element={<PartnerPortalRoutes />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

beforeEach(() => {
  prepararApi();
  localStorage.clear();
  raiz().classList.remove("dark");
  // O ThemeProvider segue o sistema quando não há escolha: aqui, claro.
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
});
afterEach(() => raiz().classList.remove("dark"));

describe("o «olho» da palavra-passe", () => {
  it("o login mostra e oculta a palavra-passe", async () => {
    montarComTema("/parceiro/entrar");
    const campo = await screen.findByLabelText("Palavra-passe");
    expect(campo).toHaveAttribute("type", "password");
    await userEvent.type(campo, "Segredo#2026");

    await userEvent.click(screen.getByRole("button", { name: "Mostrar palavra-passe" }));
    expect(screen.getByLabelText("Palavra-passe")).toHaveAttribute("type", "text");
    expect(screen.getByLabelText("Palavra-passe")).toHaveValue("Segredo#2026");

    await userEvent.click(screen.getByRole("button", { name: "Ocultar palavra-passe" }));
    expect(screen.getByLabelText("Palavra-passe")).toHaveAttribute("type", "password");
  });

  it("o olho do login não submete o formulário (não inicia sessão)", async () => {
    montarComTema("/parceiro/entrar");
    await userEvent.type(await screen.findByLabelText("Email"), "rui@parceiros.pt");
    await userEvent.type(screen.getByLabelText("Palavra-passe"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Mostrar palavra-passe" }));
    expect(api.entrar).not.toHaveBeenCalled();
  });

  it("o ecrã de boas-vindas (convite) tem um olho em cada campo, independentes", async () => {
    api.lerConvite.mockResolvedValue(convite);
    montarComTema("/parceiro/convite/abc123");
    // O título existe de imediato; o formulário só quando o convite chega.
    await screen.findByLabelText("Palavra-passe");

    const olhos = screen.getAllByRole("button", { name: "Mostrar palavra-passe" });
    expect(olhos).toHaveLength(2);
    await userEvent.click(olhos[0]);
    expect(screen.getByLabelText("Palavra-passe")).toHaveAttribute("type", "text");
    expect(screen.getByLabelText("Repetir palavra-passe")).toHaveAttribute("type", "password");
  });

  it("a página da conta tem o olho nos três campos", async () => {
    montarComTema("/parceiro/conta", { autenticado: true });
    await screen.findByLabelText("Palavra-passe actual");
    expect(screen.getAllByRole("button", { name: "Mostrar palavra-passe" })).toHaveLength(3);
  });
});

describe("a vista noturna", () => {
  it("o login e o convite têm o botão, e o parceiro abre em claro por omissão", async () => {
    montarComTema("/parceiro/entrar");
    expect(await screen.findByRole("button", { name: "Ativar vista noturna" })).toBeInTheDocument();
    expect(raiz().classList.contains("dark")).toBe(false);
  });

  it("o convite também tem o botão", async () => {
    api.lerConvite.mockResolvedValue(convite);
    montarComTema("/parceiro/convite/abc123");
    expect(await screen.findByRole("button", { name: "Ativar vista noturna" })).toBeInTheDocument();
  });

  it("clicar liga o escuro no <html>, guarda a escolha e volta a desligar", async () => {
    montarComTema("/parceiro/entrar");
    await userEvent.click(await screen.findByRole("button", { name: "Ativar vista noturna" }));
    expect(raiz().classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("theme")).toBe("dark");

    await userEvent.click(screen.getByRole("button", { name: "Desativar vista noturna" }));
    expect(raiz().classList.contains("dark")).toBe(false);
    expect(localStorage.getItem("theme")).toBe("light");
  });

  it("a área reservada (com sessão) tem o botão no cabeçalho", async () => {
    montarComTema("/parceiro", { autenticado: true });
    const cabecalho = (await screen.findByRole("banner"));
    expect(within(cabecalho).getByRole("button", { name: "Ativar vista noturna" })).toBeInTheDocument();
  });
});
