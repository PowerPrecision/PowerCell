/**
 * A secção de Manutenção MONTADA — sem isto o painel pode não existir.
 *
 * É a regra que este projecto aprendeu três vezes: um componente novo só está
 * coberto quando o ECRÃ que o deve conter é montado. O teste do painel sozinho
 * passa com ele desligado da página, e o `SystemConfigPage` já produziu um ecrã
 * em branco exactamente por aqui.
 *
 * E a porta: o religamento é exclusivo do MASTER (o único perfil global), porque a escrita move
 * a fronteira de posse de documentos (depois dela,
 * `assert_s3_file_belongs_to_process` autoriza tudo o que estiver na pasta
 * escolhida). A rota entra por `require_roles([MASTER])`; este teste é o lado
 * do ecrã.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn(), loading: vi.fn(),
  },
}));

vi.mock("@/services/api", () => ({
  getS3Relink: vi.fn().mockResolvedValue({ data: { entidades: [], pastas: [] } }),
  setS3Relink: vi.fn(),
}));

import MaintenanceSection from "../MaintenanceSection";

beforeEach(() => {
  vi.clearAllMocks();
  // `vi.stubGlobal` e não `global.fetch`: `global` não está definido no
  // ambiente de lint deste projecto (ESM), e o stub é desfeito sozinho.
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
      text: async () => "",
    })
  );
});

const montar = (role) =>
  render(
    <MaintenanceSection token="t" user={{ id: "u", role, name: "N" }} />
  );

describe("Religamento manual na secção de Manutenção", () => {
  it("o Master vê o painel", () => {
    montar("master");
    expect(screen.getByTestId("painel-religamento")).toBeInTheDocument();
  });

  it("o painel vive DENTRO da área de mapeamento S3", () => {
    // O pedido foi explícito: na área já existente de mapeamento, não no
    // detalhe do cliente/processo.
    montar("master");
    expect(
      screen.getByText(/Mapeamento Clientes\/Processos → Pastas S3/i)
    ).toBeInTheDocument();
    expect(screen.getByTestId("painel-religamento")).toBeInTheDocument();
  });

  it("o CEO NÃO vê — não é hierarquia, é a fronteira de posse", () => {
    montar("ceo");
    expect(screen.queryByTestId("painel-religamento")).toBeNull();
  });

  it("o Admin (perfil local) NÃO vê — a escrita atravessa empresas", () => {
    montar("admin");
    expect(screen.queryByTestId("painel-religamento")).toBeNull();
  });

  it("a Direcção não vê", () => {
    montar("diretor");
    expect(screen.queryByTestId("painel-religamento")).toBeNull();
  });

  it("o consultor não vê", () => {
    montar("consultor");
    expect(screen.queryByTestId("painel-religamento")).toBeNull();
  });
});
