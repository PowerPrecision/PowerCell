/**
 * AIReviewDialog — revisão da extracção por ficheiro (Épico 9, Eixo 4).
 *
 * A REGRA DE OURO QUE ISTO PROTEGE:
 *   "A IA nunca escreve na base de dados (dados pessoais/financeiros) sem
 *   a confirmação do utilizador."
 *
 * O diálogo é a última coisa entre um modelo de visão e o NIF de um
 * cliente. Duas propriedades têm de valer sempre:
 *   1. o consultor vê TUDO o que vai entrar — não só o que colidiu com um
 *      valor já existente;
 *   2. nada sai daqui sem um clique explícito em "Confirmar Todos", e esse
 *      botão fica travado enquanto houver um conflito por decidir.
 *
 * Os testes do fluxo em lote vivem em `AIReviewDialog.test.jsx`; este
 * ficheiro cobre só o que o Épico 9 acrescentou.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import AIReviewDialog from "../AIReviewDialog";

const CONFLITO = {
  field: "rendimento_anual",
  existing_value: 25000,
  new_value: 28400,
  source: "irs_2025.pdf",
};

function montar(props = {}) {
  const aoResolver = vi.fn();
  const aoConfirmar = vi.fn();
  const aoMudarAbertura = vi.fn();
  render(
    <AIReviewDialog
      open
      conflicts={[]}
      onOpenChange={aoMudarAbertura}
      onResolve={aoResolver}
      onConfirmAll={aoConfirmar}
      {...props}
    />,
  );
  return { aoResolver, aoConfirmar, aoMudarAbertura };
}

describe("AIReviewDialog — documento de origem", () => {
  it("mostra o ficheiro de onde vieram os dados", () => {
    montar({ sourceDocument: "cartao_cidadao.jpg" });
    expect(screen.getByText("cartao_cidadao.jpg")).toBeInTheDocument();
  });

  it("sem ficheiro de origem não inventa cabeçalho", () => {
    // O fluxo em lote não tem um único ficheiro de origem; dizer "Documento:"
    // sem nome seria pior do que não dizer nada.
    montar();
    expect(screen.queryByText("Documento:")).not.toBeInTheDocument();
  });
});

describe("AIReviewDialog — campos a preencher", () => {
  const NOVOS = [
    { field: "nif", value: "123456789" },
    { field: "nome_completo", value: "Maria Silva" },
  ];

  it("lista os valores que a ficha ainda não tem", () => {
    // Estes NÃO são conflitos (a ficha está vazia), mas vão ser gravados.
    // Se não estiverem à vista, o consultor confirma às cegas.
    montar({ newValues: NOVOS });
    expect(screen.getByText("123456789")).toBeInTheDocument();
    expect(screen.getByText("Maria Silva")).toBeInTheDocument();
  });

  it("mostra o rótulo legível do campo, não a chave crua", () => {
    montar({ newValues: NOVOS });
    expect(screen.getByText("Nome Completo")).toBeInTheDocument();
  });

  it("conta quantos campos vão ser preenchidos", () => {
    montar({ newValues: NOVOS });
    expect(screen.getByText("Campos a preencher (2)")).toBeInTheDocument();
  });

  it("avisa que os valores serão gravados ao confirmar", () => {
    montar({ newValues: NOVOS });
    expect(
      screen.getByText(/Serão gravados ao confirmar/i),
    ).toBeInTheDocument();
  });

  it("sem valores novos a secção não aparece", () => {
    montar({ conflicts: [CONFLITO] });
    expect(screen.queryByText(/Campos a preencher/)).not.toBeInTheDocument();
  });

  it("um valor nulo aparece como traço e não como 'null'", () => {
    montar({ newValues: [{ field: "nif", value: null }] });
    const seccao = screen.getByText("Nif").closest("div");
    expect(within(seccao).getByText("-")).toBeInTheDocument();
  });
});

describe("AIReviewDialog — nada é escrito sem confirmação", () => {
  it("o botão de confirmar chama o contentor", async () => {
    const utilizador = userEvent.setup();
    const { aoConfirmar } = montar({
      newValues: [{ field: "nif", value: "123456789" }],
      sourceDocument: "cc.jpg",
    });

    await utilizador.click(screen.getByRole("button", { name: /Confirmar Todos/i }));
    expect(aoConfirmar).toHaveBeenCalledTimes(1);
  });

  it("com um conflito por decidir, confirmar está travado", async () => {
    const { aoConfirmar } = montar({
      conflicts: [CONFLITO],
      newValues: [{ field: "nif", value: "123456789" }],
      sourceDocument: "irs_2025.pdf",
    });

    const botao = screen.getByRole("button", { name: /Confirmar Todos/i });
    expect(botao).toBeDisabled();
    await userEvent.setup().click(botao).catch(() => {});
    expect(aoConfirmar).not.toHaveBeenCalled();
  });

  it("fechar não é confirmar", async () => {
    const utilizador = userEvent.setup();
    const { aoConfirmar, aoMudarAbertura } = montar({
      newValues: [{ field: "nif", value: "123456789" }],
      sourceDocument: "cc.jpg",
    });

    await utilizador.click(screen.getByRole("button", { name: "Fechar" }));
    expect(aoMudarAbertura).toHaveBeenCalledWith(false);
    // O ponto: desistir não pode gravar nada.
    expect(aoConfirmar).not.toHaveBeenCalled();
  });
});
