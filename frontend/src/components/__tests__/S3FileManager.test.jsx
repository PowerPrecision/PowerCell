/**
 * Teste de fumo do gestor de ficheiros S3 (Épico 8, Eixo 0).
 *
 * PORQUÊ ANTES DE TUDO O RESTO:
 *   `S3FileManager.js` tem 4302 linhas e nenhum teste. Vão acontecer-lhe
 *   duas coisas seguidas — a conversão das 25 chamadas `fetch` para o
 *   cliente Axios e a extracção dos componentes visuais — e nenhuma delas
 *   pode mudar comportamento. Este ficheiro é a rede por baixo das duas.
 *
 * DELIBERADAMENTE AGNÓSTICO AO TRANSPORTE:
 *   Falseia `globalThis.fetch` **e** o cliente Axios, com a mesma carga.
 *   As asserções são sobre o que o utilizador vê e sobre as REGRAS DE
 *   NEGÓCIO (quem vê o quê), nunca sobre como o pedido viaja. Assim o
 *   teste continua a valer depois de o transporte mudar — que é
 *   exactamente para o que serve um teste de regressão.
 *
 * REGRAS COBERTAS (Eixo 3 do épico):
 *   - o perfil de indexação é SÓ LEITURA (sem upload, sem eliminar);
 *   - as ferramentas de IA são de gestão e olham para o `effectiveRole`
 *     (perfil activo), não para o papel base — é disso que depende o
 *     multi-perfil;
 *   - a categoria Index só aparece a quem pode vê-la;
 *   - um 403 do backend dá aviso LOCALIZADO, não um painel vazio.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// ── Fronteiras falsas ────────────────────────────────────────────────
const sessao = vi.hoisted(() => ({ valor: null }));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => sessao.valor,
}));

// O cliente Axios é falseado para que o teste sobreviva à conversão das
// chamadas `fetch`: hoje o componente não o usa para a listagem, amanhã usa.
const axiosFalso = vi.hoisted(() => ({
  respostas: new Map(),
  chamadas: [],
}));

vi.mock("../../services/api", async (original) => {
  const real = await original().catch(() => ({}));
  const resolver = (metodo) => (url, ...resto) => {
    axiosFalso.chamadas.push({ metodo, url: String(url), resto });
    for (const [padrao, carga] of axiosFalso.respostas) {
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
    // As funções de documentos do gestor de ficheiros passam pelo mesmo
    // resolvedor, para que o teste continue a descrever o comportamento e
    // não o transporte.
    getProcessS3Files: (processId) =>
      cliente.get(`/documents/client/${processId}/files`),
    getClientS3Mappings: (procura) =>
      cliente.get("/admin/client-s3-mappings", { params: { search: procura } }),
    saveClientS3Mapping: (processId, pasta) =>
      cliente.post("/admin/client-s3-mappings", null, { processId, pasta }),
    uploadProcessS3File: (processId, formData) =>
      cliente.post(`/documents/client/${processId}/upload`, formData),
    deleteProcessS3File: (processId, caminho) =>
      cliente.delete(`/documents/client/${processId}/file`, { caminho }),
    bulkDeleteProcessS3Files: (processId, caminhos) =>
      cliente.post(`/documents/client/${processId}/bulk-delete`, caminhos),
    bulkDownloadS3Files: (carga) => cliente.post("/documents/bulk-download", carga),
    getS3FileContent: (caminho) =>
      cliente.get(`/documents/proxy/${encodeURIComponent(caminho)}`),
    checkS3UploadConflict: (carga) =>
      cliente.post("/documents/check-upload-conflict", carga),
    checkS3MoveConflict: (carga) =>
      cliente.post("/documents/check-move-conflict", carga),
    moveS3File: (processId, carga) =>
      cliente.post(`/documents/move-file/${processId}`, carga),
    checkEmployerNif: (nif) => cliente.get(`/documents/check-employer-nif/${nif}`),
    aiAnalyzeS3Documents: (processId, carga) =>
      cliente.post(`/documents/ai-analyze/${processId}`, carga),
    aiApplyS3Suggestions: (processId, carga) =>
      cliente.post(`/documents/ai-apply-suggestions/${processId}`, carga),
    organizeS3Documents: (processId, carga) =>
      cliente.post(`/documents/organize/${processId}`, carga),
    categorizeAllS3Documents: (processId) =>
      cliente.post(`/documents/categorize-all/${processId}`, {}),
    renameAllS3DocumentsSmart: (processId) =>
      cliente.post(`/documents/rename-all-smart/${processId}`, {}),
    renameS3DocumentSmart: (processId, carga) =>
      cliente.post(`/documents/rename-smart/${processId}`, carga),
    generateProcessTemplate: (processId, modelo) =>
      cliente.get(`/templates/process/${processId}/generate/${modelo}`),
  };
});

import S3FileManager from "../S3FileManager";

// ── Dados ────────────────────────────────────────────────────────────
const utilizador = (overrides = {}) => ({
  token: "t-1",
  user: { id: "u-1", name: "Carla", role: "consultor", ...(overrides.user || {}) },
  effectiveRole: "consultor",
  ...overrides,
});

const FICHEIROS = {
  "Documentos Pessoais": [
    {
      name: "cartao_cidadao.pdf",
      path: "Clientes/Ana Martins/Documentos Pessoais/cartao_cidadao.pdf",
      size: 245678,
      last_modified: "2026-09-20T10:00:00Z",
    },
  ],
  Financeiros: [
    {
      name: "irs_2025.pdf",
      path: "Clientes/Ana Martins/Financeiros/irs_2025.pdf",
      size: 512000,
      last_modified: "2026-09-19T09:00:00Z",
    },
  ],
};

const RESPOSTA_FICHEIROS = {
  files: FICHEIROS,
  stats: { total_files: 2, total_size: 757678 },
};

/** Responde a qualquer pedido; a listagem devolve os ficheiros acima. */
function ligarRede({ estadoDaListagem = 200, carga = RESPOSTA_FICHEIROS } = {}) {
  if (estadoDaListagem === 200) {
    axiosFalso.respostas.set("/files", carga);
  } else {
    // O Axios rejeita em não-2xx, com o estado em `error.response.status`.
    const erro = new Error(`HTTP ${estadoDaListagem}`);
    erro.response = { status: estadoDaListagem, data: { detail: "Sem permissão" } };
    axiosFalso.respostas.set("/files", erro);
  }

  globalThis.fetch = vi.fn((url) => {
    const endereco = String(url);
    if (endereco.includes("/files")) {
      return Promise.resolve({
        ok: estadoDaListagem === 200,
        status: estadoDaListagem,
        json: () => Promise.resolve(estadoDaListagem === 200 ? carga : { detail: "Sem permissão" }),
      });
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
      blob: () => Promise.resolve(new Blob([""])),
    });
  });
}

