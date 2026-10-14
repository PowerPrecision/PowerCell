/**
 * Clientes Registados — Ativos vs Histórico (Lote 4, ponto 2) e âmbito do Master (ponto 1).
 *
 * Monta a PÁGINA: o separador «Histórico» existe, pede `historico=true` ao servidor, e TODO pedido
 * leva o contexto de empresa (`X-Company-Id`) — o `fetch` cru perdia-o e a lista misturava redes.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));
const sessao = vi.hoisted(() => ({ user: { id: "u1", name: "M", role: "master" } }));
vi.mock("../../contexts/AuthContext", () => ({ useAuth: () => sessao }));
vi.mock("../../services/api", async (original) => ({
  ...(await original()),
  cabecalhosDeContexto: () => ({ "X-Company-Id": "cmp-domus" }),
  getExportPermission: vi.fn(() => Promise.resolve({ data: { allow_excel_export: true } })),
}));
vi.mock("../../components/filters/ClientFilters", () => ({ default: () => <div /> }));
vi.mock("../../components/CreateProcessModal", () => ({ default: () => null }));
vi.mock("../../components/kanban/CreateClientModal", () => ({ default: () => null }));

import ClientsPage from "../ClientsPage";

const respostaDe = (clients, extra = {}) => ({
  ok: true,
  json: () => Promise.resolve({ clients, total: clients.length, ...extra }),
});

function Local() {
  const l = useLocation();
  return <span data-testid="url">{l.search}</span>;
}

function montar(url = "/clientes") {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Local />
      <Routes>
        <Route path="/clientes" element={<ClientsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const pedidosDeClientes = () =>
  globalThis.fetch.mock.calls.filter(([url]) => String(url).includes("/clients?"));

beforeEach(() => {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve(respostaDe([{ id: "c1", nome: "Ana Ativa", email: "a@x.pt", processes: [] }], { total_historico: 3 })),
  );
});

describe("ClientsPage — Ativos / Histórico", () => {
  it("por omissão pede a lista de trabalho (sem historico) e mostra quantos há no Histórico", async () => {
    montar();
    expect((await screen.findAllByText("Ana Ativa")).length).toBeGreaterThan(0);

    const [url] = pedidosDeClientes()[0];
    expect(String(url)).not.toContain("historico=true");
    expect(screen.getByTestId("clients-tab-ativos")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("clients-tab-historico")).toHaveTextContent("Histórico (3)");
  });

  it("o separador Histórico pede historico=true e fica no URL", async () => {
    montar();
    await screen.findAllByText("Ana Ativa");
    globalThis.fetch.mockClear();
    globalThis.fetch.mockImplementation(() =>
      Promise.resolve(respostaDe([{ id: "c9", nome: "Rui Concluído", email: "r@x.pt", processes: [] }], { total_historico: 3 })),
    );

    // Radix Tabs activa no `mousedown`, não no `click`.
    fireEvent.mouseDown(screen.getByTestId("clients-tab-historico"));

    expect((await screen.findAllByText("Rui Concluído")).length).toBeGreaterThan(0);
    expect(String(pedidosDeClientes().at(-1)[0])).toContain("historico=true");
    expect(screen.getByTestId("url")).toHaveTextContent("vista=historico");
    expect(screen.queryAllByText("Ana Ativa")).toHaveLength(0);
  });

  it("abrir directamente no Histórico (link/voltar) pede o histórico logo", async () => {
    montar("/clientes?vista=historico");
    await waitFor(() => expect(pedidosDeClientes().length).toBeGreaterThan(0));
    expect(String(pedidosDeClientes()[0][0])).toContain("historico=true");
    expect(screen.getByTestId("clients-tab-historico")).toHaveAttribute("aria-selected", "true");
  });

  it("TODO pedido leva o contexto de empresa (senão o Master vê todas as redes)", async () => {
    montar();
    await screen.findAllByText("Ana Ativa");
    const [, opcoes] = pedidosDeClientes()[0];
    expect(opcoes.headers["X-Company-Id"]).toBe("cmp-domus");
    expect(opcoes.headers.Authorization).toMatch(/^Bearer /);
  });

  it("a vista dos eliminados não mostra o separador (é outra vista)", async () => {
    montar("/clientes?status=deleted");
    await waitFor(() => expect(pedidosDeClientes().length).toBeGreaterThan(0));
    expect(screen.queryByTestId("clients-vista-tabs")).not.toBeInTheDocument();
  });
});
