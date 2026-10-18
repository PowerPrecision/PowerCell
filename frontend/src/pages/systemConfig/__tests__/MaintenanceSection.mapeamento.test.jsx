/**
 * Mapeamento S3 MONTADO (QA-6): nomes legíveis, ponteiros de processo visíveis no seletor e o
 * filtro «Apenas sem mapeamento» a pedir ao servidor.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn(), loading: vi.fn() },
}));

const listar = vi.fn();
vi.mock("@/services/api", () => ({
  getS3Relink: vi.fn().mockResolvedValue({ data: { entidades: [], pastas: [] } }),
  setS3Relink: vi.fn(),
  listClientS3Mappings: (...a) => listar(...a),
}));
vi.mock("../../../services/api", () => ({
  getS3Relink: vi.fn().mockResolvedValue({ data: { entidades: [], pastas: [] } }),
  setS3Relink: vi.fn(),
  listClientS3Mappings: (...a) => listar(...a),
}));

import MaintenanceSection from "../MaintenanceSection";

const RAIZ = "Documentação Clientes/";
const UUID = "9f1c3a52-1111-4111-8111-aaaaaaaaaaaa";

const resposta = (processos, extra = {}) => ({
  data: {
    s3_configured: true,
    stats: { total: 120, mapped: 80, unmapped: 40 },
    total: processos.length,
    pages: 1,
    available_folders: [
      { path: `${RAIZ}${UUID}`, name: UUID, display_name: "Ana Costa" },
      { path: `${RAIZ}Joao_Silva`, name: "Joao_Silva", display_name: "Joao_Silva" },
    ],
    processes: processos,
    ...extra,
  },
});

const processoMapeado = {
  id: "p1", client_name: "Ana Costa", process_number: "7", status: "em_curso",
  s3_folder: `${RAIZ}${UUID}/processos/p1`, s3_folder_display: "Ana Costa › Processo n.º 7",
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({}), text: async () => "" }));
});

const montarECarregar = async () => {
  render(<MaintenanceSection token="t" user={{ id: "u", role: "master", name: "N" }} />);
  const bloco = screen.getByRole("heading", { name: /Mapeamento Clientes\/Processos/ }).closest(".rounded-lg");
  fireEvent.click(within(bloco).getByRole("button", { name: /^carregar$/i }));
  await screen.findByText("Ana Costa", { selector: "span.font-medium" });
};

describe("Mapeamento S3 montado", () => {
  it("um processo com pasta de processo NÃO aparece como «Sem mapeamento»", async () => {
    listar.mockResolvedValue(resposta([processoMapeado]));
    await montarECarregar();

    const seletor = screen.getAllByRole("combobox").find((c) => c.querySelector('option[value=""]'));
    expect(seletor.value).toBe(processoMapeado.s3_folder);
    expect(screen.getByTestId("pasta-legivel")).toHaveTextContent("Ana Costa › Processo n.º 7");
  });

  it("as opções mostram o nome do cliente e nunca o uuid", async () => {
    listar.mockResolvedValue(resposta([processoMapeado]));
    await montarECarregar();
    const seletor = screen.getAllByRole("combobox").find((c) => c.querySelector('option[value=""]'));
    const rotulos = Array.from(seletor.querySelectorAll("option")).map((o) => o.textContent);
    expect(rotulos).toContain("Ana Costa");
    expect(rotulos.join("|")).not.toContain(UUID);
  });

  it("«Apenas sem mapeamento» pede ao SERVIDOR has_mapping=false (todas as páginas)", async () => {
    listar.mockResolvedValue(resposta([processoMapeado]));
    await montarECarregar();
    listar.mockClear();
    listar.mockResolvedValue(resposta([]));

    fireEvent.click(screen.getByLabelText(/apenas sem mapeamento/i));
    await waitFor(() => expect(listar).toHaveBeenCalled(), { timeout: 2000 });
    expect(listar.mock.calls[0][0]).toMatchObject({ hasMapping: false, page: 1 });
  });

  it("os cartões mostram as contagens do servidor, não as da página", async () => {
    listar.mockResolvedValue(resposta([processoMapeado]));
    await montarECarregar();
    expect(screen.getByText("120")).toBeInTheDocument();
    expect(screen.getByText("80")).toBeInTheDocument();
    expect(screen.getByText("40")).toBeInTheDocument();
  });

  it("há paginação quando o servidor tem mais do que uma página", async () => {
    listar.mockResolvedValue(resposta([processoMapeado], { pages: 3 }));
    await montarECarregar();
    expect(screen.getByTestId("paginacao-mapeamento")).toHaveTextContent("Página 1 de 3");
    listar.mockClear();
    listar.mockResolvedValue(resposta([processoMapeado], { pages: 3 }));
    fireEvent.click(screen.getByRole("button", { name: /seguinte/i }));
    await waitFor(() => expect(listar).toHaveBeenCalled());
    expect(listar.mock.calls[0][0]).toMatchObject({ page: 2 });
  });
});
