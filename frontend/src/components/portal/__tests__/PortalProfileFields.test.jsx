/**
 * Campos do perfil no Portal — divulgação progressiva (Lote 3, ponto 7).
 *
 * O QUE ESTE FICHEIRO PROTEGE
 *   1. Os campos vêm do ESQUEMA (derivado do `form_config`), não de uma
 *      lista escrita à mão. Um campo novo configurado pelo admin aparece
 *      sem tocar neste componente.
 *   2. Os obrigatórios estão à vista e SINALIZADOS; os restantes vivem
 *      atrás de "Preencher mais detalhes".
 *   3. O NIF não aparece. A regra de negócio é que nunca é editável pelo
 *      cliente — e o componente não a trata como caso especial: o backend
 *      simplesmente não o envia. O teste afirma o resultado.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import PortalProfileFields, {
  normalizarOpcoes,
  separarPorVisibilidade,
} from "../PortalProfileFields";

const ESQUEMA = [
  { field_key: "email", label: "Email", field_type: "email", is_required: true, is_primary: true },
  { field_key: "telefone", label: "Telemóvel", field_type: "tel", is_required: true, is_primary: true },
  {
    field_key: "estado_civil",
    label: "Estado Civil",
    field_type: "select",
    is_required: true,
    is_primary: true,
    options: [{ value: "solteiro", label: "Solteiro(a)" }],
  },
  { field_key: "codigo_postal", label: "Código Postal", field_type: "text", is_required: false, is_primary: false },
  { field_key: "profissao", label: "Profissão", field_type: "text", is_required: false, is_primary: false },
  { field_key: "niss", label: "NISS", field_type: "text", is_required: false, is_primary: false, hint: "11 dígitos" },
];

function montar(props = {}) {
  const onChange = vi.fn();
  render(
    <PortalProfileFields
      schema={ESQUEMA}
      values={{}}
      onChange={onChange}
      {...props}
    />,
  );
  return { onChange };
}

const expansor = () =>
  screen.getByRole("button", { name: /Preencher mais detalhes/ });

describe("Campos obrigatórios", () => {
  it("estão à vista sem abrir nada", () => {
    montar();
    expect(screen.getByLabelText(/^Email/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Telemóvel/)).toBeInTheDocument();
  });

  it("são sinalizados de forma acessível, não só com um asterisco", () => {
    // Um `*` sozinho não diz nada a um leitor de ecrã. O asterisco é
    // `aria-hidden` (fica só para quem vê) e a palavra vai num `sr-only`,
    // pelo que o nome acessível é "Email (obrigatório)" — sem o símbolo.
    montar();
    expect(
      screen.getByLabelText(/Email.*\(obrigatório\)/),
    ).toBeInTheDocument();
    // E o asterisco continua lá para quem vê o ecrã.
    expect(screen.getAllByText("*").length).toBeGreaterThan(0);
  });

  it("levam o atributo required", () => {
    montar();
    expect(screen.getByLabelText(/^Email/)).toBeRequired();
  });

  it("um campo opcional não é marcado como obrigatório", async () => {
    montar();
    await userEvent.click(expansor());
    expect(screen.getByLabelText("Profissão")).not.toBeRequired();
  });
});

describe("Divulgação progressiva", () => {
  it("os campos secundários começam escondidos", () => {
    montar();
    expect(screen.queryByLabelText("Código Postal")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Profissão")).not.toBeInTheDocument();
  });

  it("o expansor diz quantos campos esconde", () => {
    montar();
    expect(expansor()).toHaveTextContent("Preencher mais detalhes (3)");
  });

  it("abrir revela-os", async () => {
    montar();
    await userEvent.click(expansor());
    expect(screen.getByLabelText("Código Postal")).toBeInTheDocument();
    expect(screen.getByLabelText("NISS")).toBeInTheDocument();
  });

  it("volta a fechar", async () => {
    montar();
    await userEvent.click(expansor());
    await userEvent.click(expansor());
    expect(screen.queryByLabelText("Código Postal")).not.toBeInTheDocument();
  });

  it("anuncia o estado a quem usa leitor de ecrã", async () => {
    montar();
    expect(expansor()).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(expansor());
    expect(expansor()).toHaveAttribute("aria-expanded", "true");
  });

  it("sem campos secundários não há expansor", () => {
    montar({ schema: ESQUEMA.filter((c) => c.is_primary) });
    expect(
      screen.queryByRole("button", { name: /Preencher mais detalhes/ }),
    ).not.toBeInTheDocument();
  });
});

describe("O NIF nunca é editável pelo cliente", () => {
  it("não aparece quando o esquema não o inclui", () => {
    // O backend não o envia; o componente não precisa de o saber.
    montar();
    expect(screen.queryByLabelText(/NIF/i)).not.toBeInTheDocument();
  });

  it("continua ausente com a secção adicional aberta", async () => {
    montar();
    await userEvent.click(expansor());
    expect(screen.queryByLabelText(/NIF/i)).not.toBeInTheDocument();
  });
});

describe("Ligação ao contentor", () => {
  it("escrever devolve o campo e o valor", async () => {
    const { onChange } = montar();
    await userEvent.type(screen.getByLabelText(/^Email/), "a");
    expect(onChange).toHaveBeenCalledWith("email", "a");
  });

  it("mostra os valores que recebe", () => {
    montar({ values: { email: "ana@exemplo.pt" } });
    expect(screen.getByLabelText(/^Email/)).toHaveValue("ana@exemplo.pt");
  });

  it("um select mostra as opções do esquema", () => {
    montar();
    const select = screen.getByLabelText(/^Estado Civil/);
    expect(within(select).getByText("Solteiro(a)")).toBeInTheDocument();
  });

  it("uma dica do formulário interno é mostrada", async () => {
    montar();
    await userEvent.click(expansor());
    expect(screen.getByText("11 dígitos")).toBeInTheDocument();
  });

  it("perfil trancado desactiva tudo", () => {
    montar({ disabled: true });
    expect(screen.getByLabelText(/^Email/)).toBeDisabled();
  });

  it("esquema vazio não desenha nada", () => {
    const { container } = render(
      <PortalProfileFields schema={[]} values={{}} onChange={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("esquema em falta não rebenta", () => {
    const { container } = render(
      <PortalProfileFields schema={undefined} values={{}} onChange={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("Helpers", () => {
  it("normaliza opções em string", () => {
    expect(normalizarOpcoes(["individual"])).toEqual([
      { value: "individual", label: "individual" },
    ]);
  });

  it("normaliza opções em objecto", () => {
    expect(normalizarOpcoes([{ value: "m", label: "Masculino" }])).toEqual([
      { value: "m", label: "Masculino" },
    ]);
  });

  it("sem opções devolve lista vazia", () => {
    expect(normalizarOpcoes(undefined)).toEqual([]);
  });

  it("separa por is_primary", () => {
    const { principais, adicionais } = separarPorVisibilidade(ESQUEMA);
    expect(principais).toHaveLength(3);
    expect(adicionais).toHaveLength(3);
  });

  it("aguenta um esquema que não é lista", () => {
    expect(separarPorVisibilidade(null).principais).toEqual([]);
  });
});