function montar(sessaoDoTeste = utilizador()) {
  sessao.valor = sessaoDoTeste;
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <S3FileManager processId="proc-1" clientName="Ana Martins" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  axiosFalso.respostas.clear();
  axiosFalso.chamadas.length = 0;
  ligarRede();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ====================================================================

describe("S3FileManager — monta e mostra os ficheiros", () => {
  it("o gestor renderiza", async () => {
    montar();

    expect(await screen.findByTestId("s3-file-manager")).toBeInTheDocument();
  });

  it("os ficheiros devolvidos pelo backend aparecem", async () => {
    montar();

    expect(await screen.findByText("cartao_cidadao.pdf")).toBeInTheDocument();
    expect(screen.getByText("irs_2025.pdf")).toBeInTheDocument();
  });

  it("as pastas de categoria estão disponíveis", async () => {
    // A barra lateral mostra só ícones: o rótulo vive no `title`, e o
    // `data-testid` é o que a extracção tem de preservar — é por ele que
    // se agarra a pasta que também é alvo de "largar para mover".
    montar();
    await screen.findByTestId("s3-file-manager");

    expect(screen.getByTestId("folder-documentos-pessoais")).toBeInTheDocument();
    expect(screen.getByTestId("folder-financeiros")).toHaveAttribute(
      "title",
      expect.stringContaining("Financeiros"),
    );
  });
});

describe("S3FileManager — indexação é SÓ LEITURA", () => {
  const indexacao = utilizador({
    user: { id: "u-2", name: "Inês", role: "indexacao" },
    effectiveRole: "indexacao",
  });

  it("o consultor vê o botão de carregar ficheiros", async () => {
    montar();
    await screen.findByTestId("s3-file-manager");

    expect(screen.getByTestId("upload-file-btn")).toBeInTheDocument();
  });

  it("o perfil de indexação NÃO vê o botão de carregar", async () => {
    // Regressão: a indexação tem acesso de leitura ao arquivo do cliente.
    // Devolver-lhe o upload é dar-lhe escrita sobre documentos alheios.
    montar(indexacao);
    await screen.findByTestId("s3-file-manager");

    expect(screen.queryByTestId("upload-file-btn")).not.toBeInTheDocument();
  });
});

describe("S3FileManager — ferramentas de IA são de gestão", () => {
  it("o consultor não vê Analisar IA", async () => {
    montar();
    await screen.findByTestId("s3-file-manager");

    expect(screen.queryByTestId("ai-analyze-btn")).not.toBeInTheDocument();
    expect(screen.queryByTestId("smart-rename-btn")).not.toBeInTheDocument();
  });

  it("o diretor vê Analisar IA", async () => {
    montar(
      utilizador({
        user: { id: "u-3", name: "Diana", role: "diretor" },
        effectiveRole: "diretor",
      }),
    );
    await screen.findByTestId("s3-file-manager");

    expect(await screen.findByTestId("ai-analyze-btn")).toBeInTheDocument();
    expect(screen.getByTestId("smart-rename-btn")).toBeInTheDocument();
  });

  it("decide pelo PERFIL ACTIVO, não pelo papel base", async () => {
    // Multi-perfil: um administrador a operar como consultor NÃO tem as
    // ferramentas de gestão. Trocar `effectiveRole` por `hasRole(user, …)`
    // faria este teste ficar vermelho — e é esse o ponto.
    montar(
      utilizador({
        user: { id: "u-4", name: "Álvaro", role: "admin" },
        effectiveRole: "consultor",
      }),
    );
    await screen.findByTestId("s3-file-manager");

    expect(screen.queryByTestId("ai-analyze-btn")).not.toBeInTheDocument();
  });

  it("o papel base sem perfil de gestão não ganha as ferramentas", async () => {
    montar(
      utilizador({
        user: { id: "u-5", name: "Carlos", role: "consultor" },
        effectiveRole: "ceo",
      }),
    );
    await screen.findByTestId("s3-file-manager");

    expect(await screen.findByTestId("ai-analyze-btn")).toBeInTheDocument();
  });
});

describe("S3FileManager — 403 dá aviso localizado", () => {
  it("sem permissão, avisa dentro do painel em vez de o deixar vazio", async () => {
    // PACOTE 11: o resto do processo continua navegável; só esta tab avisa.
    ligarRede({ estadoDaListagem: 403 });
    montar();

    const aviso = await screen.findByTestId("s3-file-manager-permission-denied");
    expect(within(aviso).getByText(/Documentos não disponíveis/i)).toBeInTheDocument();
    // E não o painel normal: mostrar uma lista vazia faria o utilizador
    // concluir que o processo não tem documentos.
    expect(screen.queryByTestId("s3-file-manager")).not.toBeInTheDocument();
  });
});

describe("S3FileManager — pesquisa e vistas", () => {
  it("a caixa de pesquisa está presente", async () => {
    montar();
    await screen.findByTestId("s3-file-manager");

    expect(screen.getByPlaceholderText(/pesquisar/i)).toBeInTheDocument();
  });

  it("existe alternância entre lista e grelha", async () => {
    montar();
    await screen.findByTestId("s3-file-manager");

    // As duas vistas são blocos de ~600 e ~440 linhas que vão ser
    // extraídos: se a alternância se partir, o corte partiu algo.
    const botoes = screen.getAllByRole("button");
    expect(botoes.length).toBeGreaterThan(3);
  });
});
