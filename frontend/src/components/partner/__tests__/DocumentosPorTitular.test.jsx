/**
 * Portal do Parceiro — documentos do 1.º e do 2.º titular (Out 2026).
 *
 * Os valores são os do servidor (`titulares`, `titular`, `titular_label`) e diferem das omissões. O que se prova:
 * a etiqueta aparece em ficheiros e pedidos só quando há titular; o seletor «De quem é o documento» só existe com
 * dois compradores, é obrigatório (não se adivinha) e o `titular` escolhido chega ao envio.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const enviarFicheiro = vi.fn();
vi.mock("@/services/partnerApi", () => ({
  enviarFicheiro: (...a) => enviarFicheiro(...a),
  obterUrlDeDescarga: vi.fn(),
}));

import FicheiroDoCaso from "../FicheiroDoCaso";
import PartnerUploadBox from "../PartnerUploadBox";
import PedidoDeDocumento from "../PedidoDeDocumento";

const TITULARES = [
  { id: "titular1", label: "1.º titular", nome: "Ana Primeira" },
  { id: "titular2", label: "2.º titular", nome: "Rui Segundo" },
];

const ficheiro = (extra) => ({
  id: "f1", filename: "cc.pdf", category_label: "Identificação", by: "cliente", file_size: 2048,
  uploaded_at: "2026-10-05T10:00:00+00:00", estado: "recebido", titular: null, titular_label: null, ...extra,
});

const pedido = (extra) => ({
  id: "req-1", label: "Cartão de Cidadão", notes: "", estado: "pendente", expected_count: 1, uploaded_count: 0,
  ficheiros: [], titular: null, titular_label: null, ...extra,
});

function com(ui) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const pdf = () => new File(["%PDF-1.4"], "cc.pdf", { type: "application/pdf" });

beforeEach(() => {
  enviarFicheiro.mockReset();
  enviarFicheiro.mockResolvedValue({ success: true, id: "novo", destino: {} });
});

describe("a etiqueta do titular", () => {
  it("um ficheiro do 2.º titular diz de quem é, com o nome", () => {
    com(<ul><FicheiroDoCaso caseId="c1" ficheiro={ficheiro({ titular: "titular2", titular_label: "2.º titular" })} titulares={TITULARES} /></ul>);
    const etiqueta = screen.getByTestId("titular-do-ficheiro");
    expect(etiqueta).toHaveTextContent("2.º titular · Rui Segundo");
    expect(etiqueta).toHaveAttribute("data-titular", "titular2");
  });

  it("os dois ficheiros do mesmo pedido distinguem-se", () => {
    com(
      <PedidoDeDocumento
        caseId="c1"
        titulares={TITULARES}
        pedido={pedido({
          estado: "recebido",
          ficheiros: [
            ficheiro({ id: "a", filename: "t1.pdf", titular: "titular1", titular_label: "1.º titular" }),
            ficheiro({ id: "b", filename: "t2.pdf", titular: "titular2", titular_label: "2.º titular" }),
          ],
        })}
      />,
    );
    const etiquetas = screen.getAllByTestId("titular-do-ficheiro").map((e) => e.textContent);
    expect(etiquetas).toEqual(["1.º titular · Ana Primeira", "2.º titular · Rui Segundo"]);
  });

  it("um pedido sem titular (serve os dois) não leva etiqueta; com titular leva", () => {
    const { unmount } = com(<PedidoDeDocumento caseId="c1" titulares={TITULARES} pedido={pedido()} />);
    expect(screen.queryByTestId("titular-do-pedido-req-1")).not.toBeInTheDocument();
    unmount();
    com(<PedidoDeDocumento caseId="c1" titulares={TITULARES} pedido={pedido({ titular: "titular2", titular_label: "2.º titular" })} />);
    expect(screen.getByTestId("titular-do-pedido-req-1")).toHaveTextContent("2.º titular · Rui Segundo");
  });

  it("com um comprador só nenhum ficheiro leva etiqueta", () => {
    com(<ul><FicheiroDoCaso caseId="c1" ficheiro={ficheiro()} titulares={[]} /></ul>);
    expect(screen.queryByTestId("titular-do-ficheiro")).not.toBeInTheDocument();
  });
});

describe("o pedido propõe o seu titular ao enviar", () => {
  it("um pedido do 2.º titular chega ao seletor já escolhido — pendente e a juntar mais", () => {
    const { unmount } = com(
      <PedidoDeDocumento caseId="c1" titulares={TITULARES} pedido={pedido({ titular: "titular2", titular_label: "2.º titular" })} />,
    );
    expect(screen.getByLabelText("De quem é o documento")).toHaveValue("titular2");
    unmount();
    com(
      <PedidoDeDocumento
        caseId="c1"
        titulares={TITULARES}
        pedido={pedido({ estado: "recebido", expected_count: 3, uploaded_count: 1, titular: "titular1", titular_label: "1.º titular",
          ficheiros: [ficheiro({ titular: "titular1", titular_label: "1.º titular" })] })}
      />,
    );
    expect(screen.getByLabelText("De quem é o documento")).toHaveValue("titular1");
  });

  it("um pedido sem titular obriga a escolher", () => {
    com(<PedidoDeDocumento caseId="c1" titulares={TITULARES} pedido={pedido()} />);
    expect(screen.getByLabelText("De quem é o documento")).toHaveValue("");
  });
});

describe("o seletor «De quem é o documento»", () => {
  it("não existe com um comprador e o envio não leva titular", async () => {
    com(<PartnerUploadBox caseId="c1" requestId="req-1" titulares={[]} />);
    expect(screen.queryByLabelText("De quem é o documento")).not.toBeInTheDocument();
    await userEvent.upload(screen.getByTestId("input-req-1"), pdf());
    expect(enviarFicheiro).toHaveBeenCalledTimes(1);
    expect(enviarFicheiro.mock.calls[0][2]).not.toHaveProperty("titular");
  });

  it("com dois compradores é obrigatório: sem escolha não envia e explica", async () => {
    com(<PartnerUploadBox caseId="c1" requestId="req-1" titulares={TITULARES} />);
    await userEvent.upload(screen.getByTestId("input-req-1"), pdf());
    expect(enviarFicheiro).not.toHaveBeenCalled();
    expect(await screen.findByRole("alert")).toHaveTextContent(/de quem é o documento/i);
  });

  it("o titular escolhido chega ao envio", async () => {
    com(<PartnerUploadBox caseId="c1" requestId="req-1" titulares={TITULARES} />);
    await userEvent.selectOptions(screen.getByLabelText("De quem é o documento"), "titular2");
    await userEvent.upload(screen.getByTestId("input-req-1"), pdf());
    expect(enviarFicheiro).toHaveBeenCalledTimes(1);
    expect(enviarFicheiro.mock.calls[0][2]).toMatchObject({ requestId: "req-1", titular: "titular2" });
  });

  it("as opções dizem o nome de cada titular", () => {
    com(<PartnerUploadBox caseId="c1" requestId="req-1" titulares={TITULARES} />);
    const opcoes = within(screen.getByLabelText("De quem é o documento")).getAllByRole("option").map((o) => o.textContent);
    expect(opcoes).toEqual(["Escolha o titular…", "1.º titular · Ana Primeira", "2.º titular · Rui Segundo"]);
  });

  it("um pedido que já é de um titular propõe-no", async () => {
    com(<PartnerUploadBox caseId="c1" requestId="req-1" titulares={TITULARES} titularPorOmissao="titular2" />);
    expect(screen.getByLabelText("De quem é o documento")).toHaveValue("titular2");
    await userEvent.upload(screen.getByTestId("input-req-1"), pdf());
    expect(enviarFicheiro.mock.calls[0][2]).toMatchObject({ titular: "titular2" });
  });

  it("escolher depois de uma recusa limpa o aviso", async () => {
    com(<PartnerUploadBox caseId="c1" requestId="req-1" titulares={TITULARES} />);
    await userEvent.upload(screen.getByTestId("input-req-1"), pdf());
    await screen.findByRole("alert");
    await userEvent.selectOptions(screen.getByLabelText("De quem é o documento"), "titular1");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
