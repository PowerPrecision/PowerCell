/**
 * A timeline montada a sério — a ligação entre o motor e o ecrã.
 *
 * O módulo puro (`utils/processTimeline.test.js`) prova as regras; este
 * teste prova que o componente as USA. Sem ele, trocar
 * `construirTimeline` por lógica inline outra vez passaria despercebido:
 * um componente extraído só está coberto quando também é montado.
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import ProcessTimeline from "../ProcessTimeline";

const FASES = [
  { name: "clientes_espera", label: "Em Espera", color: "yellow", order: 1 },
  { name: "fase_documental", label: "Documentos", color: "blue", order: 2 },
  { name: "cpcv", label: "CPCV", color: "violet", order: 3 },
  { name: "fase_escritura", label: "Escritura", color: "green", order: 4 },
];

describe("ProcessTimeline", () => {
  it("mostra a fase actual tal como o motor a nomeia", () => {
    // O caso que partia a página: o admin criou mesmo uma fase `cpcv` e o
    // mapa de aliases reescrevia-a para `fase_escritura` — a fase actual
    // desaparecia do cabeçalho e tudo passava a ler-se como pendente.
    render(
      <ProcessTimeline
        currentStatus="cpcv"
        history={[{ new_value: "clientes_espera", timestamp: "2026-03-01T10:00:00Z" }]}
        workflowStatuses={FASES}
      />,
    );
    // Tem de ser o CRACHÁ da fase actual, não o cartão inteiro: "CPCV"
    // também aparece como etiqueta de um nó, por isso uma asserção sobre
    // o cartão passava mesmo com o alias a reescrever a fase — um teste
    // que pode passar sem provar nada é pior do que não existir.
    expect(screen.getByTestId("fase-actual")).toHaveTextContent("CPCV");
  });

  it("renderiza uma etiqueta por fase do motor", () => {
    render(<ProcessTimeline currentStatus="fase_documental" history={[]} workflowStatuses={FASES} />);
    for (const fase of FASES) {
      expect(screen.getAllByText(fase.label).length).toBeGreaterThan(0);
    }
  });

  it("marca como saltada a fase anterior sem registo no histórico", () => {
    render(
      <ProcessTimeline
        currentStatus="fase_escritura"
        history={[{ new_value: "clientes_espera", timestamp: "2026-03-01T10:00:00Z" }]}
        workflowStatuses={FASES}
      />,
    );
    // `fase_documental` e `cpcv` vêm antes da actual e nunca foram
    // registadas: são saltadas, não concluídas. Conta-se pelos marcadores
    // das fases e não pelo texto "Saltada", que a legenda também usa.
    expect(screen.getAllByTestId("fase-saltada")).toHaveLength(2);
  });

  it("sem fases carregadas mostra o estado de espera, não uma linha vazia", () => {
    const { container } = render(
      <ProcessTimeline currentStatus="cpcv" history={[]} workflowStatuses={undefined} />,
    );
    expect(container.querySelector(".animate-spin")).not.toBeNull();
  });
});
