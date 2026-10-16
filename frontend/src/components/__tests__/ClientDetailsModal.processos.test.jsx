/**
 * Modal de detalhes do cliente: «Processos» com ligação directa (Lote 7.3).
 *
 * A lista é o que o servidor devolve em `processes` — já recortado pela empresa activa e pelos partilhados
 * (provado em `test_lote73_processos_do_cliente_mongo.py`). Aqui afirma-se o que o ECRÃ faz com ela: mostra
 * só o que veio, abre cada processo, não inventa nada e pede o cliente pelo Axios (o `fetch` cru não leva o
 * `X-Company-Id` que decide o recorte).
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import fs from "node:fs";
import path from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ getClient: vi.fn(), resendPortalAccess: vi.fn() }));
vi.mock("../../services/api", () => api);
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import ClientDetailsModal from "../ClientDetailsModal";

const CLIENTE = {
  id: "cli-1", nome: "Joana Prata", nif: "123456789",
  processes: [
    { id: "p-1", process_number: 101, status: "novo", status_label: "Novo", process_type: "credito", client_role: "titular" },
    { id: "p-2", process_number: 202, status: "desistencia", status_label: "Desistência", client_role: "2º titular" },
  ],
};

const montar = (extra = {}) => render(
  <ClientDetailsModal open clientId="cli-1" onClose={vi.fn()} {...extra} />,
);

beforeEach(() => {
  vi.clearAllMocks();
  globalThis.fetch = vi.fn(() => { throw new Error("fetch cru não devia ser usado"); });
  api.getClient.mockResolvedValue({ data: CLIENTE });
});

describe("ClientDetailsModal — Processos", () => {
  it("lista os processos que o servidor devolveu, com estado e papel", async () => {
    montar();
    const secao = await screen.findByTestId("processos-do-cliente");

    expect(within(secao).getByText(/Processo 101/)).toBeInTheDocument();
    expect(within(secao).getByText(/Processo 202/)).toBeInTheDocument();
    expect(within(secao).getByText("Desistência")).toBeInTheDocument();
    expect(within(secao).getByText("2º titular")).toBeInTheDocument();
    expect(within(secao).getByRole("heading", { name: /Processos \(2\)/ })).toBeInTheDocument();
    expect(api.getClient).toHaveBeenCalledWith("cli-1");
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("cada processo tem a sua ligação para abrir", async () => {
    montar();
    const ligacoes = await screen.findAllByRole("link", { name: /Abrir processo/ });
    expect(ligacoes.map((a) => a.getAttribute("href"))).toEqual(["/processo/p-1", "/processo/p-2"]);
  });

  it("com `onNavigateToProcess` a ligação navega sem recarregar e fecha a modal", async () => {
    const onClose = vi.fn();
    const abrir = vi.fn();
    montar({ onClose, onNavigateToProcess: abrir });

    fireEvent.click((await screen.findAllByRole("link", { name: /Abrir processo 202/ }))[0]);

    expect(abrir).toHaveBeenCalledWith("p-2");
    expect(onClose).toHaveBeenCalled();
  });

  it("sem processos diz-o, em vez de uma secção vazia", async () => {
    api.getClient.mockResolvedValue({ data: { ...CLIENTE, processes: [] } });
    montar();
    expect(await screen.findByText(/Sem processos nesta empresa/)).toBeInTheDocument();
  });

  it("formas de dados reais: sem `processes`, não-lista, linhas sem id", async () => {
    api.getClient.mockResolvedValue({ data: { ...CLIENTE, processes: { 0: { id: "x" } } } });
    const a = montar();
    expect(await screen.findByText(/Sem processos nesta empresa/)).toBeInTheDocument();
    a.unmount();

    api.getClient.mockResolvedValue({ data: { ...CLIENTE, processes: [null, { process_number: 9 }, { id: "p-9", process_number: 9 }] } });
    montar();
    await waitFor(() => expect(screen.getAllByRole("link", { name: /Abrir processo/ })).toHaveLength(1));
  });

  it("o ecrã não filtra: mostra tudo o que o servidor mandou (a fronteira é do servidor)", async () => {
    api.getClient.mockResolvedValue({ data: { ...CLIENTE, processes: [CLIENTE.processes[1]] } });
    montar();
    await screen.findByTestId("processos-do-cliente");
    expect(screen.queryByText(/Processo 101/)).not.toBeInTheDocument();
    expect(screen.getByText(/Processo 202/)).toBeInTheDocument();
  });
});

describe("ClientDetailsModal — transporte", () => {
  it("nenhum `fetch` cru nem URL do backend", () => {
    const fonte = fs.readFileSync(path.resolve(process.cwd(), "src/components/ClientDetailsModal.jsx"), "utf-8")
      .replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
    expect(fonte).not.toMatch(/\bfetch\(/);
    expect(fonte).not.toMatch(/API_URL/);
    expect(fonte).toContain("getClient(");
  });
});
