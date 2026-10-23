/**
 * «Supervisão do Index» não existe numa rede sem o módulo (caso Domus, Out 2026) — nem para o Master.
 *
 * Monta o layout REAL sobre o `AuthProvider` REAL; o `/auth/me` devolve `capabilities.has_index` como o
 * servidor (`_capacidades_da_empresa_em_vigor`). Mesma harness do `menuLateral.test.jsx`.
 *
 * (cabeçalho original: O menu lateral não se «fecha» ao receber um clique, QA Index, Out 2026).
 *
 * O `DashboardLayout` é montado POR PÁGINA: cada navegação desmonta um menu e monta outro. O estado
 * dos grupos vivia num `useState` do layout, logo todos os grupos recolhiam a cada clique numa ligação,
 * e só reabria o grupo cuja rota constava de uma lista escrita à mão — `/index` e `/validades`, do perfil
 * Index, não constavam em nenhuma.
 *
 * Monta o layout REAL, uma instância POR ROTA (como a aplicação), sobre o `AuthProvider` REAL; só a rede e
 * os filhos pesados (sino, chat, pesquisa) são falseados. Os testes de uma só montagem passavam com o
 * defeito presente: o que o prova é navegar de uma página para outra.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const PERFIS = {
  master: { id: "u-m", name: "Marta", email: "m@x.pt", role: "master" },
  diretor: { id: "u-d", name: "Diogo", email: "d@x.pt", role: "diretor" },
  ceo: { id: "u-e", name: "Elisa", email: "e@x.pt", role: "ceo" },
  admin: { id: "u-a", name: "Ana", email: "a@x.pt", role: "admin" },
};
let sessao;

vi.mock("../../services/api", () => ({
  default: {
    get: vi.fn(async (url) => (String(url).includes("/auth/me") ? { data: sessao } : { data: {} })),
    post: vi.fn(async () => ({ data: {} })),
    defaults: { headers: { common: {} } },
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
  syncAuthContextHeaders: vi.fn(),
  setAuthToken: vi.fn(),
  clearAuthToken: vi.fn(),
  getRefreshedToken: vi.fn(async () => null),
}));
vi.mock("../../contexts/ThemeContext", () => ({ useTheme: () => ({ toggleTheme: vi.fn(), isDark: false }) }));
vi.mock("../../components/NotificationsDropdown", () => ({ default: () => null }));
vi.mock("../../components/TasksDropdown", () => ({ default: () => null }));
vi.mock("../../components/ChatPanel", () => ({ default: () => null }));
vi.mock("../../components/GlobalSearchModal", () => ({ default: () => null }));
vi.mock("../../components/WelcomeConfigModal", () => ({ default: () => null }));
vi.mock("../../components/calculators/CalculatorHub", () => ({ default: () => null }));
vi.mock("../../hooks/useWebSocket", () => ({ useWebSocket: () => ({ isConnected: false }) }));
vi.mock("../../hooks/useNewEmailRealtime", () => ({ invalidateEmailQueries: vi.fn() }));

import { AuthProvider, useAuth } from "../../contexts/AuthContext";
import DashboardLayout from "../DashboardLayout";

let auth;
function Espiao() {
  auth = useAuth();
  return null;
}

// UMA instância do layout por rota, como em App.js: cada página é um COMPONENTE DIFERENTE e monta o seu
// layout. Com o mesmo componente em todas as rotas o React reaproveitava a instância (e o estado dos
// grupos) entre páginas — e o teste passava com o defeito presente.
const ROTAS = ["/staff"];
const PAGINAS = Object.fromEntries(
  ROTAS.map((rota) => [
    rota,
    function PaginaDaRota() {
      return (
        <DashboardLayout title={rota}>
          <div data-testid="pagina">{rota}</div>
        </DashboardLayout>
      );
    },
  ]),
);

function montar(rotaInicial, perfil, capabilities) {
  sessao = { ...PERFIS[perfil], ...(capabilities ? { capabilities } : {}) };
  sessionStorage.setItem("activeRole", perfil);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const resultado = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[rotaInicial]}>
        <AuthProvider>
          <Espiao />
          <Routes>
            {ROTAS.map((r) => {
              const Pagina = PAGINAS[r];
              return <Route key={r} path={r} element={<Pagina />} />;
            })}
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return resultado;
}

const barra = () => document.querySelector("aside");
const supervisao = () => within(barra()).queryByRole("link", { name: "Supervisão do Index" });

async function pronto(perfil) {
  await waitFor(() => expect(auth.effectiveRole).toBe(perfil));
  await waitFor(() => expect(auth.user?.id).toBe(PERFIS[perfil].id));
}

async function abrirTudo() {
  const utilizador = userEvent.setup();
  for (const botao of within(barra()).queryAllByRole("button")) {
    if (botao.getAttribute("aria-expanded") === "false") await utilizador.click(botao);
  }
}

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  localStorage.setItem("token", "tok");
});
afterEach(() => vi.clearAllMocks());

describe.each(["diretor", "master", "ceo", "admin"])("%s", (perfil) => {
  it("rede COM Index: a supervisão está no menu", async () => {
    montar("/staff", perfil, { has_index: true });
    await pronto(perfil);
    await abrirTudo();
    expect(supervisao()).toBeInTheDocument();
  });

  it("rede SEM Index: a supervisão sai do menu", async () => {
    montar("/staff", perfil, { has_index: false });
    await pronto(perfil);
    await abrirTudo();
    expect(supervisao()).not.toBeInTheDocument();
    // o resto do menu continua lá — não se escondeu o grupo inteiro
    expect(within(barra()).getAllByRole("link").length).toBeGreaterThan(1);
  });

  it("sessão anterior ao deploy (sem o campo): falha ABERTA, a supervisão fica à vista", async () => {
    montar("/staff", perfil, undefined);
    await pronto(perfil);
    await abrirTudo();
    expect(supervisao()).toBeInTheDocument();
  });
});
