/**
 * O menu lateral não se «fecha» ao receber um clique (QA Index, Out 2026).
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
  consultor: { id: "u-c", name: "Carlos", email: "c@x.pt", role: "consultor" },
  indexacao: { id: "u-x", name: "Xavier", email: "x@x.pt", role: "indexacao" },
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
const ROTAS = ["/staff", "/index", "/index/pesquisa", "/index/:id", "/validades", "/kanban", "/processos", "/clientes", "/ficheiros"];
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

function montar(rotaInicial, perfil) {
  sessao = { ...PERFIS[perfil] };
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
const cabecalhoDoGrupo = (nome) => within(barra()).getByRole("button", { name: new RegExp(nome) });
const ligacaoNaBarra = (nome) => within(barra()).queryByRole("link", { name: nome });

async function pronto(perfil) {
  await waitFor(() => expect(auth.effectiveRole).toBe(perfil));
  await waitFor(() => expect(auth.user?.id).toBe(PERFIS[perfil].id));
}

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  localStorage.setItem("token", "tok");
});
afterEach(() => vi.clearAllMocks());

describe("o grupo da rota activa abre-se, qualquer que seja a rota", () => {
  it("Index na pesquisa avançada: «Listas de Trabalho» aberto e a ligação à vista (antes: recolhido)", async () => {
    montar("/index/pesquisa", "indexacao");
    await pronto("indexacao");
    expect(cabecalhoDoGrupo("Listas de Trabalho")).toHaveAttribute("aria-expanded", "true");
    expect(ligacaoNaBarra("Pesquisa Avançada")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Indexação" })).not.toBeInTheDocument(); // o menu isolado saiu
  });

  it("Index em /validades (rota que nenhuma lista à mão conhecia)", async () => {
    montar("/validades", "indexacao");
    await pronto("indexacao");
    expect(cabecalhoDoGrupo("Listas de Trabalho")).toHaveAttribute("aria-expanded", "true");
    expect(ligacaoNaBarra("Documentos Pendentes")).toBeInTheDocument();
  });

  it("a bancada do Index (/index/:id) abre o grupo de «Os Meus Processos», a que pertence", async () => {
    montar("/index/p-1", "indexacao");
    await pronto("indexacao");
    expect(cabecalhoDoGrupo("Listas de Trabalho")).toHaveAttribute("aria-expanded", "true");
  });

  it("contraprova: numa rota sem grupo (/staff) nenhum grupo se abre sozinho", async () => {
    montar("/staff", "consultor");
    await pronto("consultor");
    for (const g of ["O Meu Negócio", "Visão Global", "Comunicações e Ficheiros"]) {
      expect(cabecalhoDoGrupo(g)).toHaveAttribute("aria-expanded", "false");
    }
  });
});

describe("clicar numa ligação NÃO recolhe o menu", () => {
  it("abrir um grupo e clicar numa ligação sua: depois de mudar de página o grupo continua aberto", async () => {
    montar("/staff", "consultor");
    await pronto("consultor");
    await userEvent.click(cabecalhoDoGrupo("O Meu Negócio"));
    await userEvent.click(ligacaoNaBarra("Documentos Pendentes"));

    // a página mudou (outro layout montado) e o menu mantém-se aberto e navegável
    await waitFor(() => expect(screen.getByTestId("pagina")).toHaveTextContent("/validades"));
    expect(cabecalhoDoGrupo("O Meu Negócio")).toHaveAttribute("aria-expanded", "true");
    expect(ligacaoNaBarra("Os Meus Processos")).toBeInTheDocument();
  });

  it("e dá para continuar a navegar dentro do mesmo grupo, página após página", async () => {
    montar("/staff", "consultor");
    await pronto("consultor");
    await userEvent.click(cabecalhoDoGrupo("O Meu Negócio"));
    await userEvent.click(ligacaoNaBarra("Documentos Pendentes"));
    await waitFor(() => expect(screen.getByTestId("pagina")).toHaveTextContent("/validades"));
    await userEvent.click(ligacaoNaBarra("Quadro Geral"));
    await waitFor(() => expect(screen.getByTestId("pagina")).toHaveTextContent("/kanban"));
    await userEvent.click(ligacaoNaBarra("Os Meus Processos"));
    await waitFor(() => expect(screen.getByTestId("pagina")).toHaveTextContent("/processos"));
    expect(cabecalhoDoGrupo("O Meu Negócio")).toHaveAttribute("aria-expanded", "true");
  });

  it("o que a pessoa abriu noutro grupo também sobrevive à navegação", async () => {
    montar("/staff", "consultor");
    await pronto("consultor");
    await userEvent.click(cabecalhoDoGrupo("Comunicações e Ficheiros"));
    await userEvent.click(cabecalhoDoGrupo("O Meu Negócio"));
    await userEvent.click(ligacaoNaBarra("Documentos Pendentes"));
    await waitFor(() => expect(screen.getByTestId("pagina")).toHaveTextContent("/validades"));
    expect(cabecalhoDoGrupo("Comunicações e Ficheiros")).toHaveAttribute("aria-expanded", "true");
    expect(cabecalhoDoGrupo("O Meu Negócio")).toHaveAttribute("aria-expanded", "true");
  });

  it("o que a pessoa FECHOU de propósito continua fechado (só se abre o da rota)", async () => {
    montar("/staff", "consultor");
    await pronto("consultor");
    await userEvent.click(cabecalhoDoGrupo("Visão Global"));
    await userEvent.click(cabecalhoDoGrupo("Visão Global")); // fecha outra vez
    await userEvent.click(cabecalhoDoGrupo("O Meu Negócio"));
    await userEvent.click(ligacaoNaBarra("Documentos Pendentes"));
    await waitFor(() => expect(screen.getByTestId("pagina")).toHaveTextContent("/validades"));
    expect(cabecalhoDoGrupo("Visão Global")).toHaveAttribute("aria-expanded", "false");
  });

  it("clicar no cabeçalho de um grupo abre e fecha-o (o toggle funciona)", async () => {
    montar("/staff", "consultor");
    await pronto("consultor");
    const g = () => cabecalhoDoGrupo("Visão Global");
    expect(g()).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(g());
    expect(g()).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(g());
    expect(g()).toHaveAttribute("aria-expanded", "false");
  });

  it("clicar numa ligação de dentro do grupo não o fecha na própria página", async () => {
    montar("/index/pesquisa", "indexacao");
    await pronto("indexacao");
    await userEvent.click(ligacaoNaBarra("Quadro Geral"));
    await waitFor(() => expect(screen.getByTestId("pagina")).toHaveTextContent("/kanban"));
    expect(cabecalhoDoGrupo("Listas de Trabalho")).toHaveAttribute("aria-expanded", "true");
  });
});

describe("o armazenamento é opcional", () => {
  it("com o sessionStorage a falhar o menu monta e abre o grupo da rota", async () => {
    const original = Storage.prototype.getItem;
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (chave) {
      if (chave === "menu-seccoes-abertas") throw new Error("bloqueado");
      return original.call(this, chave);
    });
    montar("/index/pesquisa", "indexacao");
    await pronto("indexacao");
    expect(cabecalhoDoGrupo("Listas de Trabalho")).toHaveAttribute("aria-expanded", "true");
    vi.restoreAllMocks();
  });
});
