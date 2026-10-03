import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import BotaoComPermissao, {
  MODO_OCULTAR,
  textoDosFilhos,
} from "../BotaoComPermissao";
import { CRIAR_PROCESSO, EXPORTAR_PROCESSO } from "@/utils/capacidades";

const INDEXADOR = {
  id: "u",
  role: "indexacao",
  capabilities_por_papel: { indexacao: { PROCESS_CREATE: false } },
};
const CONSULTOR = {
  id: "c",
  role: "consultor",
  capabilities_por_papel: { consultor: { PROCESS_CREATE: true } },
};

describe("BotaoComPermissao", () => {
  it("quem pode vê um botão normal e clicável", async () => {
    const onClick = vi.fn();
    render(
      <BotaoComPermissao
        user={CONSULTOR}
        capacidade={CRIAR_PROCESSO}
        papel="consultor"
        onClick={onClick}
      >
        Novo Processo
      </BotaoComPermissao>
    );
    const botao = screen.getByRole("button", { name: "Novo Processo" });
    expect(botao).not.toBeDisabled();
    await userEvent.click(botao);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("quem não pode vê o botão DESACTIVADO, não ausente", () => {
    render(
      <BotaoComPermissao
        user={INDEXADOR}
        capacidade={CRIAR_PROCESSO}
        papel="indexacao"
      >
        Novo Processo
      </BotaoComPermissao>
    );
    const botao = screen.getByRole("button", { name: /sem permissão/i });
    expect(botao).toBeDisabled();
  });

  it("o botão bloqueado não dispara a acção", async () => {
    const onClick = vi.fn();
    render(
      <BotaoComPermissao
        user={INDEXADOR}
        capacidade={CRIAR_PROCESSO}
        papel="indexacao"
        onClick={onClick}
      >
        Novo Processo
      </BotaoComPermissao>
    );
    await userEvent.click(screen.getByRole("button", { name: /sem permissão/i }));
    expect(onClick).not.toHaveBeenCalled();
  });

  it("o modo ocultar não renderiza nada", () => {
    render(
      <BotaoComPermissao
        user={INDEXADOR}
        capacidade={CRIAR_PROCESSO}
        papel="indexacao"
        modo={MODO_OCULTAR}
      >
        Novo Processo
      </BotaoComPermissao>
    );
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("o cadeado é anunciado a quem usa leitor de ecrã", () => {
    render(
      <BotaoComPermissao
        user={INDEXADOR}
        capacidade={CRIAR_PROCESSO}
        papel="indexacao"
      >
        Novo Processo
      </BotaoComPermissao>
    );
    // `aria-disabled` além do `disabled`: alguns leitores ignoram o atributo
    // nativo em elementos compostos.
    expect(
      screen.getByRole("button", { name: /sem permissão/i }
    )).toHaveAttribute("aria-disabled", "true");
  });

  it("o papel ACTIVO decide, não o cargo base", () => {
    const consultorQueEIndexador = {
      id: "x",
      role: "consultor",
      capabilities_por_papel: {
        consultor: { PROCESS_CREATE: true },
        indexacao: { PROCESS_CREATE: false },
      },
    };
    const { unmount } = render(
      <BotaoComPermissao
        user={consultorQueEIndexador}
        capacidade={CRIAR_PROCESSO}
        papel="indexacao"
      >
        Novo Processo
      </BotaoComPermissao>
    );
    expect(screen.getByRole("button")).toBeDisabled();
    unmount();

    render(
      <BotaoComPermissao
        user={consultorQueEIndexador}
        capacidade={CRIAR_PROCESSO}
        papel="consultor"
      >
        Novo Processo
      </BotaoComPermissao>
    );
    expect(screen.getByRole("button")).not.toBeDisabled();
  });
});

describe("BotaoComPermissao — o nome acessível do botão bloqueado (Lote 7)", () => {
  /**
   * A primeira versão fazia `typeof children === "string" ? children : "Acção"`
   * e `children` quase nunca é uma string: o padrão da casa é ícone + rótulo,
   * logo um array. Resultado: TODOS os botões bloqueados do sistema se
   * anunciavam como «Acção — sem permissão» — um leitor de ecrã não distinguia
   * «Novo Processo» de «Exportar Excel», e o botão desaparecia de qualquer
   * `getByRole("button", {name: ...})`. Um botão sem nome acessível é um bug de
   * acessibilidade E um teste impossível; foi o teste de página do Kanban que
   * deu com ele.
   */
  const SEM_NADA = { id: "u1", capabilities_por_papel: { indexacao: {} } };

  it("mantém o rótulo quando os filhos são ícone + texto", () => {
    render(
      <BotaoComPermissao
        user={SEM_NADA}
        capacidade={EXPORTAR_PROCESSO}
        papel="indexacao"
      >
        <span aria-hidden="true">icone</span>
        Exportar Excel
      </BotaoComPermissao>,
    );
    const botao = screen.getByRole("button", { name: /exportar excel/i });
    expect(botao).toBeDisabled();
    expect(botao).toHaveAttribute("aria-label", expect.stringContaining("sem permissão"));
  });

  it("encontra o texto dentro de elementos aninhados", () => {
    render(
      <BotaoComPermissao
        user={SEM_NADA}
        capacidade={EXPORTAR_PROCESSO}
        papel="indexacao"
      >
        <span><strong>Exportar</strong> Excel</span>
      </BotaoComPermissao>,
    );
    expect(
      screen.getByRole("button", { name: /exportar excel/i }),
    ).toBeDisabled();
  });

  it("cai em «Acção» só quando não há texto nenhum", () => {
    // Contraprova do recuo: um botão só de ícone não tem rótulo a usar, e
    // «Acção — sem permissão» é melhor do que « — sem permissão».
    render(
      <BotaoComPermissao
        user={SEM_NADA}
        capacidade={EXPORTAR_PROCESSO}
        papel="indexacao"
      >
        <span aria-hidden="true" />
      </BotaoComPermissao>,
    );
    expect(
      screen.getByRole("button", { name: /acção — sem permissão/i }),
    ).toBeInTheDocument();
  });
});

describe("textoDosFilhos", () => {
  it("ignora o que não tem texto e junta o resto", () => {
    expect(textoDosFilhos(["Novo", null, false, undefined, "Processo"])).toBe(
      "Novo Processo",
    );
  });

  it("aceita números e devolve vazio para o vazio", () => {
    expect(textoDosFilhos(7)).toBe("7");
    expect(textoDosFilhos(null)).toBe("");
    expect(textoDosFilhos([])).toBe("");
  });
});
