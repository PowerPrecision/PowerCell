/**
 * O separador Histórico é uma trilha de auditoria — só de leitura (Ponto 9).
 *
 * O PEDIDO: "No separador Histórico, não pode ser possível adicionar
 * atividades manualmente. O histórico passa a ser read-only para os
 * utilizadores, servindo apenas como uma linha temporal gerada
 * automaticamente pelo sistema."
 *
 * PORQUE É QUE ISTO PRECISA DE UM TESTE E NÃO BASTA APAGAR O CÓDIGO
 *   Uma UI removida volta com a mesma facilidade com que saiu, e é a
 *   forma de regressão mais fácil de não dar por ela: não parte nada,
 *   não dá erro, apenas repõe um botão que alguém achou que faltava. O
 *   que este teste afirma é a AUSÊNCIA — e as ausências só se defendem
 *   com asserções.
 *
 * As afirmações são pelo papel e pelo nome acessível, não por classe
 * CSS: um botão de adicionar que reaparecesse com outro `data-testid`
 * continuaria a ser apanhado.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../../ProcessTimeline", () => ({
  default: () => <div data-testid="timeline-de-fases" />,
}));

vi.mock("../../../UnifiedAuditTrail", () => ({
  default: () => <div data-testid="tabela-de-auditoria" />,
}));

import HistoryTab from "../HistoryTab";

const props = (overrides = {}) => ({
  processId: "p-1",
  process: { status: "Em Análise" },
  history: [],
  workflowStatuses: [],
  activities: [],
  handleDeleteComment: vi.fn(),
  user: { id: "u-1", name: "Carla", role: "consultor" },
  ...overrides,
});

describe("HistoryTab — só de leitura (Ponto 9)", () => {
  it("não oferece o diálogo de registar atividade", () => {
    render(<HistoryTab {...props()} />);

    expect(screen.queryByTestId("quick-note-open")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Registar Atividade/i }),
    ).not.toBeInTheDocument();
  });

  it("não oferece caixa de texto nenhuma", () => {
    // O diálogo podia ter saído e ficar o `Textarea` solto no cartão.
    render(<HistoryTab {...props()} />);

    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("a nota de voz também não se grava a partir daqui", () => {
    // Mudou-se para o cartão de Observações, no Resumo — uma nota
    // ditada é uma nota. Ver `ProcessObservationsCard.notaDeVoz.test`.
    render(<HistoryTab {...props()} />);

    expect(screen.queryByTestId("voice-note-open")).not.toBeInTheDocument();
  });

  it("não aceita sequer as props com que se escrevia", () => {
    // Contraprova do arranque: se alguém voltar a passar
    // `handleSendComment` na esperança de o separador o usar, nada deve
    // aparecer. A ausência não pode depender de quem chama.
    render(
      <HistoryTab
        {...props({
          handleSendComment: vi.fn(),
          newComment: "texto a caminho",
          setNewComment: vi.fn(),
          isProcessLocked: false,
          onEnviarNotaDeVoz: vi.fn(),
        })}
      />,
    );

    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByTestId("quick-note-open")).not.toBeInTheDocument();
    expect(screen.queryByTestId("voice-note-open")).not.toBeInTheDocument();
    expect(screen.queryByText("texto a caminho")).not.toBeInTheDocument();
  });

  it("diz porque é que não há botão", () => {
    // Sem isto, quem procurar o "Registar Atividade" conclui que a
    // página está partida em vez de perceber que o sítio mudou.
    render(<HistoryTab {...props()} />);

    expect(screen.getByTestId("historico-so-leitura")).toHaveTextContent(
      /Resumo/,
    );
  });

  it("continua a MOSTRAR a timeline e a auditoria", () => {
    // Contraprova: "só de leitura" não pode ter virado "vazio".
    render(<HistoryTab {...props()} />);

    expect(screen.getByTestId("timeline-de-fases")).toBeInTheDocument();
    expect(screen.getByTestId("tabela-de-auditoria")).toBeInTheDocument();
  });
});
