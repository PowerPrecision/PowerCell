/**
 * «Dados do cliente» do Parceiro — o 2.º titular liga-se sozinho (QA, Out 2026).
 *
 * O erro «Empréstimo em nome individual ou com outra pessoa?: escolha uma das opções» aparecia a quem já estava a
 * preencher o 2.º titular. A forma do formulário é a que o servidor devolve (`run_get_client_form`); os valores
 * diferem das omissões e o `compra_tipo` pode vir de uma configuração com outras opções.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const obter = vi.fn();
const guardar = vi.fn();
vi.mock("@/services/partnerApi", () => ({
  obterFormularioDoCliente: (...a) => obter(...a),
  guardarFormularioDoCliente: (...a) => guardar(...a),
}));

import ClientDataForm from "../ClientDataForm";

const PASSOS = [
  {
    step: 1,
    label: "Dados do titular",
    fields: [
      { field_key: "name", label: "Nome", field_type: "text", is_required: true, options: [], data_path: "root" },
      {
        field_key: "compra_tipo",
        label: "Empréstimo em nome individual ou com outra pessoa?",
        field_type: "select",
        is_required: false,
        options: [{ value: "sozinho", label: "Sozinho" }],
        data_path: "personal_data",
      },
    ],
  },
  {
    step: 2,
    label: "2.º titular",
    fields: [
      { field_key: "titular2_name", label: "Nome do 2º Titular", field_type: "text", is_required: false, options: [], data_path: "titular2_data" },
    ],
  },
];

const formulario = (values, extra = {}) => ({ editavel: true, passos: PASSOS, values, segundo_titular: false, ...extra });

function montar() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ClientDataForm caseId="caso-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  obter.mockReset();
  guardar.mockReset();
  guardar.mockResolvedValue({ success: true });
});

describe("o 2.º titular liga-se sozinho", () => {
  it("uma ficha com dados do 2.º titular mas compra_tipo diferente abre-os já visíveis, com o interruptor ligado", async () => {
    obter.mockResolvedValue(formulario({ name: "Joana", compra_tipo: "sozinho", titular2_name: "Rui" }));
    montar();
    const interruptor = await screen.findByRole("switch", { name: "Adicionar 2.º titular" });
    expect(interruptor).toBeChecked();
    expect(await screen.findByLabelText(/Nome do 2º Titular/)).toHaveValue("Rui");
  });

  it("ligar o interruptor, preencher e guardar envia outra_pessoa + o nome (e nada mais)", async () => {
    obter.mockResolvedValue(formulario({ name: "Joana", compra_tipo: "sozinho" }));
    montar();
    const utilizador = userEvent.setup();
    await utilizador.click(await screen.findByRole("switch", { name: "Adicionar 2.º titular" }));
    await utilizador.type(await screen.findByLabelText(/Nome do 2º Titular/), "Rui");
    await utilizador.click(screen.getByRole("button", { name: "Guardar dados" }));
    await waitFor(() => expect(guardar).toHaveBeenCalledTimes(1));
    expect(guardar).toHaveBeenCalledWith("caso-1", { compra_tipo: "outra_pessoa", titular2_name: "Rui" });
  });

  it("dados antigos do 2.º titular + qualquer edição: o pedido leva a chave que o liga", async () => {
    obter.mockResolvedValue(formulario({ name: "Joana", compra_tipo: "sozinho", titular2_name: "Rui" }));
    montar();
    const utilizador = userEvent.setup();
    const campo = await screen.findByLabelText(/Nome do 2º Titular/);
    await utilizador.clear(campo);
    await utilizador.type(campo, "Rui Silva");
    await utilizador.click(screen.getByRole("button", { name: "Guardar dados" }));
    await waitFor(() => expect(guardar).toHaveBeenCalledTimes(1));
    expect(guardar.mock.calls[0][1]).toEqual({ compra_tipo: "outra_pessoa", titular2_name: "Rui Silva" });
  });

  it("desligar o interruptor continua a ser uma escolha EXPRESSA e vence os dados: avisa e envia individual", async () => {
    obter.mockResolvedValue(formulario({ name: "Joana", compra_tipo: "outra_pessoa", titular2_name: "Rui" }));
    montar();
    const utilizador = userEvent.setup();
    await utilizador.click(await screen.findByRole("switch", { name: "Adicionar 2.º titular" }));
    expect(await screen.findByText(/os dados do 2.º titular serão apagados/)).toBeInTheDocument();
    await utilizador.click(screen.getByRole("button", { name: "Guardar dados" }));
    await waitFor(() => expect(guardar).toHaveBeenCalledTimes(1));
    expect(guardar.mock.calls[0][1]).toEqual({ compra_tipo: "individual" });
  });

  it("contraprova: sem dados nem interruptor, o 2.º titular fica escondido e nada se envia", async () => {
    obter.mockResolvedValue(formulario({ name: "Joana", compra_tipo: "sozinho" }));
    montar();
    const interruptor = await screen.findByRole("switch", { name: "Adicionar 2.º titular" });
    expect(interruptor).not.toBeChecked();
    expect(screen.queryByTestId("campos-do-segundo-titular")).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Guardar dados" }));
    expect(guardar).not.toHaveBeenCalled();
  });
});
