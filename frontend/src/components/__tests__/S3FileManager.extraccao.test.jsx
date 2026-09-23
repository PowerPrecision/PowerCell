/**
 * Botão "Extrair Dados com IA" no gestor de ficheiros (Épico 9, Eixo 1/4).
 *
 * O QUE ESTÁ AQUI EM JOGO:
 *   Este botão manda um documento de um cliente para um modelo de visão e
 *   traz de volta NIF, nome e vencimento. Três regras não podem partir-se:
 *
 *   1. **Papel.** É uma ferramenta de gestão, como as outras de IA, e olha
 *      para o `effectiveRole` (perfil activo) — não para o papel base. É
 *      disso que depende o multi-perfil.
 *   2. **Formato.** Só imagens e PDF. Um .docx seguiria para uma chamada
 *      PAGA e voltaria vazio.
 *   3. **Nada é gravado aqui.** O componente entrega os dados ao contentor
 *      e o contentor é que abre a revisão. Se este ficheiro alguma vez
 *      chamar `ai-apply-suggestions`, a regra de ouro caiu.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const sessao = vi.hoisted(() => ({ valor: null }));
vi.mock("../../contexts/AuthContext", () => ({ useAuth: () => sessao.valor }));

const rede = vi.hoisted(() => ({
  respostas: new Map(),
  chamadas: [],
  extraccao: null,
}));

vi.mock("../../services/api", async (original) => {
  const real = await original().catch(() => ({}));
  const resolver = (metodo) => (url, ...resto) => {
    rede.chamadas.push({ metodo, url: String(url), corpo: resto[0] });
    for (const [padrao, carga] of rede.respostas) {
      if (String(url).includes(padrao)) {
        if (carga instanceof Error) return Promise.reject(carga);
        return Promise.resolve({ data: carga });
      }
    }
    return Promise.resolve({ data: {} });
  };
  const cliente = {
    get: resolver("GET"),
    post: resolver("POST"),
    put: resolver("PUT"),
    patch: resolver("PATCH"),
    delete: resolver("DELETE"),
  };
  return {
    ...real,
    default: cliente,
    analyzeDocumentForReview: vi.fn(() => Promise.resolve({ data: {} })),
    extractDocumentData: (processId, caminho) => {
      rede.chamadas.push({
        metodo: "POST",
        url: `/processes/${processId}/documents/extract`,
        corpo: { s3_path: caminho },
      });
      if (rede.extraccao instanceof Error) return Promise.reject(rede.extraccao);
      return Promise.resolve({ data: rede.extraccao || {} });
    },
    getProcessS3Files: (processId) =>
      cliente.get(`/documents/client/${processId}/files`),
    getClientS3Mappings: () => cliente.get("/admin/client-s3-mappings"),
    aiApplyS3Suggestions: (processId, carga) =>
      cliente.post(`/documents/ai-apply-suggestions/${processId}`, carga),
    aiAnalyzeS3Documents: (processId, carga) =>
      cliente.post(`/documents/ai-analyze/${processId}`, carga),
    getS3FileContent: (caminho) => cliente.get(`/documents/proxy/${caminho}`),
  };
});

import S3FileManager from "../S3FileManager";

const RESPOSTA_CC = {
  success: true,
  extracted_data: { nif: "123456789", nome: "Ana Martins" },
  field_confidence: { nif: 0.97 },
  conflicts: [],
  source_document: { name: "cartao_cidadao.pdf", mime_type: "application/pdf" },
  titular_matches: [],
  needs_titular_choice: false,
};

const FICHEIROS = {
  "Documentos Pessoais": [
    {
      name: "cartao_cidadao.pdf",
      path: "Clientes/Ana Martins/Documentos Pessoais/cartao_cidadao.pdf",
      size: 245678,
      last_modified: "2026-09-20T10:00:00Z",
    },
    {
      name: "procuracao.docx",
      path: "Clientes/Ana Martins/Documentos Pessoais/procuracao.docx",
      size: 30000,
      last_modified: "2026-09-20T10:00:00Z",
    },
  ],
};

function montar({ papel = "diretor", aoExtrair = vi.fn() } = {}) {
  sessao.valor = {
    token: "t-1",
    user: { id: "u-1", name: "Carla", role: papel },
    effectiveRole: papel,
  };
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <S3FileManager
        processId="proc-1"
        clientName="Ana Martins"
        onDocumentDataExtracted={aoExtrair}
      />
    </QueryClientProvider>,
  );
  return { aoExtrair };
}

const botoesDeExtraccao = () =>
  screen.queryAllByRole("button", { name: /^Extrair dados de/ });

beforeEach(() => {
  rede.respostas.clear();
  rede.chamadas.length = 0;
  rede.extraccao = RESPOSTA_CC;
  rede.respostas.set("/files", {
    files: FICHEIROS,
    stats: { total_files: 2, total_size: 275678 },
  });
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) }),
  );
});

afterEach(() => vi.restoreAllMocks());

describe("Quem vê o botão", () => {
  it("um perfil de gestão vê-o", async () => {
    montar({ papel: "diretor" });
    await waitFor(() => expect(botoesDeExtraccao().length).toBeGreaterThan(0));
  });

  it("um consultor não o vê", async () => {
    montar({ papel: "consultor" });
    await screen.findByText("cartao_cidadao.pdf");
    expect(botoesDeExtraccao()).toHaveLength(0);
  });

  it("o perfil de indexação não o vê", async () => {
    montar({ papel: "indexacao" });
    await screen.findByText("cartao_cidadao.pdf");
    expect(botoesDeExtraccao()).toHaveLength(0);
  });
});

describe("Que ficheiros aceitam extracção", () => {
  it("um PDF tem botão", async () => {
    montar();
    await waitFor(() =>
      expect(
        screen.queryAllByRole("button", {
          name: "Extrair dados de cartao_cidadao.pdf",
        }).length,
      ).toBeGreaterThan(0),
    );
  });

  it("um .docx não tem botão", async () => {
    // Não é preciosismo: seguiria para uma chamada paga e voltaria vazio.
    montar();
    await screen.findByText("procuracao.docx");
    expect(
      screen.queryAllByRole("button", {
        name: "Extrair dados de procuracao.docx",
      }),
    ).toHaveLength(0);
  });
});

describe("O que acontece ao clicar", () => {
  it("pede a extracção ao endpoint com o caminho S3 do ficheiro", async () => {
    const utilizador = userEvent.setup();
    montar();
    const [botao] = await waitFor(() => {
      const lista = screen.queryAllByRole("button", {
        name: "Extrair dados de cartao_cidadao.pdf",
      });
      expect(lista.length).toBeGreaterThan(0);
      return lista;
    });

    await utilizador.click(botao);

    await waitFor(() => {
      const pedido = rede.chamadas.find((c) => c.url.includes("/documents/extract"));
      expect(pedido).toBeTruthy();
      expect(pedido.corpo.s3_path).toBe(
        "Clientes/Ana Martins/Documentos Pessoais/cartao_cidadao.pdf",
      );
    });
  });

  it("entrega os dados ao contentor, com o ficheiro de origem", async () => {
    const utilizador = userEvent.setup();
    const { aoExtrair } = montar();
    const [botao] = await waitFor(() => {
      const lista = screen.queryAllByRole("button", {
        name: "Extrair dados de cartao_cidadao.pdf",
      });
      expect(lista.length).toBeGreaterThan(0);
      return lista;
    });

    await utilizador.click(botao);

    await waitFor(() => expect(aoExtrair).toHaveBeenCalledTimes(1));
    const carga = aoExtrair.mock.calls[0][0];
    expect(carga.extractedData).toEqual({ nif: "123456789", nome: "Ana Martins" });
    expect(carga.sourceDocument).toBe("cartao_cidadao.pdf");
    expect(carga.conflicts).toEqual([]);
  });

  it("NÃO grava nada — a regra de ouro", async () => {
    const utilizador = userEvent.setup();
    montar();
    const [botao] = await waitFor(() => {
      const lista = screen.queryAllByRole("button", {
        name: "Extrair dados de cartao_cidadao.pdf",
      });
      expect(lista.length).toBeGreaterThan(0);
      return lista;
    });

    await utilizador.click(botao);
    await waitFor(() =>
      expect(
        rede.chamadas.some((c) => c.url.includes("/documents/extract")),
      ).toBe(true),
    );

    // O ponto do épico: a extracção é de LEITURA. Quem escreve é o
    // contentor, depois de o consultor confirmar no diálogo de revisão.
    expect(
      rede.chamadas.some((c) => c.url.includes("ai-apply-suggestions")),
    ).toBe(false);
  });

  it("uma extracção sem dados não chega ao contentor", async () => {
    // Abrir um diálogo de revisão vazio seria pior do que dizer que não deu.
    rede.extraccao = { success: true, extracted_data: {}, conflicts: [] };
    const utilizador = userEvent.setup();
    const { aoExtrair } = montar();
    const [botao] = await waitFor(() => {
      const lista = screen.queryAllByRole("button", {
        name: "Extrair dados de cartao_cidadao.pdf",
      });
      expect(lista.length).toBeGreaterThan(0);
      return lista;
    });

    await utilizador.click(botao);
    await waitFor(() =>
      expect(
        rede.chamadas.some((c) => c.url.includes("/documents/extract")),
      ).toBe(true),
    );
    expect(aoExtrair).not.toHaveBeenCalled();
  });

  it("um erro do backend não chega ao contentor", async () => {
    const erro = new Error("403");
    erro.response = { status: 403, data: { detail: "Sem permissão" } };
    rede.extraccao = erro;

    const utilizador = userEvent.setup();
    const { aoExtrair } = montar();
    const [botao] = await waitFor(() => {
      const lista = screen.queryAllByRole("button", {
        name: "Extrair dados de cartao_cidadao.pdf",
      });
      expect(lista.length).toBeGreaterThan(0);
      return lista;
    });

    await utilizador.click(botao);
    await waitFor(() =>
      expect(
        rede.chamadas.some((c) => c.url.includes("/documents/extract")),
      ).toBe(true),
    );
    expect(aoExtrair).not.toHaveBeenCalled();
  });
});
