/**
 * O Portal do Parceiro MONTADO — o trabalho: painel, lead, caso e ficheiros.
 *
 * As respostas são as REAIS do servidor (fixtures geradas pelos serviços), e
 * os valores são diferentes das omissões: com valores iguais às omissões,
 * um erro de leitura é indistinguível de uma leitura correcta.
 */
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import confirmacao from "@/test/fixtures/parceiro/confirmacao_de_envio.json";
import leadCriada from "@/test/fixtures/parceiro/lead_criada.json";
import leadRepetida from "@/test/fixtures/parceiro/lead_repetida.json";

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
}));

import * as api from "@/services/partnerApi";
import { queryKeys } from "@/lib/queryClient";
import { FIXTURES, erroHttp, montar, prepararApi } from "./montagem";

beforeEach(() => prepararApi());
afterEach(() => vi.restoreAllMocks());

// ════════════════════════════════════════════════════════════════════
//  PAINEL
// ════════════════════════════════════════════════════════════════════
describe("o painel", () => {
  const metrica = async (rotulo) => {
    const resumo = await screen.findByRole("region", { name: "Resumo" });
    return (await within(resumo).findByText(rotulo)).nextSibling;
  };

  it("mostra as métricas simples do servidor", async () => {
    montar("/parceiro");
    expect(await metrica("Leads")).toHaveTextContent("2");
    expect(await metrica("Em aprovação")).toHaveTextContent("1");
    expect(await metrica("Escriturados")).toHaveTextContent("1");
    expect(await metrica("Conversão")).toHaveTextContent("16,7 %");
    expect(await metrica("Pedidos pendentes")).toHaveTextContent("2");
  });

  it("sem base de cálculo a conversão é «—», nunca «0 %»", async () => {
    api.obterPainel.mockResolvedValue({ ...FIXTURES.painel, taxa_de_conversao: null, total_de_casos: 0 });
    montar("/parceiro");
    expect(await metrica("Conversão")).toHaveTextContent("—");
  });

  it("lista os casos com link para o detalhe, etapa e pedidos pendentes", async () => {
    montar("/parceiro");
    const link = await screen.findByRole("link", { name: /Cliente a-novo/ });
    expect(link).toHaveAttribute("href", "/parceiro/casos/a-novo");
    expect(within(link).getByText("Em preparação")).toBeInTheDocument();
    expect(within(link).getByText(/PROC-a-novo/)).toBeInTheDocument();
    expect(within(link).getByText(/Carla Consultora/)).toBeInTheDocument();
    expect(within(link).getByText("1 pendente")).toBeInTheDocument();
  });

  it("os botões de etapa vêm do funil do servidor, com as contagens", async () => {
    montar("/parceiro");
    const grupo = await screen.findByRole("group", { name: "Filtrar por etapa" });
    // o grupo existe desde o primeiro render; os botões do funil só quando o painel chega
    await within(grupo).findByRole("button", { name: "Leads (2)" });
    const botoes = within(grupo).getAllByRole("button");
    expect(botoes.map((b) => b.textContent)).toEqual([
      "Todos (6)", "Leads (2)", "Em preparação (1)", "Em análise (0)", "Em aprovação (1)", "Escriturados (1)", "Perdidos (1)",
    ]);
  });

  it("filtrar por etapa pede essa etapa ao servidor e marca o botão", async () => {
    montar("/parceiro");
    await userEvent.click(await screen.findByRole("button", { name: "Em aprovação (1)" }));
    await waitFor(() => expect(api.listarCasos).toHaveBeenLastCalledWith(expect.objectContaining({ etapa: "aprovado", page: 1 })));
    expect(screen.getByRole("button", { name: "Em aprovação (1)" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Todos (6)" })).toHaveAttribute("aria-pressed", "false");
  });

  it("a pesquisa parte para o servidor depois de uma pausa e volta à primeira página", async () => {
    montar("/parceiro");
    await screen.findByRole("link", { name: /Cliente a-novo/ });
    await userEvent.type(screen.getByRole("searchbox", { name: "Pesquisar casos" }), "ana");
    await waitFor(() => expect(api.listarCasos).toHaveBeenLastCalledWith(expect.objectContaining({ q: "ana", page: 1 })), { timeout: 2000 });
    // uma só pesquisa, e não uma por tecla
    expect(api.listarCasos.mock.calls.filter(([f]) => f.q === "an" || f.q === "a")).toHaveLength(0);
  });

  it("sem casos, convida a submeter a primeira lead", async () => {
    api.listarCasos.mockResolvedValue({ items: [], total: 0, page: 1, size: 15, pages: 1 });
    montar("/parceiro");
    expect(await screen.findByText(/Ainda não tem casos/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Submeter lead" })).toHaveAttribute("href", "/parceiro/novo-lead");
  });

  it("sem casos por causa de um filtro, diz-o (e não convida a submeter)", async () => {
    montar("/parceiro");
    await userEvent.click(await screen.findByRole("button", { name: "Perdidos (1)" }));
    api.listarCasos.mockResolvedValue({ items: [], total: 0, page: 1, size: 15, pages: 1 });
    await userEvent.click(screen.getByRole("button", { name: "Em análise (0)" }));
    expect(await screen.findByText(/Nenhum caso corresponde ao filtro/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Submeter lead" })).not.toBeInTheDocument();
  });

  it("uma lista que falha diz porquê e o painel continua a servir", async () => {
    api.listarCasos.mockRejectedValue(erroHttp(500, "Erro interno"));
    montar("/parceiro");
    expect(await screen.findByText("Erro interno")).toBeInTheDocument();
    expect(await metrica("Leads")).toHaveTextContent("2");
  });

  it("pagina quando há mais do que uma página", async () => {
    // o servidor devolve a página pedida (o mock fixo devolvia sempre a 1.ª e o ecrã lê a do servidor)
    api.listarCasos.mockImplementation(async ({ page }) => ({ ...FIXTURES.casos, page, pages: 3, total: 40 }));
    montar("/parceiro");
    await userEvent.click(await screen.findByRole("button", { name: /Seguinte/ }));
    await waitFor(() => expect(api.listarCasos).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })));
    expect(await screen.findByText("Página 2 de 3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Anterior/ })).toBeEnabled();
  });

  it("nada financeiro no painel: o parceiro paga-nos, não recebe comissões", async () => {
    const { container } = montar("/parceiro");
    await screen.findByRole("link", { name: /Cliente a-novo/ });
    expect(container.textContent).not.toMatch(/comiss|valor|€|eur\b|pago/i);
  });
});

// ════════════════════════════════════════════════════════════════════
//  LEAD
// ════════════════════════════════════════════════════════════════════
describe("submeter uma lead", () => {
  const preencherO_Essencial = async () => {
    await userEvent.type(await screen.findByLabelText("Nome do cliente *"), "Joana Cliente");
    await userEvent.type(screen.getByLabelText("Email *"), "joana@cliente.pt");
  };

  it("sem os dados obrigatórios e sem consentimento: mostra os erros e não envia", async () => {
    montar("/parceiro/novo-lead");
    await userEvent.click(await screen.findByRole("button", { name: "Submeter lead" }));
    const alertas = screen.getAllByRole("alert").map((a) => a.textContent);
    expect(alertas).toEqual(expect.arrayContaining([
      "Indique o nome do cliente.", "Indique um email válido.", "Confirme que tem autorização do cliente.",
    ]));
    expect(api.submeterLead).not.toHaveBeenCalled();
  });

  it("o consentimento é obrigatório mesmo com tudo o resto certo", async () => {
    montar("/parceiro/novo-lead");
    await preencherO_Essencial();
    await userEvent.click(screen.getByRole("button", { name: "Submeter lead" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("autorização do cliente");
    expect(api.submeterLead).not.toHaveBeenCalled();
  });

  it("envia SÓ os campos que o servidor aceita", async () => {
    api.submeterLead.mockResolvedValue(leadCriada);
    montar("/parceiro/novo-lead");
    await preencherO_Essencial();
    await userEvent.type(screen.getByLabelText("Telefone"), "912345678");
    await userEvent.click(screen.getByRole("checkbox", { name: /O cliente já tem imóvel/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /autorização do cliente/ }));
    await userEvent.click(screen.getByRole("button", { name: "Submeter lead" }));

    await waitFor(() => expect(api.submeterLead).toHaveBeenCalledTimes(1));
    expect(api.submeterLead).toHaveBeenCalledWith({
      name: "Joana Cliente",
      email: "joana@cliente.pt",
      phone: "912345678",
      process_type: "credito_habitacao",
      has_property: true,
      consent_confirmed: true,
    });
  });

  it("depois de submeter, leva ao caso e deixa submeter outra", async () => {
    api.submeterLead.mockResolvedValue(leadCriada);
    montar("/parceiro/novo-lead");
    await preencherO_Essencial();
    await userEvent.click(screen.getByRole("checkbox", { name: /autorização do cliente/ }));
    await userEvent.click(screen.getByRole("button", { name: "Submeter lead" }));

    expect(await screen.findByText("Lead submetida")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Ver o caso/ })).toHaveAttribute("href", "/parceiro/casos/lead-novo");
    await userEvent.click(screen.getByRole("button", { name: "Submeter outra" }));
    expect(await screen.findByLabelText("Nome do cliente *")).toHaveValue("");
  });

  it("o duplo clique do próprio parceiro diz que já tinha sido submetida", async () => {
    api.submeterLead.mockResolvedValue(leadRepetida);
    montar("/parceiro/novo-lead");
    await preencherO_Essencial();
    await userEvent.click(screen.getByRole("checkbox", { name: /autorização do cliente/ }));
    await userEvent.click(screen.getByRole("button", { name: "Submeter lead" }));
    expect(await screen.findByText("Esta lead já tinha sido submetida")).toBeInTheDocument();
  });

  it("um erro do servidor aparece e os dados ficam (nada se perde)", async () => {
    api.submeterLead.mockRejectedValue(erroHttp(429, "Atingiu o limite diário de leads."));
    montar("/parceiro/novo-lead");
    await preencherO_Essencial();
    await userEvent.click(screen.getByRole("checkbox", { name: /autorização do cliente/ }));
    await userEvent.click(screen.getByRole("button", { name: "Submeter lead" }));
    expect(await screen.findByText("Atingiu o limite diário de leads.")).toBeInTheDocument();
    expect(screen.getByLabelText("Nome do cliente *")).toHaveValue("Joana Cliente");
  });

  it("com duas redes é preciso escolher a rede — e é essa que vai", async () => {
    api.obterPerfil.mockResolvedValue({
      ...FIXTURES.perfil,
      redes: [
        { network_id: "rede-a", company_id: "c1", company_name: "Power", status: "active" },
        { network_id: "rede-b", company_id: "c2", company_name: "Domus", status: "active" },
      ],
    });
    api.submeterLead.mockResolvedValue(leadCriada);
    montar("/parceiro/novo-lead");
    await preencherO_Essencial();
    await userEvent.click(screen.getByRole("checkbox", { name: /autorização do cliente/ }));
    await userEvent.click(screen.getByRole("button", { name: "Submeter lead" }));
    expect(await screen.findByText("Escolha a rede a que esta lead se destina.")).toBeInTheDocument();
    expect(api.submeterLead).not.toHaveBeenCalled();

    await userEvent.selectOptions(screen.getByLabelText("Rede *"), "rede-b");
    await userEvent.click(screen.getByRole("button", { name: "Submeter lead" }));
    await waitFor(() => expect(api.submeterLead).toHaveBeenCalledWith(expect.objectContaining({ network_id: "rede-b" })));
  });

  it("com uma só rede não pergunta nem envia a rede", async () => {
    api.submeterLead.mockResolvedValue(leadCriada);
    montar("/parceiro/novo-lead");
    await preencherO_Essencial();
    expect(screen.queryByLabelText("Rede *")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: /autorização do cliente/ }));
    await userEvent.click(screen.getByRole("button", { name: "Submeter lead" }));
    await waitFor(() => expect(api.submeterLead).toHaveBeenCalled());
    expect(api.submeterLead.mock.calls[0][0]).not.toHaveProperty("network_id");
  });
});

// ════════════════════════════════════════════════════════════════════
//  CASO
// ════════════════════════════════════════════════════════════════════
describe("o caso", () => {
  it("mostra o cabeçalho de um processo", async () => {
    montar("/parceiro/casos/a-novo");
    expect(await screen.findByRole("heading", { name: "Cliente a-novo" })).toBeInTheDocument();
    expect(screen.getByText(/PROC-a-novo/)).toBeInTheDocument();
    expect(screen.getByText(/Consultor: Carla Consultora/)).toBeInTheDocument();
    expect(screen.getByText("Em preparação")).toBeInTheDocument();
  });

  it("os pedidos pendentes vêm primeiro, com a nota da equipa e o progresso", async () => {
    montar("/parceiro/casos/a-novo");
    const pendente = await screen.findByTestId("pedido-req-1");
    expect(within(pendente).getByText("CC frente e verso")).toBeInTheDocument();
    expect(within(pendente).getByText("Frente e verso, por favor")).toBeInTheDocument();
    expect(within(pendente).getByLabelText("0 de 2 ficheiros")).toBeInTheDocument();
    expect(within(pendente).getByText("Pendente")).toBeInTheDocument();

    const ordem = screen.getAllByTestId(/^pedido-/).map((n) => n.getAttribute("data-testid"));
    expect(ordem).toEqual(["pedido-req-1", "pedido-req-2"]);
  });

  it("um pedido recebido mostra quem enviou cada ficheiro e não oferece envio", async () => {
    montar("/parceiro/casos/a-novo");
    const recebido = await screen.findByTestId("pedido-req-2");
    expect(within(recebido).getByText("Recebido")).toBeInTheDocument();
    expect(within(recebido).getByText(/irs-cliente\.pdf/)).toBeInTheDocument();
    expect(within(recebido).getByText(/Enviado pelo cliente/)).toBeInTheDocument();
    expect(within(recebido).getByText(/Enviado por si/)).toBeInTheDocument();
    expect(within(recebido).queryByRole("button", { name: "Enviar ficheiro" })).not.toBeInTheDocument();
  });

  it("os ficheiros soltos aparecem à parte", async () => {
    montar("/parceiro/casos/a-novo");
    const seccao = await screen.findByRole("region", { name: "Outros ficheiros" });
    expect(within(seccao).getByText("foto.jpg")).toBeInTheDocument();
    expect(within(seccao).getByText("extra.pdf")).toBeInTheDocument();
  });

  it("uma lead explica que está em análise e mostra os pedidos dela", async () => {
    montar("/parceiro/casos/lead-1");
    expect(await screen.findByText(/está a ser analisada/)).toBeInTheDocument();
    expect(screen.getByTestId("pedido-req-lead")).toBeInTheDocument();
  });

  it("um caso que não é seu diz «não existe», sem pistas e sem rebentar", async () => {
    montar("/parceiro/casos/de-outro-parceiro");
    expect(await screen.findByRole("alert")).toHaveTextContent("não existe ou já não está disponível");
    expect(screen.getByRole("link", { name: /Voltar ao painel/ })).toHaveAttribute("href", "/parceiro");
  });

  it("não há notas internas nem dados financeiros na página", async () => {
    const { container } = montar("/parceiro/casos/a-novo");
    await screen.findByRole("heading", { name: "Cliente a-novo" });
    expect(container.textContent).not.toMatch(/comiss|NOTA INTERNA|€|NIF|rendimento|prestação/i);
  });
});

// ════════════════════════════════════════════════════════════════════
//  FICHEIROS
// ════════════════════════════════════════════════════════════════════
describe("enviar e descarregar", () => {
  const pdf = () => new File(["%PDF-1.4"], "cc.pdf", { type: "application/pdf" });

  it("responder a um pedido envia com o id do pedido e refresca o caso e invalida a lista e o painel", async () => {
    api.enviarFicheiro.mockResolvedValue({ ...confirmacao, destino: { ...confirmacao.destino, fila_ia: false } });
    const { queryClient } = montar("/parceiro/casos/a-novo");
    const invalidar = vi.spyOn(queryClient, "invalidateQueries");
    const pedido = await screen.findByTestId("pedido-req-1");
    const antes = api.obterCaso.mock.calls.length;

    await userEvent.upload(within(pedido).getByTestId("input-req-1"), pdf());

    await waitFor(() => expect(api.enviarFicheiro).toHaveBeenCalledTimes(1));
    const [caso, ficheiro, opcoes] = api.enviarFicheiro.mock.calls[0];
    expect(caso).toBe("a-novo");
    expect(ficheiro.name).toBe("cc.pdf");
    expect(opcoes).toEqual(expect.objectContaining({ requestId: "req-1" }));
    await waitFor(() => expect(api.obterCaso.mock.calls.length).toBeGreaterThan(antes));
    // o painel NÃO está montado na página do caso, logo não há pedido a contar — mas a
    // invalidação tem de ter sido pedida (é ela que o torna stale para quando o parceiro voltar)
    const chaves = invalidar.mock.calls.map(([f]) => JSON.stringify(f.queryKey));
    expect(chaves).toContain(JSON.stringify(queryKeys.partner.painel()));
    expect(chaves).toContain(JSON.stringify(queryKeys.partner.casosAll()));
    expect(await within(pedido).findByText("Enviado")).toBeInTheDocument();
  });

  it("um envio solto não leva pedido", async () => {
    api.enviarFicheiro.mockResolvedValue(confirmacao);
    montar("/parceiro/casos/a-novo");
    await userEvent.upload(await screen.findByTestId("input-solto"), pdf());
    await waitFor(() => expect(api.enviarFicheiro).toHaveBeenCalled());
    expect(api.enviarFicheiro.mock.calls[0][2].requestId).toBeUndefined();
  });

  it("quando o servidor manda o ficheiro para a Indexação, o ecrã di-lo", async () => {
    api.enviarFicheiro.mockResolvedValue(confirmacao); // fila_ia: true
    montar("/parceiro/casos/a-novo");
    await userEvent.upload(await screen.findByTestId("input-solto"), pdf());
    expect(await screen.findByText(/segue para a análise da nossa equipa/)).toBeInTheDocument();
  });

  it("um envio que falha nomeia o ficheiro e dá o motivo", async () => {
    api.enviarFicheiro.mockRejectedValue(erroHttp(400, "Conteúdo do ficheiro não permitido."));
    montar("/parceiro/casos/a-novo");
    await userEvent.upload(await screen.findByTestId("input-solto"), pdf());
    expect(await screen.findByText("Conteúdo do ficheiro não permitido.")).toBeInTheDocument();
    expect(await screen.findByText("Não foi possível enviar: cc.pdf.")).toBeInTheDocument();
  });

  it("vários ficheiros enviam-se um a um, por ordem", async () => {
    const ordem = [];
    api.enviarFicheiro.mockImplementation(async (_c, f) => {
      ordem.push(f.name);
      return confirmacao;
    });
    montar("/parceiro/casos/a-novo");
    const entrada = await screen.findByTestId("input-solto");
    await userEvent.upload(entrada, [new File(["a"], "a.pdf", { type: "application/pdf" }), new File(["b"], "b.png", { type: "image/png" })]);
    await waitFor(() => expect(ordem).toEqual(["a.pdf", "b.png"]));
  });

  it("largar um .exe é recusado com o nome — e nunca chega ao servidor", async () => {
    montar("/parceiro/casos/a-novo");
    const zona = await screen.findByTestId("dropzone-solto");
    const exe = new File(["MZ"], "virus.exe", { type: "application/x-msdownload" });
    fireEvent.drop(zona, { dataTransfer: { types: ["Files"], files: [exe] } });
    expect(await screen.findByRole("alert")).toHaveTextContent(/virus\.exe/);
    expect(api.enviarFicheiro).not.toHaveBeenCalled();
  });

  it("largar um PDF envia-o (o arrasto aceita os mesmos tipos do botão)", async () => {
    api.enviarFicheiro.mockResolvedValue(confirmacao);
    montar("/parceiro/casos/a-novo");
    const zona = await screen.findByTestId("dropzone-req-1");
    fireEvent.drop(zona, { dataTransfer: { types: ["Files"], files: [pdf()] } });
    await waitFor(() => expect(api.enviarFicheiro).toHaveBeenCalled());
    expect(api.enviarFicheiro.mock.calls[0][2].requestId).toBe("req-1");
  });

  it("descarregar pede o URL pelo id do ficheiro e abre-o sem `opener`", async () => {
    const abrir = vi.spyOn(window, "open").mockImplementation(() => null);
    api.obterUrlDeDescarga.mockResolvedValue({ url: "https://s3.exemplo/get", filename: "irs-parceiro.pdf" });
    montar("/parceiro/casos/a-novo");
    await userEvent.click(await screen.findByRole("button", { name: "Descarregar irs-parceiro.pdf" }));
    await waitFor(() => expect(abrir).toHaveBeenCalledWith("https://s3.exemplo/get", "_blank", "noopener,noreferrer"));
    expect(api.obterUrlDeDescarga).toHaveBeenCalledWith("a-novo", "f-eu");
  });

  it("uma descarga que falha diz porquê", async () => {
    vi.spyOn(window, "open").mockImplementation(() => null);
    api.obterUrlDeDescarga.mockRejectedValue(erroHttp(404, "Ficheiro não encontrado."));
    montar("/parceiro/casos/a-novo");
    await userEvent.click(await screen.findByRole("button", { name: "Descarregar irs-parceiro.pdf" }));
    expect(await screen.findByText("Ficheiro não encontrado.")).toBeInTheDocument();
  });
});
