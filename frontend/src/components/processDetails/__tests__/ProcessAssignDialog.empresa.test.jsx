/**
 * Nas listas de atribuição cada pessoa mostra a EMPRESA a que pertence (atribuições B2B):
 * quem atribui tem de saber se está a escolher alguém da Power ou da Precision.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";

import ProcessAssignDialog from "../ProcessAssignDialog";

const utilizadores = [
  { id: "c-1", name: "Ana Consultora", role: "consultor", empresa_etiqueta: "Power", empresas: ["Power"] },
  { id: "c-2", name: "Bruno Consultor", role: "consultor", empresa_etiqueta: "Precision · Domus", empresas: ["Domus", "Precision"] },
  { id: "c-3", name: "Carla Sem Empresa", role: "consultor" },
  { id: "i-1", name: "Inês Intermediária", role: "intermediario", empresa_etiqueta: "Precision" },
  { id: "x-1", name: "Xavier Index", role: "indexacao", empresa_etiqueta: "Precision" },
  { id: "p-1", name: "Paula Parceira", role: "parceiro", empresa_etiqueta: "Domus" },
];

const props = {
  open: true,
  onOpenChange: vi.fn(),
  clientName: "Cliente de Teste",
  processNumber: 42,
  loadingUsers: false,
  appUsers: utilizadores,
  selectedConsultores: [],
  setSelectedConsultores: vi.fn(),
  selectedMediadores: [],
  setSelectedMediadores: vi.fn(),
  selectedIndexacao: "",
  setSelectedIndexacao: vi.fn(),
  selectedParceiro: "",
  setSelectedParceiro: vi.fn(),
  savingAssignment: false,
  onSave: vi.fn(),
};

const linhaDe = (nome) => screen.getByText(nome).closest("label");

describe("ProcessAssignDialog — empresa de cada pessoa", () => {
  it("mostra a empresa à frente do nome do consultor", () => {
    render(<ProcessAssignDialog {...props} />);

    expect(within(linhaDe("Ana Consultora")).getByTestId("empresa-do-utilizador")).toHaveTextContent("Power");
  });

  it("quem tem mais do que uma empresa mostra a etiqueta completa do servidor", () => {
    render(<ProcessAssignDialog {...props} />);

    expect(within(linhaDe("Bruno Consultor")).getByTestId("empresa-do-utilizador")).toHaveTextContent(
      "Precision · Domus",
    );
  });

  it("mostra a empresa no intermediário", () => {
    render(<ProcessAssignDialog {...props} />);

    expect(within(linhaDe("Inês Intermediária")).getByTestId("empresa-do-utilizador")).toHaveTextContent(
      "Precision",
    );
  });

  it("sem empresa dita pelo servidor não desenha etiqueta nenhuma (nem a inventa)", () => {
    render(<ProcessAssignDialog {...props} />);

    expect(within(linhaDe("Carla Sem Empresa")).queryByTestId("empresa-do-utilizador")).toBeNull();
  });

  it("o resumo dos seleccionados também leva a empresa", () => {
    render(<ProcessAssignDialog {...props} selectedConsultores={["c-1"]} />);

    const chip = screen.getAllByText("Ana Consultora").map((e) => e.closest("[class*='secondary']")).find(Boolean);
    expect(chip).toBeTruthy();
    expect(within(chip).getByTestId("empresa-do-utilizador")).toHaveTextContent("Power");
  });
});
