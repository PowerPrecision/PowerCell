import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ProcessAssignDialog from "../ProcessAssignDialog";

// Regras de atribuição (Flavio, Nov 2026).
const users = [
  { id: "u-paulo", name: "Paulo", role: "consultor" },
  { id: "u-pedro", name: "Pedro", role: "consultor", so_leitura: true },
  { id: "u-diana", name: "Diana", role: "diretor" },
  { id: "u-marta", name: "Marta", role: "intermediario" },
  { id: "u-ivo", name: "Ivo", role: "indexacao" },
];

const base = {
  open: true,
  onOpenChange: vi.fn(),
  appUsers: users,
  loadingUsers: false,
  selectedConsultores: ["u-pedro"],
  setSelectedConsultores: vi.fn(),
  selectedMediadores: [],
  setSelectedMediadores: vi.fn(),
  selectedDirecao: [],
  setSelectedDirecao: vi.fn(),
  selectedIndexacao: "u-ivo",
  setSelectedIndexacao: vi.fn(),
  selectedParceiro: "",
  setSelectedParceiro: vi.fn(),
  onSave: vi.fn(),
};

describe("Gerir Atribuições — regras", () => {
  it("o diretor está na Direção e não nos Consultores", () => {
    render(<ProcessAssignDialog {...base} />);
    expect(within(screen.getByTestId("seccao-direcao")).getByText("Diana")).toBeInTheDocument();
    expect(within(screen.getByTestId("seccao-consultores")).queryByText("Diana")).toBeNull();
  });

  it("quem a outra empresa atribuiu aparece sem botão de retirar e não é opção", () => {
    render(<ProcessAssignDialog {...base} />);
    const seccao = screen.getByTestId("seccao-consultores");
    expect(within(seccao).getAllByText("Pedro")).toHaveLength(1); // só o selo, não a opção
    expect(within(seccao).queryByLabelText("Retirar Pedro")).toBeNull();
    expect(within(seccao).getByText("Paulo")).toBeInTheDocument();
  });

  it("o Index só vê o campo Index", () => {
    render(<ProcessAssignDialog {...base} soIndex />);
    expect(screen.queryByTestId("seccao-consultores")).toBeNull();
    expect(screen.queryByTestId("parceiro-select")).toBeNull();
    expect(screen.getByTestId("indexacao-select")).toBeInTheDocument();
  });
});
