import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import BotaoComPermissao, {
  MODO_OCULTAR,
} from "../BotaoComPermissao";
import { CRIAR_PROCESSO } from "@/utils/capacidades";

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
