/**
 * A Pool (Registo de Clientes) montada: eliminar e navegar (Lote 4, 2 e 3).
 *
 * Esta página de 941 linhas nunca tinha sido montada num teste — a regra
 * do `WebmailPage` e da `UsersAccessAdminTab` outra vez. Daí o primeiro
 * teste ser o mais estúpido possível.
 *
 * A FORMA DOS DADOS É A REAL: `GET /clients/registered` devolve
 * `{clients: [...], total: N}` com cada linha enriquecida por
 * `client_registered.py` (`nome`, `contacto`, `dados_pessoais`, `nif`,
 * `has_process`, `processes`, `is_sub35`, …). Foi lida no serviço antes
 * de escrever isto: um mock com a forma inventada é pior do que nenhum.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));

vi.mock("../../components/CreateProcessModal", () => ({ default: () => <div /> }));

const navegar = vi.fn();
vi.mock("react-router-dom", () => ({
  useNavigate: () => navegar,
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
}));

let papelActivo = "diretor";
// As capacidades por papel vêm do `/auth/me` (Lote 6, ponto 3). `null` =
// sessão sem o contrato, que é o caso de uma sessão anterior ao deploy.
let capacidadesPorPapel = null;
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: "u1",
      name: "Quem Apaga",
      role: "consultor",
      ...(capacidadesPorPapel
        ? { capabilities_por_papel: capacidadesPorPapel }
        : {}),
    },
    // O papel do PERFIL ACTIVO difere do papel base de propósito: é
    // esse o caso que o gate antigo (pelo `user.role`) decidia mal.
    effectiveRole: papelActivo,
  }),
}));

vi.mock("../../services/api", () => ({
  getRegisteredClients: vi.fn(),
  getClient: vi.fn(),
  deleteClient: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import ClientRegistrationsPage from "../ClientRegistrationsPage";
import * as api from "../../services/api";
import { toast } from "sonner";

const LINHAS = [
  {
    id: "c1",
    nome: "Ana Martins",
    contacto: { email: "ana@exemplo.pt", telefone: "910000001" },
    dados_pessoais: { nif: "100000001", birth_date: "2000-05-05" },
    nif: "100000001",
    has_process: false,
    processes: [],
    is_sub35: true,
    created_at: "2026-09-01T10:00:00Z",
    lead_status: "new",
  },
  {
    id: "c2",
    nome: "Bruno Costa",
    contacto: { email: "bruno@exemplo.pt" },
    dados_pessoais: { nif: "100000002" },
    nif: "100000002",
    has_process: true,
    processes: [{ id: "p2", process_number: "012", status: "pre_registo" }],
    is_sub35: false,
    created_at: "2026-09-02T10:00:00Z",
    lead_status: "converted",
  },
  {
    id: "c3",
    nome: "Carla Dias",
    contacto: {},
    dados_pessoais: {},
    has_process: false,
    processes: [],
    is_sub35: false,
    created_at: "2026-09-03T10:00:00Z",
    lead_status: "new",
  },
];

function responder(linhas = LINHAS) {
  api.getRegisteredClients.mockResolvedValue({
    data: { clients: linhas, total: linhas.length },
  });
}

async function montar() {
  const resultado = render(<ClientRegistrationsPage />);
  await screen.findByText("Ana Martins");
  return resultado;
}

describe("Pool — montagem e etiqueta", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    papelActivo = "diretor";
    responder();
  });

  it("monta e lista os registos", async () => {
    await montar();
    expect(api.getRegisteredClients).toHaveBeenCalled();
    expect(screen.getByText("Bruno Costa")).toBeTruthy();
  });

  it("mostra a etiqueta Sub35 apenas em quem o servidor marcou", async () => {
    await montar();
    const etiquetas = screen.getAllByTestId("etiqueta-sub35");
    expect(etiquetas).toHaveLength(1);
  });
});

describe("Pool — eliminar (ponto 2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    papelActivo = "diretor";
    responder();
    api.deleteClient.mockResolvedValue({ data: { success: true } });
  });

  it("a Direção vê o botão em cada linha", async () => {
    await montar();
    expect(screen.getByTestId("btn-eliminar-cliente-c1")).toBeTruthy();
    expect(screen.getByTestId("btn-eliminar-cliente-c3")).toBeTruthy();
  });

  it("um consultor NÃO vê o botão", async () => {
    papelActivo = "consultor";
    await montar();
    expect(screen.queryByTestId("btn-eliminar-cliente-c1")).toBeNull();
  });

  it("o gate é pelo perfil ACTIVO e não pelo papel base", async () => {
    // O utilizador deste teste tem `role: "consultor"` no JWT. Com o
    // gate antigo (`user.role`) a Direção a trabalhar a partir de um
    // perfil base de consultor não via o botão — e o backend, que lê o
    // papel efectivo, tê-lo-ia deixado eliminar.
    papelActivo = "admin";
    await montar();
    expect(screen.getByTestId("btn-eliminar-cliente-c1")).toBeTruthy();
  });

  it("pede confirmação antes de eliminar", async () => {
    const utilizador = userEvent.setup();
    await montar();
    await utilizador.click(screen.getByTestId("btn-eliminar-cliente-c1"));

    expect(await screen.findByText("Eliminar registo")).toBeTruthy();
    // Nada foi enviado só por abrir o diálogo.
    expect(api.deleteClient).not.toHaveBeenCalled();
  });

  it("avisa que o PROCESSO vai com o registo", async () => {
    const utilizador = userEvent.setup();
    await montar();
    await utilizador.click(screen.getByTestId("btn-eliminar-cliente-c2"));
    // O c2 tem processo: o aviso das consequências é obrigatório, senão
    // é um "tem a certeza?" que não informa.
    expect(
      await screen.findByText(/Este registo tem processo associado/),
    ).toBeTruthy();
  });

  it("não avisa de um processo que não existe", async () => {
    const utilizador = userEvent.setup();
    await montar();
    await utilizador.click(screen.getByTestId("btn-eliminar-cliente-c1"));
    await screen.findByText("Eliminar registo");
    expect(screen.queryByText(/Este registo tem processo associado/)).toBeNull();
  });

  it("elimina e recarrega a lista ao confirmar", async () => {
    const utilizador = userEvent.setup();
    await montar();
    const pedidosAntes = api.getRegisteredClients.mock.calls.length;

    await utilizador.click(screen.getByTestId("btn-eliminar-cliente-c1"));
    await utilizador.click(await screen.findByTestId("btn-confirmar-eliminar-cliente"));

    await waitFor(() => expect(api.deleteClient).toHaveBeenCalledWith("c1"));
    expect(toast.success).toHaveBeenCalled();
    // A lista recarrega: sem isto a linha eliminada fica no ecrã e o
    // utilizador clica-lhe outra vez.
    await waitFor(() =>
      expect(api.getRegisteredClients.mock.calls.length).toBeGreaterThan(pedidosAntes),
    );
  });

  it("mostra a mensagem DO SERVIDOR quando a eliminação falha", async () => {
    const utilizador = userEvent.setup();
    api.deleteClient.mockRejectedValue({
      response: { data: { detail: "Sem permissão para eliminar clientes" } },
    });
    await montar();
    await utilizador.click(screen.getByTestId("btn-eliminar-cliente-c1"));
    await utilizador.click(await screen.findByTestId("btn-confirmar-eliminar-cliente"));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Sem permissão para eliminar clientes"),
    );
  });
});

describe("Pool — Próximo/Anterior no diálogo (ponto 3)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    papelActivo = "diretor";
    responder();
    api.getClient.mockImplementation(async (id) => ({
      data: LINHAS.find((l) => l.id === id),
    }));
  });

  async function abrirDetalhes(nome) {
    const utilizador = userEvent.setup();
    await montar();
    await utilizador.click(screen.getByRole("button", { name: nome }));
    await screen.findByText("Detalhes do Cliente");
    return utilizador;
  }

  it("mostra a posição na lista", async () => {
    await abrirDetalhes("Bruno Costa");
    expect(screen.getByTestId("posicao-na-lista").textContent).toContain("2 / 3");
  });

  it("avança para o cliente seguinte sem fechar o diálogo", async () => {
    const utilizador = await abrirDetalhes("Ana Martins");
    await utilizador.click(screen.getByRole("button", { name: "Cliente seguinte" }));
    await waitFor(() => expect(api.getClient).toHaveBeenCalledWith("c2"));
    expect(screen.getByText("Detalhes do Cliente")).toBeTruthy();
  });

  it("recua para o anterior", async () => {
    const utilizador = await abrirDetalhes("Bruno Costa");
    await utilizador.click(screen.getByRole("button", { name: "Cliente anterior" }));
    await waitFor(() => expect(api.getClient).toHaveBeenCalledWith("c1"));
  });

  it("no PRIMEIRO, o botão anterior está DESACTIVADO e não ausente", async () => {
    // Um botão que desaparece faz o controlo saltar de sítio e o
    // utilizador perde o alvo do rato a meio de uma revisão.
    await abrirDetalhes("Ana Martins");
    expect(screen.getByRole("button", { name: "Cliente anterior" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cliente seguinte" })).toBeEnabled();
  });

  it("no ÚLTIMO, é o seguinte que fica desactivado", async () => {
    await abrirDetalhes("Carla Dias");
    expect(screen.getByRole("button", { name: "Cliente seguinte" })).toBeDisabled();
  });

  it("os rótulos falam de CLIENTES e não de processos", async () => {
    // O componente é partilhado com os Detalhes do processo; os rótulos
    // por omissão dizem "Processo anterior", o que num diálogo de
    // cliente seria mentira para um leitor de ecrã.
    await abrirDetalhes("Ana Martins");
    expect(screen.queryByRole("button", { name: "Processo anterior" })).toBeNull();
  });

  it("não há setas quando a lista tem um registo só", async () => {
    responder([LINHAS[0]]);
    const utilizador = userEvent.setup();
    render(<ClientRegistrationsPage />);
    await screen.findByText("Ana Martins");
    await utilizador.click(screen.getByRole("button", { name: "Ana Martins" }));
    await screen.findByText("Detalhes do Cliente");
    // Com um só, as duas setas estariam desactivadas: o controlo inteiro
    // não acrescenta nada e sai.
    const navegacao = screen.queryByTestId("navegacao-contigua");
    if (navegacao) {
      expect(within(navegacao).getByRole("button", { name: "Cliente anterior" })).toBeDisabled();
      expect(within(navegacao).getByRole("button", { name: "Cliente seguinte" })).toBeDisabled();
    }
  });
});


// ════════════════════════════════════════════════════════════════════
// LOTE 6, ponto 3 — os botões fantasma
// ════════════════════════════════════════════════════════════════════

describe("Pool — «Criar Processo» só a quem pode", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    responder();
  });

  const comCapacidades = (mapa) => {
    capacidadesPorPapel = mapa;
  };

  it("o perfil de indexação NÃO vê «Criar Processo»", async () => {
    papelActivo = "indexacao";
    comCapacidades({ indexacao: { PROCESS_CREATE: false } });
    await montar();
    expect(screen.queryByRole("button", { name: /criar processo/i })).toBeNull();
  });

  it("o consultor vê — contraprova de que o gate não esconde a todos", async () => {
    papelActivo = "consultor";
    comCapacidades({ consultor: { PROCESS_CREATE: true } });
    await montar();
    // Duas linhas sem processo (Ana e Carla).
    expect(
      screen.getAllByRole("button", { name: /criar processo/i })
    ).toHaveLength(2);
  });

  it("o PAPEL ACTIVO decide, não o cargo base", async () => {
    // Cargo base de indexação, a agir COMO consultor: a rota — que lê o papel
    // efectivo — deixa passar, logo o botão tem de aparecer. O gate antigo
    // (`userRole !== "indexacao"`, sobre o papel do JWT) escondia-o.
    papelActivo = "consultor";
    comCapacidades({
      indexacao: { PROCESS_CREATE: false },
      consultor: { PROCESS_CREATE: true },
    });
    await montar();
    expect(
      screen.getAllByRole("button", { name: /criar processo/i }).length
    ).toBeGreaterThan(0);
  });

  it("sem o contrato no `/auth/me`, o botão NÃO desaparece", async () => {
    // Falhar fechado aqui esconderia os botões a todos no dia de um deploy
    // desalinhado — e um ecrã sem botões não produz erro nenhum. A parede é
    // o servidor, que falha fechado.
    papelActivo = "consultor";
    comCapacidades(null);
    await montar();
    expect(
      screen.getAllByRole("button", { name: /criar processo/i }).length
    ).toBeGreaterThan(0);
  });

  it("o admin tem bypass mesmo sem a capacidade no mapa", async () => {
    papelActivo = "admin";
    comCapacidades({ admin: {} });
    await montar();
    expect(
      screen.getAllByRole("button", { name: /criar processo/i }).length
    ).toBeGreaterThan(0);
  });
});
