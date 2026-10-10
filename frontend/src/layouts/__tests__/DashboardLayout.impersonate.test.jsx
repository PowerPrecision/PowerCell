/**
 * O menu lateral em impersonate espelha o do utilizador-alvo (Bloco 4, ponto 33).
 *
 * "Ao usar o impersonate, os menus de administração devem ficar ocultos,
 * mesmo que quem o activou seja Admin. O ambiente tem de espelhar
 * exactamente e apenas o que o utilizador-alvo vê."
 *
 * A propriedade que se afirma é a ESPELHAÇÃO, não uma lista de proibidos:
 * para cada perfil-alvo, as ligações do menu de um administrador a "ver
 * como" esse perfil são exactamente as do mesmo perfil com sessão própria.
 * Uma lista de exclusão (`sem /admin`) passava com um menu amputado e
 * deixava de apanhar o item de administração que se acrescente amanhã.
 *
 * Monta o `DashboardLayout` REAL sobre o `AuthProvider` REAL — só o
 * `services/api` e os filhos pesados (sino, chat, pesquisa) são falseados.
 */
import { render, screen, waitFor, act, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const PERFIS = {
  consultor: { id: "u-c", name: "Carlos", email: "c@x.pt", role: "consultor" },
  intermediario: { id: "u-i", name: "Inês", email: "i@x.pt", role: "intermediario" },
  diretor: { id: "u-d", name: "Diana", email: "d@x.pt", role: "diretor" },
  administrativo: { id: "u-a", name: "Artur", email: "a@x.pt", role: "administrativo" },
  indexacao: { id: "u-x", name: "Xavier", email: "x@x.pt", role: "indexacao" },
  ceo: { id: "u-ceo", name: "Cátia", email: "ceo@x.pt", role: "ceo" },
};
const ADMIN = { id: "adm", name: "Admin", email: "admin@x.pt", role: "admin" };

let sessao; // quem responde ao /auth/me
let alvo; // quem o impersonate devolve

vi.mock("../../services/api", () => ({
  default: {
    get: vi.fn(async (url) => (String(url).includes("/auth/me") ? { data: sessao } : { data: {} })),
    post: vi.fn(async (url) => {
      if (String(url).includes("/admin/impersonate/")) {
        sessao = { ...alvo, is_impersonated: true, impersonated_by_name: "Admin" };
        return { data: { access_token: "tok-alvo", user: { ...alvo, is_impersonated: true, impersonated_by_name: "Admin" } } };
      }
      return { data: {} };
    }),
    defaults: { headers: { common: {} } },
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
  syncAuthContextHeaders: vi.fn(),
  setAuthToken: vi.fn(),
  clearAuthToken: vi.fn(),
  getRefreshedToken: vi.fn(async () => null),
}));

vi.mock("../../contexts/ThemeContext", () => ({
  useTheme: () => ({ toggleTheme: vi.fn(), isDark: false }),
}));
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

function montar() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/staff"]}>
        <AuthProvider>
          <Espiao />
          <DashboardLayout title="Teste"><div>conteúdo</div></DashboardLayout>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/**
 * Todas as ligações do menu lateral (a barra, não o cabeçalho).
 *
 * Os grupos são `Collapsible`: fechados, o conteúdo nem está na árvore. Sem
 * os abrir, o teste compararia só o que por acaso está aberto — e um item
 * de administração dentro de um grupo fechado passava despercebido.
 */
function ligacoesDoMenu(container) {
  const aside = container.querySelector("aside");
  aside?.querySelectorAll('button[aria-expanded="false"]').forEach((b) => fireEvent.click(b));
  const hrefs = new Set();
  aside?.querySelectorAll("a[href]").forEach((a) => hrefs.add(a.getAttribute("href")));
  return [...hrefs].sort();
}

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  localStorage.setItem("token", "tok");
});
afterEach(() => vi.clearAllMocks());

async function menuComSessaoPropria(perfil) {
  sessao = { ...PERFIS[perfil] };
  sessionStorage.setItem("activeRole", perfil);
  const { container, unmount } = montar();
  await waitFor(() => expect(auth.effectiveRole).toBe(perfil));
  await waitFor(() => expect(auth.user?.id).toBe(PERFIS[perfil].id));
  const ligacoes = ligacoesDoMenu(container);
  unmount();
  return ligacoes;
}

async function menuEmImpersonate(perfil) {
  sessao = { ...ADMIN };
  alvo = PERFIS[perfil];
  sessionStorage.setItem("activeRole", "admin");
  const { container, unmount } = montar();
  await waitFor(() => expect(auth.effectiveRole).toBe("admin"));
  await act(async () => { await auth.impersonate(alvo.id); });
  await waitFor(() => expect(auth.isImpersonating).toBe(true));
  await waitFor(() => expect(auth.effectiveRole).toBe(perfil));
  const ligacoes = ligacoesDoMenu(container);
  unmount();
  return ligacoes;
}

describe("impersonate espelha o menu do alvo", () => {
  it.each(Object.keys(PERFIS))("o menu de um admin a ver como %s é igual ao da sessão própria", async (perfil) => {
    const proprio = await menuComSessaoPropria(perfil);
    const emImpersonate = await menuEmImpersonate(perfil);

    expect(proprio.length).toBeGreaterThan(0);
    expect(emImpersonate).toEqual(proprio);
  });

  it.each(["consultor", "intermediario", "diretor", "administrativo", "indexacao"])(
    "um admin a ver como %s não vê NENHUM menu de administração",
    async (perfil) => {
      const ligacoes = await menuEmImpersonate(perfil);

      expect(ligacoes.filter((h) => h.startsWith("/admin") || h === "/system-admin")).toEqual([]);
      expect(screen.queryByText("Painel de Administração")).toBeNull();
    },
  );

  it("contraprova: o mesmo admin SEM impersonate vê os menus de administração", async () => {
    // Sem isto, "nenhuma ligação /admin" passava com um menu sempre vazio.
    sessao = { ...ADMIN };
    sessionStorage.setItem("activeRole", "admin");
    const { container } = montar();
    await waitFor(() => expect(auth.effectiveRole).toBe("admin"));
    await waitFor(() => expect(ligacoesDoMenu(container).some((h) => h.startsWith("/admin"))).toBe(true));
    expect(ligacoesDoMenu(container)).toContain("/system-admin");
  });

  it("um CEO como alvo mantém os SEUS menus de administração (espelha, não amputa)", async () => {
    const ligacoes = await menuEmImpersonate("ceo");
    expect(ligacoes).toContain("/system-admin");
    expect(ligacoes).toContain("/admin/desempenho");
  });
});
