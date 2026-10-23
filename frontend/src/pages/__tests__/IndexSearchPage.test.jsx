/**
 * A pesquisa avançada do Index MONTADA, com o «Ver documento» (Out 2026).
 *
 * A regra do `WebmailPage`: um ecrã só está coberto quando a PÁGINA é montada. Aqui monta-se a página,
 * a tabela e o visualizador REAIS; só se falseiam as fronteiras (o layout, o Axios e o `blob:` do jsdom).
 *
 * A forma dos resultados é a REAL do servidor (`index_advanced_search.resultado_do_documento` e
 * `resultado_do_trabalho`), com valores DIFERENTES das omissões.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));
vi.mock("../../services/api", () => ({
  searchIndexAdvanced: vi.fn(),
  getIndexDocumentContent: vi.fn(),
  // o corpo de erro de um `responseType: blob` vem como Blob; aqui chega já legível
  readBlobErrorBody: vi.fn(async (e) => (e?.response?.data && typeof e.response.data === "object" ? e.response.data : null)),
}));

import { getIndexDocumentContent, searchIndexAdvanced } from "../../services/api";
import IndexSearchPage from "../index/IndexSearchPage";

const EXTRATO = {
  document_id: "doc-extrato-1", document_type: "extrato", process_id: "proc-1", process_number: 4711,
  company_name: "Casa Alfa", period: "2026-09", needs_review: false, bank: "Caixa Geral de Depósitos",
};
const RECIBO = {
  document_id: "doc-recibo-1", document_type: "recibo", process_id: "proc-2", process_number: 4712,
  company_name: "Casa Alfa", period: "2026-07", needs_review: true,
  employer: { nif: "501964843", name: "Empresa Simulada, Lda", location: "Setúbal" },
  job_title: "Engenheira", contract_type: "efetivo", net_salary: 1234.56,
};
const EMPREGO = {
  process_id: "proc-3", process_number: 4713, company_name: "Casa Beta", job_id: "job_abc",
  employer: { nif: "509442013", name: "Outra SA", location: "Porto" }, job_title: "Gerente",
  net_salary: 2500, contract_type: "termo_certo", period: "2026-09", needs_review: false,
  admission_date: "2021-05-03", certified_by_declaration: true, source_documents: 2,
  document_ids: ["doc-a", "doc-b"],
};

const resposta = (view, items, total = items.length) => ({ data: { view, items, total, page: 1, size: 25, filters: {} } });
const ficheiro = (tipo = "application/pdf") => ({ data: new Blob(["bytes"], { type: tipo }), headers: { "content-type": tipo } });

function Localizacao() {
  const l = useLocation();
  return <div data-testid="localizacao">{l.pathname}{l.search}</div>;
}

function montar(entrada = "/index/pesquisa") {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[entrada]}>
        <Localizacao />
        <Routes>
          <Route path="/index/pesquisa" element={<IndexSearchPage />} />
          <Route path="/index" element={<div>fila</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

let criados;
let libertados;
beforeEach(() => {
  vi.clearAllMocks();
  criados = [];
  libertados = [];
  URL.createObjectURL = vi.fn(() => {
    const url = `blob:teste/${criados.length}`;
    criados.push(url);
    return url;
  });
  URL.revokeObjectURL = vi.fn((url) => libertados.push(url));
});
afterEach(() => vi.restoreAllMocks());

async function pesquisarExtratos(user, banco = "CGD") {
  await user.selectOptions(screen.getByLabelText("O que procurar"), "extrato");
  await user.type(screen.getByLabelText("Banco"), banco);
  await user.click(screen.getByRole("button", { name: "Pesquisar" }));
}

describe("antes de pesquisar", () => {
  it("não faz pedido nenhum e diz o que fazer", () => {
    montar();
    expect(screen.getByText("Escolha o que procurar")).toBeInTheDocument();
    expect(searchIndexAdvanced).not.toHaveBeenCalled();
  });

  it("não tem «Voltar à fila»: a fila-pool foi extinta", () => {
    montar();
    expect(screen.queryByText(/Voltar à fila/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /fila/i })).not.toBeInTheDocument();
  });

  it("o banco só aparece quando se procuram extratos", async () => {
    const user = userEvent.setup();
    montar();
    expect(screen.queryByLabelText("Banco")).toBeNull();
    await user.selectOptions(screen.getByLabelText("O que procurar"), "extrato");
    expect(screen.getByLabelText("Banco")).toBeInTheDocument();
    expect(screen.queryByLabelText("Líquido mínimo (€)")).toBeNull();
    await user.selectOptions(screen.getByLabelText("O que procurar"), "recibo");
    expect(screen.queryByLabelText("Banco")).toBeNull();
    expect(screen.getByLabelText("Líquido mínimo (€)")).toBeInTheDocument();
  });
});

describe("extratos da CGD → Ver documento", () => {
  it("pesquisa, mostra a linha e abre o documento SEM sair da página", async () => {
    const user = userEvent.setup();
    searchIndexAdvanced.mockResolvedValue(resposta("documents", [EXTRATO]));
    getIndexDocumentContent.mockResolvedValue(ficheiro("application/pdf"));
    montar();

    await pesquisarExtratos(user);
    expect(searchIndexAdvanced).toHaveBeenCalledWith({ document_type: "extrato", bank: "CGD", size: 25 });

    const linha = await screen.findByTestId("pesquisa-linha");
    expect(within(linha).getByText("Caixa Geral de Depósitos")).toBeInTheDocument();
    expect(within(linha).getByTestId("resultado-processo")).toHaveAttribute("target", "_blank");

    await user.click(within(linha).getByRole("button", { name: /Ver documento/ }));
    // o pedido leva o ID do documento que fez match — a referência exacta, nunca uma chave S3
    await waitFor(() => expect(getIndexDocumentContent).toHaveBeenCalledWith("doc-extrato-1"));
    const dialogo = await screen.findByRole("dialog");
    expect(await within(dialogo).findByTestId("previsualizacao-pdf")).toHaveAttribute("src", criados[0]);

    // a pesquisa ficou por baixo, intacta, e a localização não mudou
    expect(screen.getByTestId("localizacao").textContent).toContain("/index/pesquisa");
    expect(screen.getByTestId("pesquisa-resultados")).toBeInTheDocument();
  });

  it("uma imagem desenha-se como imagem (o tipo é o que o servidor declarou)", async () => {
    const user = userEvent.setup();
    searchIndexAdvanced.mockResolvedValue(resposta("documents", [EXTRATO]));
    getIndexDocumentContent.mockResolvedValue(ficheiro("image/png"));
    montar();
    await pesquisarExtratos(user);
    await user.click(await screen.findByTestId("ver-documento"));
    expect(await screen.findByTestId("previsualizacao-imagem")).toBeInTheDocument();
    expect(screen.queryByTestId("previsualizacao-pdf")).toBeNull();
  });

  it("um tipo que o servidor não declara como pré-visualizável nunca vira <iframe>", async () => {
    const user = userEvent.setup();
    searchIndexAdvanced.mockResolvedValue(resposta("documents", [EXTRATO]));
    getIndexDocumentContent.mockResolvedValue({ data: new Blob(["<h1>x</h1>"]), headers: { "content-type": "text/html" } });
    montar();
    await pesquisarExtratos(user);
    await user.click(await screen.findByTestId("ver-documento"));
    expect(await screen.findByTestId("previsualizacao-erro")).toBeInTheDocument();
    expect(screen.queryByTestId("previsualizacao-pdf")).toBeNull();
    expect(screen.queryByTestId("previsualizacao-imagem")).toBeNull();
  });

  it("fechar liberta o blob (um createObjectURL esquecido segura o ficheiro em memória)", async () => {
    const user = userEvent.setup();
    searchIndexAdvanced.mockResolvedValue(resposta("documents", [EXTRATO]));
    getIndexDocumentContent.mockResolvedValue(ficheiro());
    montar();
    await pesquisarExtratos(user);
    await user.click(await screen.findByTestId("ver-documento"));
    await screen.findByTestId("previsualizacao-pdf");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(libertados).toEqual([criados[0]]);
  });
});

describe("quando o servidor recusa", () => {
  it.each([
    [404, undefined, /já não está disponível/],
    [403, undefined, /Sem permissão/],
    [413, undefined, /demasiado grande/],
    [415, undefined, /não tem pré-visualização/],
    [503, "Serviço de armazenamento indisponível.", /armazenamento indisponível/],
  ])("%s diz-se no próprio visualizador, sem fechar a pesquisa", async (estado, detail, padrao) => {
    const user = userEvent.setup();
    searchIndexAdvanced.mockResolvedValue(resposta("documents", [EXTRATO]));
    getIndexDocumentContent.mockRejectedValue({ response: { status: estado, data: detail ? { detail } : {} } });
    montar();
    await pesquisarExtratos(user);
    await user.click(await screen.findByTestId("ver-documento"));
    expect(await screen.findByTestId("previsualizacao-erro")).toHaveTextContent(padrao);
    expect(screen.getByTestId("pesquisa-resultados")).toBeInTheDocument();
  });
});

describe("recibos e declarações", () => {
  it("o valor exacto vai como mínimo = máximo e a linha mostra o líquido", async () => {
    const user = userEvent.setup();
    searchIndexAdvanced.mockResolvedValue(resposta("documents", [RECIBO]));
    montar();
    await user.selectOptions(screen.getByLabelText("O que procurar"), "recibo");
    await user.type(screen.getByLabelText("Líquido mínimo (€)"), "1234,56");
    await user.type(screen.getByLabelText("Líquido máximo (€)"), "1234,56");
    await user.click(screen.getByRole("button", { name: "Pesquisar" }));
    expect(searchIndexAdvanced).toHaveBeenCalledWith({ document_type: "recibo", min_salary: 1234.56, max_salary: 1234.56, size: 25 });
    const linha = await screen.findByTestId("pesquisa-linha");
    expect(linha.textContent).toMatch(/1\.?234,56/);
    expect(within(linha).getByText("Setúbal")).toBeInTheDocument();
    expect(within(linha).getByText("A rever")).toBeInTheDocument();
  });

  it("uma declaração por localidade pede só os campos que lhe pertencem", async () => {
    const user = userEvent.setup();
    searchIndexAdvanced.mockResolvedValue(resposta("documents", []));
    montar();
    await user.selectOptions(screen.getByLabelText("O que procurar"), "declaracao_efetividade");
    await user.type(screen.getByLabelText("Localidade / região"), "Lisboa");
    await user.click(screen.getByRole("button", { name: "Pesquisar" }));
    expect(searchIndexAdvanced).toHaveBeenCalledWith({ document_type: "declaracao_efetividade", employer_location: "Lisboa", size: 25 });
    expect(await screen.findByText("Sem resultados")).toBeInTheDocument();
  });
});

describe("a vista por emprego", () => {
  it("o contrato certificado pela declaração diz-se e os vários documentos navegam-se", async () => {
    const user = userEvent.setup();
    searchIndexAdvanced.mockResolvedValue(resposta("jobs", [EMPREGO]));
    getIndexDocumentContent.mockResolvedValue(ficheiro());
    montar();
    await user.click(screen.getByRole("button", { name: "Pesquisar" }));
    const linha = await screen.findByTestId("pesquisa-linha");
    expect(within(linha).getByText("Certificado")).toBeInTheDocument();
    expect(within(linha).getByText("Termo certo")).toBeInTheDocument();
    expect(within(linha).getByText("03/05/2021")).toBeInTheDocument();

    await user.click(within(linha).getByRole("button", { name: /Ver documentos \(2\)/ }));
    await waitFor(() => expect(getIndexDocumentContent).toHaveBeenCalledWith("doc-a"));
    expect(screen.getByTestId("visualizador-posicao")).toHaveTextContent("Documento 1 de 2");
    await user.click(screen.getByRole("button", { name: "Documento seguinte" }));
    await waitFor(() => expect(getIndexDocumentContent).toHaveBeenCalledWith("doc-b"));
    expect(screen.getByTestId("visualizador-posicao")).toHaveTextContent("Documento 2 de 2");
    expect(screen.getByRole("button", { name: "Documento seguinte" })).toBeDisabled();
    // o blob do primeiro ficou libertado ao trocar
    expect(libertados).toContain(criados[0]);
  });

  it("uma linha sem referência a documentos não desenha o botão", async () => {
    const user = userEvent.setup();
    searchIndexAdvanced.mockResolvedValue(resposta("jobs", [{ ...EMPREGO, document_ids: [] }]));
    montar();
    await user.click(screen.getByRole("button", { name: "Pesquisar" }));
    await screen.findByTestId("pesquisa-linha");
    expect(screen.queryByTestId("ver-documento")).toBeNull();
    expect(screen.getByText("Sem documento")).toBeInTheDocument();
  });
});

describe("o URL guarda a pergunta", () => {
  it("abrir a página com uma pesquisa no URL pesquisa e pré-preenche o formulário", async () => {
    searchIndexAdvanced.mockResolvedValue(resposta("documents", [EXTRATO]));
    montar("/index/pesquisa?ps_tipo=extrato&ps_banco=Santander&ps_go=1");
    expect(await screen.findByTestId("pesquisa-linha")).toBeInTheDocument();
    expect(searchIndexAdvanced).toHaveBeenCalledWith({ document_type: "extrato", bank: "Santander", size: 25 });
    expect(screen.getByLabelText("Banco")).toHaveValue("Santander");
    expect(screen.getByLabelText("O que procurar")).toHaveValue("extrato");
  });

  it("pesquisar escreve os filtros no URL, e «Limpar» apaga-os", async () => {
    const user = userEvent.setup();
    searchIndexAdvanced.mockResolvedValue(resposta("documents", [EXTRATO]));
    montar();
    await pesquisarExtratos(user, "BPI");
    await screen.findByTestId("pesquisa-linha");
    expect(screen.getByTestId("localizacao").textContent).toMatch(/ps_tipo=extrato.*ps_banco=BPI|ps_banco=BPI.*ps_tipo=extrato/);
    await user.click(screen.getByRole("button", { name: "Limpar" }));
    await waitFor(() => expect(screen.getByTestId("localizacao").textContent).toBe("/index/pesquisa"));
    expect(screen.getByText("Escolha o que procurar")).toBeInTheDocument();
  });
});

describe("erros", () => {
  it("um valor inválido diz-se antes do pedido e não pesquisa", async () => {
    const user = userEvent.setup();
    montar();
    await user.selectOptions(screen.getByLabelText("O que procurar"), "recibo");
    await user.type(screen.getByLabelText("Líquido mínimo (€)"), "2000");
    await user.type(screen.getByLabelText("Líquido máximo (€)"), "1000");
    await user.click(screen.getByRole("button", { name: "Pesquisar" }));
    expect(await screen.findByText(/máximo não pode ser inferior/)).toBeInTheDocument();
    expect(searchIndexAdvanced).not.toHaveBeenCalled();
  });

  it("um erro de LEITURA nunca é «sem resultados»: diz-se e deixa tentar de novo", async () => {
    const user = userEvent.setup();
    searchIndexAdvanced.mockRejectedValueOnce({ response: { status: 503, data: { detail: "A pesquisa não terminou a tempo." } } });
    montar();
    await user.click(screen.getByRole("button", { name: "Pesquisar" }));
    const alerta = await screen.findByTestId("pesquisa-erro");
    expect(alerta).toHaveTextContent("A pesquisa não terminou a tempo.");
    expect(screen.queryByText("Sem resultados")).toBeNull();

    searchIndexAdvanced.mockResolvedValueOnce(resposta("documents", [EXTRATO]));
    await user.click(within(alerta).getByRole("button", { name: /Tentar de novo/ }));
    expect(await screen.findByTestId("pesquisa-linha")).toBeInTheDocument();
  });

  it("a forma errada da resposta não rebenta o ecrã", async () => {
    const user = userEvent.setup();
    searchIndexAdvanced.mockResolvedValue({ data: { items: { x: 1 }, total: 0 } });
    montar();
    await user.click(screen.getByRole("button", { name: "Pesquisar" }));
    expect(await screen.findByText("Sem resultados")).toBeInTheDocument();
  });
});
