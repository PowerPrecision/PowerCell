import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CamposDoPasso from "../CamposDoPasso";

const renderCampo = (campo) => (
  <label key={campo.field_key} htmlFor={campo.field_key}>
    {campo.field_key}
    <input id={campo.field_key} />
  </label>
);

function montar(props = {}) {
  return render(
    <CamposDoPasso
      primarios={[{ field_key: "name" }, { field_key: "email" }]}
      secundarios={[{ field_key: "sexo" }, { field_key: "altura" }]}
      renderCampo={renderCampo}
      {...props}
    />,
  );
}

describe("CamposDoPasso", () => {
  it("mostra os campos que bloqueiam sem nada a escondê-los", () => {
    montar();
    expect(screen.getByLabelText(/name/)).toBeVisible();
    expect(screen.getByLabelText(/email/)).toBeVisible();
  });

  it("começa com os campos adicionais fechados", () => {
    montar();
    expect(screen.queryByLabelText(/sexo/)).toBeNull();
  });

  it("abre o painel ao clicar e revela os campos", async () => {
    const user = userEvent.setup();
    montar();
    await user.click(screen.getByTestId("abrir-campos-adicionais"));
    expect(await screen.findByLabelText(/sexo/)).toBeVisible();
    expect(screen.getByLabelText(/altura/)).toBeVisible();
  });

  it("diz, dentro do painel, que se pode continuar sem preencher", async () => {
    // O ponto inteiro do Ponto 9: quem abre e vê campos precisa de saber
    // no mesmo sítio que pode fechar e seguir.
    const user = userEvent.setup();
    montar();
    await user.click(screen.getByTestId("abrir-campos-adicionais"));
    expect(await screen.findByTestId("ajuda-campos-adicionais"))
      .toHaveTextContent(/impede.*continuar/i);
  });

  it("nunca escreve 'obrigatório' no convite", () => {
    montar();
    expect(screen.getByTestId("abrir-campos-adicionais").textContent.toLowerCase())
      .not.toContain("obrigat");
  });

  it("não desenha painel nenhum quando não há campos secundários", () => {
    montar({ secundarios: [] });
    expect(screen.queryByTestId("abrir-campos-adicionais")).toBeNull();
    expect(screen.getByLabelText(/name/)).toBeVisible();
  });

  it("abre já aberto quando o cliente retomou dados lá dentro", async () => {
    // Formulário guardado no localStorage: esconder o que ele já
    // escreveu dava a sensação de ter perdido o trabalho.
    montar({ abertoPorOmissao: true });
    expect(await screen.findByLabelText(/sexo/)).toBeVisible();
  });
});
