/**
 * «Rever Sugestões IA» (Lote 4, ponto 4).
 *
 * O Drawer é apresentação: o harness abaixo faz o papel do contentor com a
 * MÁQUINA DE ESTADOS REAL (`utils/sugestoesEmLinha`), não com um duplo — um
 * duplo que reimplementasse "aprovar todas" validaria o duplo. O que se afirma
 * é a regra de ouro: aceitar mostra-se, mas só o aprovado chega ao que se grava.
 */
import { useState } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import SugestoesIADrawer from "../SugestoesIADrawer";
import {
  aprovar,
  aprovarTodas,
  criarSugestoes,
  rejeitar,
  valoresAprovados,
} from "../../../utils/sugestoesEmLinha";

const REVISAO = {
  conflicts: [{ field: "nif", existing_value: "111111111", new_value: "123456789" }],
  newValues: [
    { field: "naturalidade", value: "Lisboa" },
    { field: "valor_imovel", value: 250000 },
  ],
  sourceDocument: "cartao-cidadao.pdf",
  targetTitular: "titular1",
};

function Harness({ aoGravar = () => {}, inicial = criarSugestoes(REVISAO) }) {
  const [sugestoes, setSugestoes] = useState(inicial);
  const [aberto, setAberto] = useState(true);
  return (
    <>
      <span data-testid="aprovados">{JSON.stringify(valoresAprovados(sugestoes))}</span>
      <SugestoesIADrawer
        aberto={aberto}
        onAbertoChange={setAberto}
        sugestoes={sugestoes}
        onAprovar={(c) => setSugestoes((s) => aprovar(s, c))}
        onRejeitar={(c) => setSugestoes((s) => rejeitar(s, c))}
        onAprovarTodas={() => {
          setSugestoes((s) => aprovarTodas(s));
          aoGravar();
        }}
      />
    </>
  );
}

describe("SugestoesIADrawer", () => {
  it("mostra Campo | Valor Atual | Sugestão IA | Ação, com rótulos legíveis", () => {
    render(<Harness />);
    const cabecalhos = screen.getAllByRole("columnheader").map((c) => c.textContent);
    expect(cabecalhos).toEqual(["Campo", "Valor Atual", "Sugestão IA", "Ação"]);

    const linhaNif = screen.getByTestId("sugestao-linha-nif");
    expect(within(linhaNif).getByRole("rowheader")).toHaveTextContent("NIF");
    expect(screen.getByTestId("sugestao-atual-nif")).toHaveTextContent("111111111");
    expect(screen.getByTestId("sugestao-nova-nif")).toHaveTextContent("123456789");
    expect(linhaNif).toHaveTextContent(/substitui um valor existente/i);
  });

  it("um campo vazio mostra «—» no valor atual (nunca uma célula em branco)", () => {
    render(<Harness />);
    expect(screen.getByTestId("sugestao-atual-naturalidade")).toHaveTextContent("—");
    expect(screen.getByTestId("sugestao-linha-naturalidade")).not.toHaveTextContent(/substitui/i);
  });

  it("um campo sem rótulo conhecido cai num recurso legível, não na chave crua", () => {
    const sugestoes = criarSugestoes({ newValues: [{ field: "campo_novo_da_ia", value: "x" }] });
    render(<Harness inicial={sugestoes} />);
    expect(screen.getByRole("rowheader")).toHaveTextContent("Campo novo da ia");
  });

  it("aceitar UM campo não aprova os outros — só o aceite entra no que se grava", async () => {
    const u = userEvent.setup();
    render(<Harness />);

    await u.click(screen.getByRole("button", { name: "Aceitar sugestão para NIF" }));

    expect(JSON.parse(screen.getByTestId("aprovados").textContent)).toEqual({ nif: "123456789" });
    // A linha decidida troca os botões pelo estado e os outros continuam pendentes.
    expect(within(screen.getByTestId("sugestao-linha-nif")).getByText("Aceite")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Aceitar sugestão para Naturalidade" })).toBeInTheDocument();
    expect(screen.getByTestId("sugestoes-ia-contagem")).toHaveTextContent("2 por decidir de 3");
  });

  it("rejeitar um campo não o grava e não reabre a pergunta", async () => {
    const u = userEvent.setup();
    render(<Harness />);

    await u.click(screen.getByRole("button", { name: "Rejeitar sugestão para NIF" }));

    expect(JSON.parse(screen.getByTestId("aprovados").textContent)).toEqual({});
    expect(within(screen.getByTestId("sugestao-linha-nif")).getByText("Rejeitada")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Aceitar sugestão para NIF" })).not.toBeInTheDocument();
  });

  it("«Aceitar Todas» aprova o que está pendente e NÃO reabre o que foi rejeitado", async () => {
    const aoGravar = vi.fn();
    const u = userEvent.setup();
    render(<Harness aoGravar={aoGravar} />);

    await u.click(screen.getByRole("button", { name: "Rejeitar sugestão para NIF" }));
    await u.click(screen.getByRole("button", { name: "Aceitar Todas" }));

    expect(JSON.parse(screen.getByTestId("aprovados").textContent)).toEqual({
      naturalidade: "Lisboa",
      valor_imovel: 250000,
    });
    expect(aoGravar).toHaveBeenCalledTimes(1);
    // Sem pendentes, o botão em bloco desaparece.
    expect(screen.queryByRole("button", { name: "Aceitar Todas" })).not.toBeInTheDocument();
    expect(screen.getByTestId("sugestoes-ia-contagem")).toHaveTextContent("Todas decididas (3)");
  });

  it("sem sugestões diz-se, em vez de mostrar uma tabela vazia", () => {
    render(<Harness inicial={null} />);
    expect(screen.getByTestId("sugestoes-ia-vazio")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("fechado não desenha nada", () => {
    render(
      <SugestoesIADrawer
        aberto={false}
        onAbertoChange={() => {}}
        sugestoes={criarSugestoes(REVISAO)}
      />,
    );
    expect(screen.queryByTestId("sugestoes-ia-drawer")).not.toBeInTheDocument();
  });
});
