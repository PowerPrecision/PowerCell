/**
 * Clientes Registados — paginação, ordenação e «Por Parceiro» no SERVIDOR (P4).
 *
 * Monta a PÁGINA: o pedido leva `page`/`size`/`sort_field`/`sort_order`, a página vive no URL, mudar
 * de filtro volta à primeira, e a exportação percorre TODAS as páginas (e não só a que está no ecrã).
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));
vi.mock("../../contexts/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1", name: "M", role: "master" } }) }));
vi.mock("../../services/api", async (original) => ({
  ...(await original()),
  cabecalhosDeContexto: () => ({}),
  getExportPermission: vi.fn(() => Promise.resolve({ data: { allow_excel_export: true } })),
}));
// O filtro real tem um `useQuery`; aqui só interessa o que a PÁGINA faz com o valor que ele devolve.
vi.mock("../../components/filters/ClientFilters", () => ({
  default: ({ parceiro, onParceiroChange }) => (
    <div>
      <span data-testid="parceiro-activo">{parceiro}</span>
      <button type="button" onClick={() => onParceiroChange("pt-1")}>escolher parceiro</button>
    </div>
  ),
}));
vi.mock("../../components/CreateProcessModal", () => ({ default: () => null }));
vi.mock("../../components/kanban/CreateClientModal", () => ({ default: () => null }));
const xlsx = vi.hoisted(() => ({ linhas: null }));
vi.mock("xlsx", () => ({
  utils: {
    json_to_sheet: (rows) => { xlsx.linhas = rows; return {}; },
    book_new: () => ({}),
    book_append_sheet: () => {},
  },
  writeFile: () => {},
}));

import ClientsPage from "../ClientsPage";

const clientes = (n, de = 0) =>
  Array.from({ length: n }, (_, i) => ({ id: `c${de + i}`, nome: `Cliente ${de + i}`, contacto: {}, processes: [] }));

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

// O ecrã desenha a tabela e os cartões (duas vezes cada nome): espera-se por QUALQUER ocorrência.
const aparece = async (nome) => expect((await screen.findAllByText(nome)).length).toBeGreaterThan(0);

const pedidos = () => globalThis.fetch.mock.calls.map(([url]) => new URL(String(url)).searchParams);

beforeEach(() => {
  globalThis.fetch = vi.fn((url) => {
    const p = new URL(String(url)).searchParams;
    const numero = Number(p.get("page") || 1);
    const tamanho = Number(p.get("size") || 50);
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({
        clients: clientes(tamanho, (numero - 1) * tamanho).slice(0, numero === 3 ? 20 : tamanho),
        total: 120, page: numero, size: tamanho, pages: Math.ceil(120 / tamanho),
      }),
    });
  });
});

describe("ClientsPage — paginação no servidor", () => {
  it("pede a primeira página de 50, com a ordenação, e mostra o total", async () => {
    montar();
    await aparece("Cliente 0");
    const [primeiro] = pedidos();
    expect(primeiro.get("page")).toBe("1");
    expect(primeiro.get("size")).toBe("50");
    expect(primeiro.get("sort_field")).toBe("created_at");
    expect(primeiro.get("sort_order")).toBe("desc");
    expect(primeiro.get("limit")).toBeNull(); // acabou o «500 de uma vez»
    expect(screen.getByTestId("paginacao-intervalo")).toHaveTextContent("1–50 de 120 clientes");
  });

  it("«Seguinte» pede a página 2 e guarda-a no URL", async () => {
    montar();
    await aparece("Cliente 0");
    fireEvent.click(screen.getByTestId("paginacao-seguinte"));
    await aparece("Cliente 50");
    expect(screen.getByTestId("url")).toHaveTextContent("page=2");
    expect(pedidos().at(-1).get("page")).toBe("2");
  });

  it("abrir diretamente a página 3 pede a página 3", async () => {
    montar("/clientes?page=3");
    await aparece("Cliente 100");
    expect(pedidos()[0].get("page")).toBe("3");
    expect(screen.getByTestId("paginacao-intervalo")).toHaveTextContent("101–120 de 120 clientes");
  });

  it("escolher um parceiro envia-o ao servidor e volta à primeira página", async () => {
    montar("/clientes?page=2");
    await aparece("Cliente 50");
    fireEvent.click(screen.getByText("escolher parceiro"));
    await waitFor(() => expect(pedidos().at(-1).get("parceiro")).toBe("pt-1"));
    expect(pedidos().at(-1).get("page")).toBe("1");
    expect(screen.getByTestId("url")).not.toHaveTextContent("page=");
    expect(screen.getByTestId("parceiro-activo")).toHaveTextContent("pt-1");
  });

  it("sem parceiro escolhido o pedido não leva o parâmetro", async () => {
    montar();
    await aparece("Cliente 0");
    expect(pedidos()[0].has("parceiro")).toBe(false);
  });

  it("exportar percorre TODAS as páginas de 200 e junta o conjunto inteiro (450 clientes → 3 pedidos)", async () => {
    montar();
    await aparece("Cliente 0");
    globalThis.fetch.mockClear();
    globalThis.fetch.mockImplementation((url) => {
      const p = new URL(String(url)).searchParams;
      const numero = Number(p.get("page") || 1);
      const tamanho = Number(p.get("size") || 50);
      const nesta = Math.max(0, Math.min(tamanho, 450 - (numero - 1) * tamanho));
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          clients: clientes(nesta, (numero - 1) * tamanho), total: 450, page: numero, size: tamanho,
          pages: Math.ceil(450 / tamanho),
        }),
      });
    });
    fireEvent.click(screen.getByRole("button", { name: /exportar excel/i }));
    await waitFor(() => expect(xlsx.linhas).not.toBeNull());
    const chamadas = pedidos();
    expect(chamadas.every((p) => p.get("size") === "200")).toBe(true);
    expect(chamadas.map((p) => p.get("page"))).toEqual(["1", "2", "3"]);
    expect(xlsx.linhas).toHaveLength(450);
  });
});
