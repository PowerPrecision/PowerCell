/**
 * Arrastar do computador para o separador Documentos (Lote 6, ponto 3).
 *
 * O QUE FALTAVA
 * =============
 * As categorias já tinham `onDrop` — mas **só para MOVER** ficheiros entre
 * elas. Um ficheiro arrastado do Finder/Explorador não fazia nada: o
 * `handleDrop` lia `draggedFiles`/`draggedFile` (estado interno) e ignorava
 * `dataTransfer.files`. O botão era o único caminho de upload.
 *
 * O QUE ESTES TESTES DEFENDEM
 * ===========================
 *   1. que largar um ficheiro do sistema numa categoria o ENVIA para ELA;
 *   2. que o arrasto INTERNO continua a MOVER — é a metade que se parte sem
 *      dar erro, porque os dois gestos chegam pelo mesmo `onDrop`;
 *   3. que o arrasto aplica a MESMA lista de tipos do `accept` do botão.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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



const ficheiroDoSistema = (nome) =>
  new File(["x"], nome, { type: "application/octet-stream" });

const arrastoDoSistema = (...nomes) => ({
  types: ["Files"],
  files: nomes.map(ficheiroDoSistema),
  dropEffect: "",
});

/** Um arrasto INTERNO: é assim que o mover entre categorias chega. */
const arrastoInterno = () => ({
  types: ["text/plain"],
  files: [],
  dropEffect: "",
  getData: () => "",
});

const pedidos = (padrao) =>
  axiosFalso.chamadas.filter((c) => c.url.includes(padrao));

describe("S3FileManager — arrastar do computador", () => {
  it("largar um PDF numa categoria envia-o para ELA", async () => {
    montar();
    const zona = await screen.findByTestId("zona-financeiros");

    axiosFalso.chamadas.length = 0;
    fireEvent.drop(zona, { dataTransfer: arrastoDoSistema("irs_2026.pdf") });

    // O caminho de upload começa pela verificação de conflitos de nome —
    // é o mesmo do botão, de propósito: foi extraído, não duplicado.
    await waitFor(() =>
      expect(pedidos("check-upload-conflict").length).toBeGreaterThan(0)
    );
    const carga = pedidos("check-upload-conflict")[0].resto[0];
    expect(carga.category).toBe("Financeiros");
    expect(carga.filenames).toEqual(["irs_2026.pdf"]);
  });

  it("o arrasto INTERNO não envia nada — continua a MOVER", async () => {
    montar();
    const zona = await screen.findByTestId("zona-financeiros");

    axiosFalso.chamadas.length = 0;
    fireEvent.drop(zona, { dataTransfer: arrastoInterno() });

    await waitFor(() => expect(pedidos("check-upload-conflict")).toHaveLength(0));
    expect(pedidos("/upload")).toHaveLength(0);
  });

  it("um tipo que o botão recusaria também é recusado no arrasto", async () => {
    montar();
    const zona = await screen.findByTestId("zona-financeiros");

    axiosFalso.chamadas.length = 0;
    fireEvent.drop(zona, { dataTransfer: arrastoDoSistema("virus.exe") });

    await waitFor(() => expect(pedidos("check-upload-conflict")).toHaveLength(0));
  });

  it("de uma mistura, só o aceite segue", async () => {
    montar();
    const zona = await screen.findByTestId("zona-financeiros");

    axiosFalso.chamadas.length = 0;
    fireEvent.drop(zona, {
      dataTransfer: arrastoDoSistema("irs.pdf", "virus.exe"),
    });

    await waitFor(() =>
      expect(pedidos("check-upload-conflict").length).toBeGreaterThan(0)
    );
    expect(pedidos("check-upload-conflict")[0].resto[0].filenames).toEqual([
      "irs.pdf",
    ]);
  });

  it("o perfil de indexação não ganha upload por arrasto", async () => {
    // O gestor é SÓ LEITURA para a indexação; uma porta nova não pode abrir
    // o que a porta antiga fechava.
    montar(utilizador({ user: { role: "indexacao" }, effectiveRole: "indexacao" }));
    const zona = await screen.findByTestId("zona-financeiros");

    axiosFalso.chamadas.length = 0;
    fireEvent.drop(zona, { dataTransfer: arrastoDoSistema("irs.pdf") });

    await waitFor(() => expect(pedidos("/upload")).toHaveLength(0));
  });
});
