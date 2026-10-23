import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

const AQUI = dirname(fileURLToPath(import.meta.url));
let utilizador;
vi.mock("../contexts/AuthContext", () => ({ useAuth: () => ({ user: utilizador }) }));

import RequerModuloIndex from "./RequerModuloIndex";

function montar(user) {
  utilizador = user;
  return render(
    <MemoryRouter initialEntries={["/index"]}>
      <Routes>
        <Route path="/index" element={<RequerModuloIndex><p>fila do Index</p></RequerModuloIndex>} />
        <Route path="/staff" element={<p>painel</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RequerModuloIndex", () => {
  it("rede sem Index: o link directo vai ao painel (mesmo para o Master)", () => {
    montar({ role: "master", capabilities: { has_index: false } });
    expect(screen.getByText("painel")).toBeInTheDocument();
    expect(screen.queryByText("fila do Index")).not.toBeInTheDocument();
  });

  it("rede com Index: a fila abre", () => {
    montar({ role: "diretor", capabilities: { has_index: true } });
    expect(screen.getByText("fila do Index")).toBeInTheDocument();
  });

  it("sem o contrato (sessão antiga): falha aberta", () => {
    montar({ role: "diretor" });
    expect(screen.getByText("fila do Index")).toBeInTheDocument();
  });
});

describe("a ligação em App.js", () => {
  it("a rota /index (supervisão) passa por RequerModuloIndex, dentro do ProtectedRoute", async () => {
    const fonte = readFileSync(join(AQUI, "..", "App.js"), "utf8");
    const rota = fonte.slice(fonte.indexOf('path="/index"'), fonte.indexOf('path="/index/pesquisa"'));
    expect(rota.indexOf("<ProtectedRoute")).toBeGreaterThan(-1);
    expect(rota.indexOf("<RequerModuloIndex>")).toBeGreaterThan(rota.indexOf("<ProtectedRoute"));
    expect(rota.indexOf("<IndexDashboardPage")).toBeGreaterThan(rota.indexOf("<RequerModuloIndex>"));
  });
});
