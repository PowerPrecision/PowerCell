/**
 * P1/P2 — a lista de registos com leads de parceiro: ESTADO só com a badge, acções na coluna
 * ACÇÕES e «Ver Detalhes da Lead» com tudo o que o parceiro submeteu.
 *
 * A forma dos dados é a REAL (`client_registered.py`: `validacao_financeira` é o ESTADO em texto na
 * lista; `GET /financial-validation/lead/{id}/details` devolve a lista positiva de
 * `financial_validation.run_detalhes_da_lead`). Os valores do fixture são diferentes das omissões.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));
vi.mock("../../components/CreateProcessModal", () => ({
  default: ({ open, preSelectedClient }) => (open ? <div data-testid="modal-criar-processo">{preSelectedClient?.name}</div> : null),
}));

let parametros = "";
const definirParametros = vi.fn();
vi.mock("react-router-dom", () => ({
  useNavigate: () => vi.fn(),
  useSearchParams: () => [new URLSearchParams(parametros), definirParametros],
}));

let papelActivo = "diretor";
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "u1", name: "Quem Decide", role: "consultor" }, effectiveRole: papelActivo }),
}));

vi.mock("../../services/api", () => ({
  getRegisteredClients: vi.fn(),
  getClient: vi.fn(),
  deleteClient: vi.fn(),
  getPartnerOptions: vi.fn(),
  getLeadDetails: vi.fn(),
  decidirValidacaoFinanceira: vi.fn(),
  obterComprovativoDaValidacao: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

import ClientRegistrationsPage from "../ClientRegistrationsPage";
import * as api from "../../services/api";

const LEAD = {
  id: "c-lead",
  nome: "Rita Parceira",
  contacto: { email: "rita@exemplo.pt", telefone: "910000099" },
  dados_pessoais: { nif: "200000009" },
  nif: "200000009",
  has_process: false,
  processes: [],
  is_sub35: false,
  created_at: "2026-10-01T10:00:00Z",
  lead_status: "new",
  fonte: "partner_portal",
  parceiro_name: "Parceiro Alfa",
  validacao_financeira: "pendente",
};

const DETALHES = {
  id: "c-lead",
  nome: "Rita Parceira",
  contacto: { email: "rita@exemplo.pt", telefone: "910000099" },
  dados_pessoais: { nif: "200000009", profissao: "Engenheira Civil", email: "repetido@x.pt" },
  titular2_data: { nome: "Rui Parceiro" },
  dados_financeiros: { rendimento_mensal: 3120 },
  dados_imobiliarios: {},
  notas_do_parceiro: "Cliente com pressa — escritura em Dezembro",
  parceiro: { id: "par-1", nome: "Parceiro Alfa" },
  empresa_destino: "Power Real Estate",
  created_at: "2026-10-01T10:00:00Z",
  validacao: { estado: "pendente" },
  ficheiros: [
    { file_id: "f2", filename: "cc.pdf", category: "Identificação", uploaded_at: "2026-10-03", comprovativo: false },
    { file_id: "f1", filename: "pagamento.pdf", category: "Comprovativo de Pagamento", uploaded_at: "2026-10-02", comprovativo: true },
  ],
};

function responder(linhas = [LEAD], total = linhas.length) {
  api.getRegisteredClients.mockResolvedValue({ data: { clients: linhas, total } });
}

async function montar() {
  render(<ClientRegistrationsPage />);
  await screen.findAllByText("Rita Parceira");
}

beforeEach(() => {
  vi.clearAllMocks();
  papelActivo = "diretor";
  parametros = "";
  responder();
  api.getPartnerOptions.mockResolvedValue({ data: { partners: [{ id: "par-1", name: "Parceiro Alfa" }], total: 1 } });
  api.getLeadDetails.mockResolvedValue(DETALHES);
  api.decidirValidacaoFinanceira.mockResolvedValue({ success: true });
  api.obterComprovativoDaValidacao.mockResolvedValue({ url: "https://s3.exemplo/get" });
});

describe("ESTADO só com a badge; as acções na coluna ACÇÕES", () => {
  it("o estado é a badge «Não validado» e nenhum botão de decisão vive na mesma célula", async () => {
    await montar();
    const badge = screen.getByTestId("validacao-nao-validado");
    expect(badge).toHaveTextContent("Não validado");
    const celulaDoEstado = badge.parentElement;
    expect(within(celulaDoEstado).queryByTestId("validar-processo")).toBeNull();
    expect(within(celulaDoEstado).queryByTestId("rejeitar-processo")).toBeNull();
    expect(within(celulaDoEstado).queryByTestId("ver-comprovativo")).toBeNull();
    expect(within(celulaDoEstado).queryByRole("button")).toBeNull();
  });

  it("Validar, Rejeitar e Ver comprovativo estão no menu «⋯» da coluna ACÇÕES", async () => {
    const utilizador = userEvent.setup();
    await montar();
    const gatilho = screen.getByTestId("accoes-validacao-c-lead");
    expect(gatilho.closest("[data-testid]")).not.toBeNull();
    await utilizador.click(gatilho);
    expect(await screen.findByTestId("validar-processo")).toBeInTheDocument();
    expect(screen.getByTestId("rejeitar-processo")).toBeInTheDocument();
    expect(screen.getByTestId("ver-comprovativo")).toBeInTheDocument();
  });

  it("Validar no menu decide a lead e volta a pedir a lista", async () => {
    const utilizador = userEvent.setup();
    await montar();
    const pedidosAntes = api.getRegisteredClients.mock.calls.length;
    await utilizador.click(screen.getByTestId("accoes-validacao-c-lead"));
    await utilizador.click(await screen.findByTestId("validar-processo"));
    await waitFor(() => expect(api.decidirValidacaoFinanceira).toHaveBeenCalledWith("lead", "c-lead", { decision: "validate" }));
    await waitFor(() => expect(api.getRegisteredClients.mock.calls.length).toBeGreaterThan(pedidosAntes));
  });

  it("Ver comprovativo no menu abre o ficheiro", async () => {
    const utilizador = userEvent.setup();
    const abrir = vi.spyOn(window, "open").mockImplementation(() => null);
    await montar();
    await utilizador.click(screen.getByTestId("accoes-validacao-c-lead"));
    await utilizador.click(await screen.findByTestId("ver-comprovativo"));
    await waitFor(() => expect(abrir).toHaveBeenCalledWith("https://s3.exemplo/get", "_blank", "noopener,noreferrer"));
    abrir.mockRestore();
  });

  it.each(["consultor", "intermediario", "indexacao", "admin"])(
    "contraprova: %s vê a badge mas NÃO o menu de decisão",
    async (papel) => {
      papelActivo = papel;
      await montar();
      expect(screen.getByTestId("validacao-nao-validado")).toBeInTheDocument();
      expect(screen.queryByTestId("accoes-validacao-c-lead")).toBeNull();
    },
  );

  it("«Criar Processo» continua na coluna ACÇÕES, ao lado dos botões de decisão", async () => {
    await montar();
    const gatilho = screen.getByTestId("accoes-validacao-c-lead");
    const criar = screen.getAllByRole("button", { name: /criar processo/i })[0];
    expect(criar.parentElement).toBe(gatilho.parentElement);
  });
});

describe("«Ver Detalhes da Lead»", () => {
  const abrir = async () => {
    const utilizador = userEvent.setup();
    await montar();
    await utilizador.click(screen.getByTestId("btn-detalhes-lead-c-lead"));
    return utilizador;
  };

  it("abre a gaveta e mostra o que o parceiro submeteu", async () => {
    await abrir();
    const gaveta = await screen.findByTestId("lead-details-drawer");
    await within(gaveta).findByTestId("lead-bloco-contactos");
    expect(api.getLeadDetails).toHaveBeenCalledWith("c-lead");
    expect(within(gaveta).getByText("Parceiro Alfa")).toBeInTheDocument();
    expect(within(gaveta).getByText("Power Real Estate")).toBeInTheDocument();
    expect(within(gaveta).getByText("Engenheira Civil")).toBeInTheDocument();
    expect(within(gaveta).getByText("Rui Parceiro")).toBeInTheDocument();
    expect(within(gaveta).getByText("3120")).toBeInTheDocument();
    expect(within(gaveta).getByTestId("lead-bloco-notas")).toHaveTextContent("escritura em Dezembro");
  });

  it("não repete nos dados pessoais o que já está nos contactos", async () => {
    await abrir();
    const gaveta = await screen.findByTestId("lead-details-drawer");
    await within(gaveta).findByTestId("lead-bloco-contactos");
    expect(within(gaveta).queryByText("repetido@x.pt")).toBeNull();
  });

  it("lista os ficheiros com o comprovativo à cabeça e marcado", async () => {
    await abrir();
    const bloco = await screen.findByTestId("lead-bloco-ficheiros");
    const itens = within(bloco).getAllByRole("listitem");
    expect(itens).toHaveLength(2);
    expect(itens[0]).toHaveTextContent("pagamento.pdf");
    expect(itens[0]).toHaveTextContent("Comprovativo");
    expect(itens[1]).toHaveTextContent("cc.pdf");
  });

  it("o rodapé da gaveta tem Validar, Rejeitar, Ver comprovativo e Criar Processo", async () => {
    await abrir();
    const rodape = await screen.findByTestId("lead-details-accoes");
    expect(within(rodape).getByTestId("drawer-validar")).toBeInTheDocument();
    expect(within(rodape).getByTestId("drawer-rejeitar")).toBeInTheDocument();
    expect(within(rodape).getByTestId("drawer-ver-comprovativo")).toBeInTheDocument();
    expect(within(rodape).getByTestId("drawer-criar-processo")).toBeInTheDocument();
  });

  it("Validar na gaveta decide, fecha a gaveta e refaz a lista", async () => {
    const utilizador = await abrir();
    const pedidosAntes = api.getRegisteredClients.mock.calls.length;
    await utilizador.click(await screen.findByTestId("drawer-validar"));
    await waitFor(() => expect(api.decidirValidacaoFinanceira).toHaveBeenCalledWith("lead", "c-lead", { decision: "validate" }));
    await waitFor(() => expect(screen.queryByTestId("lead-details-drawer")).toBeNull());
    expect(api.getRegisteredClients.mock.calls.length).toBeGreaterThan(pedidosAntes);
  });

  it("Criar Processo na gaveta fecha-a e abre o diálogo de criação para ESSA lead", async () => {
    const utilizador = await abrir();
    await utilizador.click(await screen.findByTestId("drawer-criar-processo"));
    expect(await screen.findByTestId("modal-criar-processo")).toHaveTextContent("Rita Parceira");
    expect(screen.queryByTestId("lead-details-drawer")).toBeNull();
  });

  it("quem não decide vê os detalhes mas não as acções de decisão", async () => {
    papelActivo = "consultor";
    await abrir();
    const gaveta = await screen.findByTestId("lead-details-drawer");
    await within(gaveta).findByTestId("lead-bloco-contactos");
    expect(within(gaveta).queryByTestId("drawer-validar")).toBeNull();
    expect(within(gaveta).queryByTestId("drawer-ver-comprovativo")).toBeNull();
  });

  it("um erro de leitura diz-se; nunca se apresenta como «sem dados»", async () => {
    api.getLeadDetails.mockRejectedValue({ response: { data: { detail: "Não encontrado." } } });
    await abrir();
    expect(await screen.findByTestId("lead-details-erro")).toHaveTextContent("Não encontrado.");
    expect(screen.queryByTestId("lead-bloco-contactos")).toBeNull();
  });
});

describe("filtro «Por Parceiro» e paginação no servidor", () => {
  it("o filtro vem do URL para o pedido", async () => {
    parametros = "parceiro=par-1";
    await montar();
    const params = api.getRegisteredClients.mock.calls.at(-1)[0];
    expect(params.get("parceiro")).toBe("par-1");
  });

  it("sem filtro, o pedido não leva `parceiro`", async () => {
    await montar();
    expect(api.getRegisteredClients.mock.calls.at(-1)[0].has("parceiro")).toBe(false);
  });

  it("pede 50 por página (skip 0) e a página seguinte pede skip 50", async () => {
    const utilizador = userEvent.setup();
    responder([LEAD], 120);
    await montar();
    const primeiro = api.getRegisteredClients.mock.calls.at(-1)[0];
    expect(primeiro.get("limit")).toBe("50");
    expect(primeiro.get("skip")).toBe("0");
    await utilizador.click(await screen.findByTestId("paginacao-seguinte"));
    await waitFor(() => expect(api.getRegisteredClients.mock.calls.at(-1)[0].get("skip")).toBe("50"));
  });

  it("uma falha na lista de parceiros diz-se e não estraga a página", async () => {
    api.getPartnerOptions.mockRejectedValue(new Error("boom"));
    await montar();
    expect(await screen.findByTestId("filtro-parceiro-indisponivel")).toBeInTheDocument();
    expect(screen.getAllByText("Rita Parceira").length).toBeGreaterThan(0);
  });
});
