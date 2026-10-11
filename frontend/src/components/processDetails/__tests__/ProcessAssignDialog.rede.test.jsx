/**
 * O diálogo de atribuição diz a verdade sobre a regra de rede (Via Rápida
 * extinta): só aparece gente da própria rede, e para passar o processo a
 * outra empresa há a Partilha Explícita. Sem a nota, quem procura um
 * colega de outra empresa conclui que o ecrã está partido.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import ProcessAssignDialog from "../ProcessAssignDialog";

const props = {
  open: true,
  onOpenChange: vi.fn(),
  clientName: "Cliente de Teste",
  processNumber: 42,
  loadingUsers: false,
  appUsers: [],
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

describe("ProcessAssignDialog — a regra de rede", () => {
  it("diz que só aparecem pessoas da rede e aponta a Partilha Explícita", () => {
    render(<ProcessAssignDialog {...props} />);

    expect(screen.getByText(/só aparecem\s+pessoas da sua rede/i)).toBeInTheDocument();
    expect(screen.getByText(/Partilhar com Empresa/)).toBeInTheDocument();
  });
});
