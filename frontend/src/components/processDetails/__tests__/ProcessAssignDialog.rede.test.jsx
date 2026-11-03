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
  // Nov 2026: a fronteira passou a ser a EMPRESA (regras do Flavio).
  it("diz que só aparecem pessoas da empresa e que a outra empresa não se altera", () => {
    render(<ProcessAssignDialog {...props} />);

    expect(screen.getByText(/Só aparecem pessoas da empresa/i)).toBeInTheDocument();
    expect(screen.getByText(/outra empresa/)).toBeInTheDocument();
  });
});
