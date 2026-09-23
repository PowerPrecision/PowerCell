/**
 * Teste da barra de domínios do processo (Épico 8, Eixo 1).
 *
 * Os `TabsTrigger` do Radix falam com o contexto do `<Tabs>`, por isso o
 * componente é montado dentro de um — é assim que é usado a sério.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Tabs } from "../../ui/tabs";
import ProcessDomainTabsList from "../ProcessDomainTabsList";

const montar = (props = {}, { onValueChange = vi.fn(), value = "personal" } = {}) =>
  render(
    <Tabs value={value} onValueChange={onValueChange}>
      <ProcessDomainTabsList {...props} />
    </Tabs>,
  );

describe("ProcessDomainTabsList — os oito domínios", () => {
  it("rende todos os separadores", () => {
    montar();

    for (const nome of [
      "Cliente",
      "Financeiros",
      "Imóvel / CPCV",
      "Crédito",
      "Agenda",
      "Emails",
      "Visitas",
      "Mensagens",
    ]) {
      expect(screen.getByRole("tab", { name: nome })).toBeInTheDocument();
    }
  });

  it("são oito, nem mais nem menos", () => {
    // Uma extracção que perdesse um separador tirava um domínio inteiro de
    // dados do alcance do consultor sem nada rebentar.
    montar();

    expect(screen.getAllByRole("tab")).toHaveLength(8);
  });

  it("escolher um separador avisa o contexto do Tabs", async () => {
    const utilizador = userEvent.setup();
    const onValueChange = vi.fn();
    montar({}, { onValueChange });

    await utilizador.click(screen.getByRole("tab", { name: "Crédito" }));

    expect(onValueChange).toHaveBeenCalledWith("credit");
  });

  it("o separador activo vem do contexto, não de estado próprio", () => {
    montar({}, { value: "emails" });

    expect(screen.getByRole("tab", { name: "Emails" })).toHaveAttribute(
      "data-state",
      "active",
    );
  });
});

describe("ProcessDomainTabsList — sinal de mensagens por ler", () => {
  it("sem mensagens por ler, não há sinal", () => {
    montar({ unreadMessagesCount: 0 });

    expect(screen.queryByLabelText(/mensagens por ler/)).not.toBeInTheDocument();
  });

  it("com mensagens por ler, mostra a contagem", () => {
    montar({ unreadMessagesCount: 3 });

    expect(screen.getByLabelText("3 mensagens por ler")).toHaveTextContent("3");
  });

  it("acima de nove mostra 9+", () => {
    montar({ unreadMessagesCount: 42 });

    expect(screen.getByLabelText("42 mensagens por ler")).toHaveTextContent("9+");
  });

  it("sem a prop não rebenta", () => {
    montar();

    expect(screen.queryByLabelText(/mensagens por ler/)).not.toBeInTheDocument();
  });
});
