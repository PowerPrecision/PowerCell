/**
 * O Portal do Parceiro MONTADO — documentos do 1.º e do 2.º titular (Out 2026).
 *
 * A página liga `caso.titulares` a pedidos, ficheiros e zonas de envio: só a página montada prova essa ligação
 * (os componentes sozinhos passam com ela partida). A resposta é a fixture REAL do servidor, com dois titulares.
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/services/partnerApi", () => ({
  entrar: vi.fn(), obterPerfil: vi.fn(), lerConvite: vi.fn(), aceitarConvite: vi.fn(), mudarPalavraPasse: vi.fn(),
  obterPainel: vi.fn(), listarCasos: vi.fn(), obterCaso: vi.fn(), submeterLead: vi.fn(), obterDestinos: vi.fn(),
  obterUrlDeDescarga: vi.fn(), enviarFicheiro: vi.fn(), obterFormularioDoCliente: vi.fn(),
  guardarFormularioDoCliente: vi.fn(), escreverNota: vi.fn(),
}));

import * as api from "@/services/partnerApi";
import { FIXTURES, montar, prepararApi } from "./montagem";

const TITULARES = [
  { id: "titular1", label: "1.º titular", nome: "Ana Primeira" },
  { id: "titular2", label: "2.º titular", nome: "Rui Segundo" },
];

function casoComDoisTitulares() {
  const caso = structuredClone(FIXTURES.casoDeProcesso);
  caso.titulares = TITULARES;
  caso.pedidos = [
    {
      id: "req-1", label: "Cartão de Cidadão", notes: "", estado: "pendente", expected_count: 2, uploaded_count: 0,
      titular: null, titular_label: null, ficheiros: [],
    },
    {
      id: "req-2", label: "Declaração de IRS", notes: "", estado: "recebido", expected_count: 1, uploaded_count: 1,
      titular: null, titular_label: null,
      ficheiros: [{
        id: "f-irs", filename: "irs-rui.pdf", by: "eu", category_label: "IRS", file_size: 1024,
        uploaded_at: "2026-10-05T10:00:00+00:00", estado: "recebido", titular: "titular2", titular_label: "2.º titular",
      }],
    },
  ];
  caso.ficheiros = [{
    id: "f-solto", filename: "cc-ana.pdf", by: "cliente", category_label: "Identificação", file_size: 2048,
    uploaded_at: "2026-10-06T10:00:00+00:00", estado: "recebido", titular: "titular1", titular_label: "1.º titular",
  }];
  return caso;
}

beforeEach(() => prepararApi());
afterEach(() => vi.restoreAllMocks());

describe("caso com dois titulares", () => {
  it("os ficheiros dizem de quem são, nos pedidos e nos soltos", async () => {
    api.obterCaso.mockImplementation(async () => casoComDoisTitulares());
    montar("/parceiro/casos/a-novo");
    const pedido = await screen.findByTestId("pedido-req-2");
    expect(within(pedido).getByTestId("titular-do-ficheiro")).toHaveTextContent("2.º titular · Rui Segundo");
    const soltos = await screen.findAllByTestId("titular-do-ficheiro");
    expect(soltos.map((e) => e.textContent)).toContain("1.º titular · Ana Primeira");
  });

  it("um envio sem dizer de quem é fica por fazer; a escolha chega ao servidor", async () => {
    api.obterCaso.mockImplementation(async () => casoComDoisTitulares());
    api.enviarFicheiro.mockResolvedValue({ success: true, id: "n", destino: {} });
    montar("/parceiro/casos/a-novo");
    const pedido = await screen.findByTestId("pedido-req-1");
    const pdf = new File(["%PDF-1.4"], "cc.pdf", { type: "application/pdf" });

    await userEvent.upload(within(pedido).getByTestId("input-req-1"), pdf);
    expect(api.enviarFicheiro).not.toHaveBeenCalled();
    expect(await within(pedido).findByRole("alert")).toHaveTextContent(/de quem é o documento/i);

    await userEvent.selectOptions(within(pedido).getByLabelText("De quem é o documento"), "titular2");
    await userEvent.upload(within(pedido).getByTestId("input-req-1"), pdf);
    await waitFor(() => expect(api.enviarFicheiro).toHaveBeenCalledTimes(1));
    expect(api.enviarFicheiro.mock.calls[0][2]).toMatchObject({ requestId: "req-1", titular: "titular2" });
  });

  it("o envio solto também pergunta de quem é", async () => {
    api.obterCaso.mockImplementation(async () => casoComDoisTitulares());
    montar("/parceiro/casos/a-novo");
    await screen.findByTestId("pedido-req-1");
    const zona = await screen.findByTestId("dropzone-solto");
    expect(within(zona).getByLabelText("De quem é o documento")).toBeInTheDocument();
  });
});

describe("caso com um comprador", () => {
  it("nenhuma etiqueta e nenhum seletor de titular", async () => {
    montar("/parceiro/casos/a-novo");
    await screen.findByTestId("pedido-req-1");
    expect(screen.queryAllByTestId("titular-do-ficheiro")).toHaveLength(0);
    expect(screen.queryByLabelText("De quem é o documento")).not.toBeInTheDocument();
  });
});
