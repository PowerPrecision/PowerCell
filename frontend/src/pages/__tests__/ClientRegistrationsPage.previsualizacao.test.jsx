/**
 * «Visualizar» na gaveta de detalhes da lead: imagem e PDF desenhados DENTRO do painel, com limites
 * de tamanho e scroll. Monta a PÁGINA real (com a gaveta real e o `PreviewDoFicheiro` real); só a
 * fronteira de rede (`services/api`) é falsa — mas devolve Blobs a sério, pelo mesmo caminho
 * (`responseType: "blob"`) que o Axios usa em produção.
 *
 * O jsdom não tem `URL.createObjectURL` nem desenha imagens/PDF: afirma-se o que o ecrã ENTREGA ao
 * browser (o elemento certo, com o `src` do blob, o tipo do blob e os limites de layout). O render
 * efectivo num browser real foi verificado à parte (ver AGENTS.md).
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));
vi.mock("../../components/CreateProcessModal", () => ({ default: () => null }));
vi.mock("react-router-dom", () => ({
  useNavigate: () => vi.fn(),
  useSearchParams: () => [new URLSearchParams(""), vi.fn()],
}));
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "u1", name: "Quem Decide", role: "consultor" }, effectiveRole: "diretor" }),
}));
vi.mock("../../services/api", () => ({
  getRegisteredClients: vi.fn(),
  getClient: vi.fn(),
  deleteClient: vi.fn(),
  getPartnerOptions: vi.fn(),
  getLeadDetails: vi.fn(),
  getLeadFileContent: vi.fn(),
  decidirValidacaoFinanceira: vi.fn(),
  obterComprovativoDaValidacao: vi.fn(),
  // Igual ao real: lê o corpo de erro que veio como Blob.
  readBlobErrorBody: async (error) => {
    const corpo = error?.response?.data;
    if (!corpo) return {};
    if (corpo instanceof Blob) {
      try { return JSON.parse(await corpo.text()); } catch { return {}; }
    }
    return typeof corpo === "object" ? corpo : {};
  },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

import ClientRegistrationsPage from "../ClientRegistrationsPage";
import * as api from "../../services/api";

const LEAD = {
  id: "c-lead", nome: "Rita Parceira",
  contacto: { email: "rita@exemplo.pt", telefone: "910000099" },
  dados_pessoais: { nif: "200000009" }, nif: "200000009",
  has_process: false, processes: [], is_sub35: false,
  created_at: "2026-10-01T10:00:00Z", lead_status: "new", fonte: "partner_portal",
  parceiro_name: "Parceiro Alfa", validacao_financeira: "pendente",
};

const DETALHES = {
  id: "c-lead", nome: "Rita Parceira",
  contacto: { email: "rita@exemplo.pt", telefone: "910000099" },
  dados_pessoais: { nif: "200000009" }, titular2_data: {}, dados_financeiros: {}, dados_imobiliarios: {},
  parceiro: { id: "par-1", nome: "Parceiro Alfa" }, empresa_destino: "Power Real Estate",
  created_at: "2026-10-01T10:00:00Z", validacao: { estado: "pendente" },
  ficheiros: [
    { file_id: "f-png", filename: "Foto-Fachada.PNG", category: "Imóvel", uploaded_at: "2026-10-04", comprovativo: false, previsualizavel: true },
    { file_id: "f-pdf", filename: "pagamento.pdf", category: "Comprovativo de Pagamento", uploaded_at: "2026-10-02", comprovativo: true, previsualizavel: true },
    { file_id: "f-doc", filename: "contrato.docx", category: "Outros", uploaded_at: "2026-10-03", comprovativo: false, previsualizavel: false },
  ],
};

const blobsCriados = [];
const revogados = [];

async function abrirGaveta() {
  const utilizador = userEvent.setup();
  render(<ClientRegistrationsPage />);
  await screen.findAllByText("Rita Parceira");
  await utilizador.click(screen.getByTestId("btn-detalhes-lead-c-lead"));
  const gaveta = await screen.findByTestId("lead-details-drawer");
  const bloco = await within(gaveta).findByTestId("lead-bloco-ficheiros");
  return { utilizador, gaveta, bloco };
}

beforeEach(() => {
  vi.clearAllMocks();
  // O jsdom não tem `Blob.prototype.text` (os browsers têm); `readBlobErrorBody` depende dele.
  if (!Blob.prototype.text) {
    Blob.prototype.text = function text() {
      return new Promise((resolver, rejeitar) => {
        const leitor = new FileReader();
        leitor.onload = () => resolver(String(leitor.result));
        leitor.onerror = () => rejeitar(leitor.error);
        leitor.readAsText(this);
      });
    };
  }
  blobsCriados.length = 0;
  revogados.length = 0;
  let n = 0;
  URL.createObjectURL = vi.fn((blob) => {
    blobsCriados.push(blob);
    n += 1;
    return `blob:preview-${n}`;
  });
  URL.revokeObjectURL = vi.fn((u) => revogados.push(u));
  api.getRegisteredClients.mockResolvedValue({ data: { clients: [LEAD], total: 1 } });
  api.getPartnerOptions.mockResolvedValue({ data: { partners: [{ id: "par-1", name: "Parceiro Alfa" }], total: 1 } });
  api.getLeadDetails.mockResolvedValue(DETALHES);
  api.getLeadFileContent.mockImplementation(async (_lead, fileId) => ({
    data: new Blob([fileId === "f-png" ? "PNGBYTES" : "%PDF-1.4 bytes"], { type: "application/octet-stream" }),
  }));
});

describe("o botão «Visualizar»", () => {
  it("existe um por ficheiro pré-visualizável e o .docx diz que não tem pré-visualização", async () => {
    const { bloco } = await abrirGaveta();
    expect(within(bloco).getByRole("button", { name: "Visualizar Foto-Fachada.PNG" })).toBeInTheDocument();
    expect(within(bloco).getByRole("button", { name: "Visualizar pagamento.pdf" })).toBeInTheDocument();
    expect(within(bloco).queryByRole("button", { name: /contrato\.docx/ })).toBeNull();
    expect(within(bloco).getByTestId("lead-ficheiro-f-doc")).toHaveTextContent("Sem pré-visualização");
    // Nada é pedido ao servidor até alguém clicar.
    expect(api.getLeadFileContent).not.toHaveBeenCalled();
  });

  it("o servidor manda: um .pdf que ele diz não previsualizável não tem botão", async () => {
    api.getLeadDetails.mockResolvedValue({
      ...DETALHES,
      ficheiros: [{ file_id: "f-x", filename: "x.pdf", category: "Outros", previsualizavel: false }],
    });
    const { bloco } = await abrirGaveta();
    expect(within(bloco).queryByRole("button", { name: /Visualizar/ })).toBeNull();
    expect(within(bloco).getByText("Sem pré-visualização")).toBeInTheDocument();
  });
});

describe("imagem", () => {
  it("desenha um <img> com o blob, tipado pela extensão, dentro da área com limites e scroll", async () => {
    const { utilizador, gaveta, bloco } = await abrirGaveta();
    await utilizador.click(within(bloco).getByRole("button", { name: "Visualizar Foto-Fachada.PNG" }));

    const imagem = await within(gaveta).findByTestId("previsualizacao-imagem");
    expect(api.getLeadFileContent).toHaveBeenCalledWith("c-lead", "f-png");
    expect(imagem.tagName).toBe("IMG");
    expect(imagem).toHaveAttribute("src", "blob:preview-1");
    expect(imagem).toHaveAccessibleName("Pré-visualização de Foto-Fachada.PNG");
    // O tipo do blob é o NOSSO (extensão), não o `octet-stream` que a resposta trouxe.
    expect(blobsCriados[0].type).toBe("image/png");
    // Limites: a imagem nunca passa a largura do painel e o recipiente rola.
    expect(imagem.className).toMatch(/max-w-full/);
    const area = within(gaveta).getByTestId("previsualizacao-area");
    expect(area.className).toMatch(/max-h-\[60vh\]/);
    expect(area.className).toMatch(/overflow-auto/);
    expect(area.className).toMatch(/max-w-full/);
    expect(area).toContainElement(imagem);
    expect(within(gaveta).getByRole("button", { name: "Visualizar Foto-Fachada.PNG" })).toHaveAttribute("aria-pressed", "true");
  });
});

describe("PDF", () => {
  it("desenha um <iframe> com o blob application/pdf, de altura limitada, dentro da área com scroll", async () => {
    const { utilizador, gaveta, bloco } = await abrirGaveta();
    await utilizador.click(within(bloco).getByRole("button", { name: "Visualizar pagamento.pdf" }));

    const quadro = await within(gaveta).findByTestId("previsualizacao-pdf");
    expect(api.getLeadFileContent).toHaveBeenCalledWith("c-lead", "f-pdf");
    expect(quadro.tagName).toBe("IFRAME");
    expect(quadro).toHaveAttribute("src", "blob:preview-1");
    expect(quadro).toHaveAttribute("title", "Pré-visualização de pagamento.pdf");
    expect(blobsCriados[0].type).toBe("application/pdf");
    expect(quadro.className).toMatch(/h-\[60vh\]/);
    expect(quadro.className).toMatch(/w-full/);
    expect(within(gaveta).getByTestId("previsualizacao-area")).toContainElement(quadro);
    expect(within(gaveta).queryByTestId("previsualizacao-imagem")).toBeNull();
  });
});

describe("ciclo de vida", () => {
  it("só uma pré-visualização aberta de cada vez, e o blob anterior é libertado", async () => {
    const { utilizador, gaveta, bloco } = await abrirGaveta();
    await utilizador.click(within(bloco).getByRole("button", { name: "Visualizar Foto-Fachada.PNG" }));
    await within(gaveta).findByTestId("previsualizacao-imagem");

    await utilizador.click(within(bloco).getByRole("button", { name: "Visualizar pagamento.pdf" }));
    await within(gaveta).findByTestId("previsualizacao-pdf");

    expect(within(gaveta).getAllByTestId("previsualizacao")).toHaveLength(1);
    expect(within(gaveta).queryByTestId("previsualizacao-imagem")).toBeNull();
    expect(revogados).toContain("blob:preview-1");
  });

  it("«Fechar» e o botão «Visualizar» outra vez fecham e libertam o blob", async () => {
    const { utilizador, gaveta, bloco } = await abrirGaveta();
    await utilizador.click(within(bloco).getByRole("button", { name: "Visualizar pagamento.pdf" }));
    await within(gaveta).findByTestId("previsualizacao-pdf");

    await utilizador.click(within(gaveta).getByTestId("previsualizacao-fechar"));
    expect(within(gaveta).queryByTestId("previsualizacao")).toBeNull();
    expect(revogados).toEqual(["blob:preview-1"]);

    await utilizador.click(within(bloco).getByRole("button", { name: "Visualizar pagamento.pdf" }));
    await within(gaveta).findByTestId("previsualizacao-pdf");
    await utilizador.click(within(bloco).getByRole("button", { name: "Visualizar pagamento.pdf" }));
    expect(within(gaveta).queryByTestId("previsualizacao")).toBeNull();
    expect(revogados).toEqual(["blob:preview-1", "blob:preview-2"]);
  });
});

describe("falhas", () => {
  const recusa = (estado, detail) => {
    const corpo = detail ? new Blob([JSON.stringify({ detail })], { type: "application/json" }) : new Blob([]);
    return Object.assign(new Error("x"), { response: { status: estado, data: corpo } });
  };

  it("diz o motivo do servidor (lido do Blob de erro) e não desenha nada", async () => {
    api.getLeadFileContent.mockRejectedValue(recusa(413, "Ficheiro demasiado grande (limite 15 MB)."));
    const { utilizador, gaveta, bloco } = await abrirGaveta();
    await utilizador.click(within(bloco).getByRole("button", { name: "Visualizar pagamento.pdf" }));
    const alerta = await within(gaveta).findByRole("alert");
    expect(alerta).toHaveTextContent("Ficheiro demasiado grande (limite 15 MB).");
    expect(within(gaveta).queryByTestId("previsualizacao-pdf")).toBeNull();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });

  it.each([
    [404, "O ficheiro já não está disponível."],
    [403, "Sem permissão para ver este ficheiro."],
    [503, "Não foi possível carregar a pré-visualização."],
  ])("sem motivo no corpo, o %s diz «%s»", async (estado, texto) => {
    api.getLeadFileContent.mockRejectedValue(recusa(estado));
    const { utilizador, gaveta, bloco } = await abrirGaveta();
    await utilizador.click(within(bloco).getByRole("button", { name: "Visualizar pagamento.pdf" }));
    expect(await within(gaveta).findByRole("alert")).toHaveTextContent(texto);
  });

  it("a gaveta continua utilizável depois de uma falha (outro ficheiro abre)", async () => {
    api.getLeadFileContent.mockRejectedValueOnce(recusa(404));
    const { utilizador, gaveta, bloco } = await abrirGaveta();
    await utilizador.click(within(bloco).getByRole("button", { name: "Visualizar pagamento.pdf" }));
    await within(gaveta).findByRole("alert");
    await utilizador.click(within(bloco).getByRole("button", { name: "Visualizar Foto-Fachada.PNG" }));
    await waitFor(() => expect(within(gaveta).getByTestId("previsualizacao-imagem")).toBeInTheDocument());
    expect(within(gaveta).queryByRole("alert")).toBeNull();
  });
});
