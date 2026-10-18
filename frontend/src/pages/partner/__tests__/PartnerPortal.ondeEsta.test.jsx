/**
 * O parceiro vê ONDE o processo está (Out 2026).
 *
 * O parceiro é um angariador: traz o caso e a Empresa Y (destino) pode partilhá-lo em
 * cadeia com a Z sem a sua aprovação. Ele não executa, mas tem de saber onde está o caso
 * que trouxe — só o NOME da empresa; a linhagem inteira é do staff.
 *
 * Monta a árvore REAL; as respostas são as fixtures geradas pelo servidor
 * (`test_parceiro_contrato_frontend.py`) com o campo posto à mão só no sítio testado.
 */
import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/services/partnerApi", () => ({
  entrar: vi.fn(), obterPerfil: vi.fn(), lerConvite: vi.fn(), aceitarConvite: vi.fn(),
  mudarPalavraPasse: vi.fn(), obterPainel: vi.fn(), listarCasos: vi.fn(), obterCaso: vi.fn(),
  submeterLead: vi.fn(), obterDestinos: vi.fn(), obterUrlDeDescarga: vi.fn(), enviarFicheiro: vi.fn(),
  obterFormularioDoCliente: vi.fn(), guardarFormularioDoCliente: vi.fn(),
}));

import * as api from "@/services/partnerApi";
import { FIXTURES, montar, prepararApi } from "./montagem";

beforeEach(() => {
  prepararApi();
});

const comEmpresa = (nome) => ({
  ...FIXTURES.casos,
  items: FIXTURES.casos.items.map((c) => (c.id === "a-novo" ? { ...c, empresa_actual: nome } : c)),
});

describe("o parceiro vê onde o caso está", () => {
  it("a lista mostra a etiqueta da empresa «Empresa Z» no caso partilhado em cadeia", async () => {
    api.listarCasos.mockResolvedValue(comEmpresa("Empresa Z"));
    montar("/parceiro");
    const link = await screen.findByRole("link", { name: /Cliente a-novo/ });
    expect(within(link).getByTestId("empresa-do-caso")).toHaveTextContent("Empresa Z");
  });

  it("o detalhe também", async () => {
    api.obterCaso.mockImplementation(async () => ({ ...structuredClone(FIXTURES.casoDeProcesso), empresa_actual: "Empresa Z" }));
    montar("/parceiro/casos/a-novo");
    expect(await screen.findByText(/Está em Empresa Z/)).toBeInTheDocument();
  });

  it("duas empresas (ramificação) aparecem juntas", async () => {
    api.listarCasos.mockResolvedValue(comEmpresa("Empresa Z, Empresa K"));
    montar("/parceiro");
    const link = await screen.findByRole("link", { name: /Cliente a-novo/ });
    expect(within(link).getByTestId("empresa-do-caso")).toHaveTextContent("Empresa Z, Empresa K");
  });

  it("sem empresa conhecida não se inventa «Está em»", async () => {
    api.listarCasos.mockResolvedValue(comEmpresa(null));
    montar("/parceiro");
    const link = await screen.findByRole("link", { name: /Cliente a-novo/ });
    expect(within(link).queryByTestId("empresa-do-caso")).toBeNull();
    expect(within(link).queryByText(/Está em/)).toBeNull();
  });

  it("uma lead mostra a empresa de destino que o parceiro escolheu", async () => {
    api.listarCasos.mockResolvedValue({
      ...FIXTURES.casos,
      items: FIXTURES.casos.items.map((c) => (c.kind === "lead" ? { ...c, empresa_destino: "Power Real Estate" } : c)),
    });
    montar("/parceiro");
    const etiquetas = await screen.findAllByTestId("empresa-do-caso");
    expect(etiquetas.length).toBeGreaterThan(0);
    expect(etiquetas.every((e) => e.textContent === "Power Real Estate")).toBe(true);
  });

  it("o parceiro não vê a linhagem: nem setas nem quem passou a quem", async () => {
    api.listarCasos.mockResolvedValue(comEmpresa("Empresa Z"));
    montar("/parceiro");
    await screen.findByRole("link", { name: /Cliente a-novo/ });
    expect(screen.queryByTestId("linhagem-do-processo")).toBeNull();
    expect(screen.queryByText(/Partilhado por/)).toBeNull();
  });
});
