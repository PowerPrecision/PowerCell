/**
 * O Portal do Parceiro MONTADO — o filtro de viabilidade e os dados do cliente.
 *
 * Uma lead só segue para a equipa com o Comprovativo de Pagamento; até lá
 * está RETIDA do lado do parceiro. As respostas são as fixtures geradas pelo
 * servidor (valores diferentes das omissões), e o que se afirma é o que o
 * parceiro VÊ e o que o ecrã ENVIA.
 */
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import casoDevolvida from "@/test/fixtures/parceiro/caso_lead_devolvida.json";
import casoExpirada from "@/test/fixtures/parceiro/caso_lead_expirada.json";
import casoPendente from "@/test/fixtures/parceiro/caso_lead_pendente.json";
import comprovativo from "@/test/fixtures/parceiro/confirmacao_comprovativo.json";
import confirmacao from "@/test/fixtures/parceiro/confirmacao_de_envio.json";
import formulario from "@/test/fixtures/parceiro/formulario_cliente.json";
import formularioComSegundo from "@/test/fixtures/parceiro/formulario_com_segundo_titular.json";

vi.mock("@/services/partnerApi", () => ({
  entrar: vi.fn(),
  obterPerfil: vi.fn(),
  lerConvite: vi.fn(),
  aceitarConvite: vi.fn(),
  mudarPalavraPasse: vi.fn(),
  obterPainel: vi.fn(),
  listarCasos: vi.fn(),
  obterCaso: vi.fn(),
  submeterLead: vi.fn(),
  obterUrlDeDescarga: vi.fn(),
  enviarFicheiro: vi.fn(),
  obterFormularioDoCliente: vi.fn(),
  guardarFormularioDoCliente: vi.fn(),
}));

import * as api from "@/services/partnerApi";
import { FIXTURES, montar, prepararApi } from "./montagem";

const pdf = (nome = "pagamento.pdf") => new File(["%PDF-1.4"], nome, { type: "application/pdf" });

function caso(fixture) {
  api.obterCaso.mockImplementation(async (id) => {
    if (id === fixture.id) return structuredClone(fixture);
    throw { response: { status: 404, data: { detail: "Caso não encontrado." } } };
  });
}

beforeEach(() => {
  prepararApi();
  api.obterFormularioDoCliente.mockResolvedValue(structuredClone(formulario));
});
afterEach(() => vi.restoreAllMocks());

// ════════════════════════════════════════════════════════════════════
//  A lead retida
// ════════════════════════════════════════════════════════════════════
describe("uma lead pendente (sem comprovativo)", () => {
  it("diz que está retida e que só segue com o Comprovativo de Pagamento", async () => {
    caso(casoPendente);
    montar(`/parceiro/casos/${casoPendente.id}`);
    const aviso = await screen.findByTestId("aviso-pendente");
    expect(aviso).toHaveTextContent("retida do seu lado");
    expect(aviso).toHaveTextContent("Comprovativo de Pagamento");
    expect(screen.getByText("Pendentes", { selector: "span, div" })).toBeInTheDocument();
  });

  it("mostra o comprovativo como pendente OBRIGATÓRIO, nos Pendentes", async () => {
    caso(casoPendente);
    montar(`/parceiro/casos/${casoPendente.id}`);
    const pendentes = await screen.findByRole("region", { name: "Documentos pendentes" });
    const slot = within(pendentes).getByTestId("comprovativo-obrigatorio");
    expect(slot).toHaveTextContent("Obrigatório");
  });

  it("enviar o comprovativo envia a categoria «Comprovativo_Pagamento» e diz que a lead seguiu", async () => {
    caso(casoPendente);
    api.enviarFicheiro.mockResolvedValue(structuredClone(comprovativo));
    montar(`/parceiro/casos/${casoPendente.id}`);
    await userEvent.upload(await screen.findByTestId("input-comprovativo"), pdf());
    await waitFor(() => expect(api.enviarFicheiro).toHaveBeenCalled());
    expect(api.enviarFicheiro.mock.calls[0][0]).toBe(casoPendente.id);
    expect(api.enviarFicheiro.mock.calls[0][2].category).toBe("Comprovativo_Pagamento");
    expect(await screen.findByText(/seguiu para a nossa equipa/)).toBeInTheDocument();
  });

  it("o arrasto sobre o comprovativo envia a mesma categoria", async () => {
    caso(casoPendente);
    api.enviarFicheiro.mockResolvedValue(structuredClone(comprovativo));
    montar(`/parceiro/casos/${casoPendente.id}`);
    fireEvent.drop(await screen.findByTestId("comprovativo"), { dataTransfer: { types: ["Files"], files: [pdf()] } });
    await waitFor(() => expect(api.enviarFicheiro).toHaveBeenCalled());
    expect(api.enviarFicheiro.mock.calls[0][2].category).toBe("Comprovativo_Pagamento");
  });

  it("um envio SEM comprovativo não diz que a lead seguiu", async () => {
    caso(casoPendente);
    api.enviarFicheiro.mockResolvedValue({ ...structuredClone(confirmacao), lead_submetida: false });
    montar(`/parceiro/casos/${casoPendente.id}`);
    await userEvent.upload(await screen.findByTestId("input-solto"), pdf("cc.pdf"));
    await waitFor(() => expect(api.enviarFicheiro).toHaveBeenCalled());
    await screen.findByText("Enviado");
    expect(screen.queryByText(/seguiu para a nossa equipa/)).not.toBeInTheDocument();
  });

  it("o envio solto oferece as categorias do Portal do Cliente e envia a escolhida", async () => {
    caso(casoPendente);
    api.enviarFicheiro.mockResolvedValue(structuredClone(confirmacao));
    montar(`/parceiro/casos/${casoPendente.id}`);
    const seletor = await screen.findByLabelText("Tipo de documento");
    const rotulos = Array.from(seletor.querySelectorAll("option")).map((o) => o.textContent);
    expect(rotulos).toEqual(expect.arrayContaining(["Recibo de Vencimento", "Comprovativo de Pagamento", "Cartão de Cidadão"]));
    await userEvent.selectOptions(seletor, "Recibo_Vencimento");
    await userEvent.upload(screen.getByTestId("input-solto"), pdf("recibo.pdf"));
    await waitFor(() => expect(api.enviarFicheiro).toHaveBeenCalled());
    expect(api.enviarFicheiro.mock.calls[0][2].category).toBe("Recibo_Vencimento");
  });

  it("sem escolher categoria não envia nenhuma (a equipa classifica)", async () => {
    caso(casoPendente);
    api.enviarFicheiro.mockResolvedValue(structuredClone(confirmacao));
    montar(`/parceiro/casos/${casoPendente.id}`);
    await userEvent.upload(await screen.findByTestId("input-solto"), pdf("x.pdf"));
    await waitFor(() => expect(api.enviarFicheiro).toHaveBeenCalled());
    expect(api.enviarFicheiro.mock.calls[0][2].category).toBeUndefined();
  });
});

describe("uma lead devolvida pela equipa", () => {
  it("mostra o motivo e pede um novo comprovativo", async () => {
    caso(casoDevolvida);
    montar(`/parceiro/casos/${casoDevolvida.id}`);
    const aviso = await screen.findByTestId("aviso-devolvida");
    expect(aviso).toHaveTextContent("devolveu esta lead");
    expect(aviso).toHaveTextContent("Motivo: Comprovativo ilegível");
    expect(aviso).toHaveTextContent("novo Comprovativo de Pagamento");
    expect(screen.getByTestId("comprovativo-obrigatorio")).toBeInTheDocument();
  });
});

describe("uma lead expirada", () => {
  it("diz que expirou e já não oferece envios nem comprovativo", async () => {
    caso(casoExpirada);
    montar(`/parceiro/casos/${casoExpirada.id}`);
    expect(await screen.findByTestId("aviso-expirada")).toHaveTextContent("expirou por inactividade (60 dias");
    expect(screen.queryByTestId("comprovativo-obrigatorio")).not.toBeInTheDocument();
    expect(screen.queryByTestId("input-solto")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Enviar outro documento" })).not.toBeInTheDocument();
  });

  it("os dados do cliente ficam só de leitura", async () => {
    caso(casoExpirada);
    api.obterFormularioDoCliente.mockResolvedValue({ ...structuredClone(formulario), editavel: false });
    montar(`/parceiro/casos/${casoExpirada.id}`);
    await userEvent.click(await screen.findByRole("tab", { name: /Dados do cliente/ }));
    expect(await screen.findByText(/já não podem ser editados/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Guardar dados" })).not.toBeInTheDocument();
  });
});

describe("uma lead normal (já na equipa) e um processo", () => {
  it("uma lead libertada não mostra o comprovativo obrigatório", async () => {
    montar("/parceiro/casos/lead-1");
    await screen.findByText(/está a ser analisada/);
    expect(screen.queryByTestId("comprovativo-obrigatorio")).not.toBeInTheDocument();
    expect(screen.queryByTestId("aviso-pendente")).not.toBeInTheDocument();
  });

  it("um processo não tem o separador «Dados do cliente»", async () => {
    montar("/parceiro/casos/a-novo");
    await screen.findByRole("region", { name: "Documentos pendentes" });
    expect(screen.queryByRole("tab", { name: /Dados do cliente/ })).not.toBeInTheDocument();
  });
});

// ════════════════════════════════════════════════════════════════════
//  Dados do cliente: a estrutura do registo público + 2.º titular
// ════════════════════════════════════════════════════════════════════
describe("o separador «Dados do cliente»", () => {
  const abrir = async (fixture = casoPendente) => {
    caso(fixture);
    montar(`/parceiro/casos/${fixture.id}`);
    await userEvent.click(await screen.findByRole("tab", { name: /Dados do cliente/ }));
    return screen.findByRole("form", { name: "Dados do cliente" });
  };

  it("desenha os campos do formulário público, com os valores da ficha", async () => {
    const form = await abrir();
    expect(within(form).getByTestId("dynamic-name")).toHaveValue("Joana Cliente");
    expect(within(form).getByTestId("dynamic-email")).toHaveValue("joana@cliente.pt");
    expect(within(form).getByTestId("dynamic-nif")).toHaveValue("");
    // o campo que liga o 2.º titular é o interruptor, não um selector cru
    expect(within(form).queryByTestId("dynamic-compra_tipo")).not.toBeInTheDocument();
  });

  it("o 2.º titular começa desligado e os seus campos não aparecem", async () => {
    const form = await abrir();
    expect(within(form).getByRole("switch", { name: "Adicionar 2.º titular" })).not.toBeChecked();
    expect(within(form).queryByTestId("campos-do-segundo-titular")).not.toBeInTheDocument();
  });

  it("ligar o interruptor mostra os campos do 2.º titular", async () => {
    const form = await abrir();
    await userEvent.click(within(form).getByRole("switch", { name: "Adicionar 2.º titular" }));
    const campos = await within(form).findByTestId("campos-do-segundo-titular");
    expect(within(campos).getByTestId("dynamic-titular2_name")).toBeInTheDocument();
    expect(within(campos).getByTestId("dynamic-titular2_nif")).toBeInTheDocument();
  });

  it("guardar envia SÓ o que mudou, com as chaves do formulário público", async () => {
    api.guardarFormularioDoCliente.mockResolvedValue({ success: true, campos_guardados: [], segundo_titular: true });
    const form = await abrir();
    await userEvent.click(within(form).getByRole("switch", { name: "Adicionar 2.º titular" }));
    const campos = await within(form).findByTestId("campos-do-segundo-titular");
    await userEvent.type(within(campos).getByTestId("dynamic-titular2_name"), "Rui Silva");
    await userEvent.clear(within(form).getByTestId("dynamic-profissao"));
    await userEvent.type(within(form).getByTestId("dynamic-profissao"), "Médica");
    await userEvent.click(within(form).getByRole("button", { name: "Guardar dados" }));

    await waitFor(() => expect(api.guardarFormularioDoCliente).toHaveBeenCalled());
    const [id, enviado] = api.guardarFormularioDoCliente.mock.calls[0];
    expect(id).toBe(casoPendente.id);
    expect(enviado).toEqual({ compra_tipo: "outra_pessoa", titular2_name: "Rui Silva", profissao: "Médica" });
    expect(await screen.findByText("Dados guardados.")).toBeInTheDocument();
  });

  it("o que se escreveu no 2.º titular e depois se desligou NÃO vai no pedido", async () => {
    api.guardarFormularioDoCliente.mockResolvedValue({ success: true, campos_guardados: [], segundo_titular: false });
    const form = await abrir();
    const interruptor = within(form).getByRole("switch", { name: "Adicionar 2.º titular" });
    await userEvent.click(interruptor);
    await userEvent.type(await within(form).findByTestId("dynamic-titular2_name"), "Rui Silva");
    await userEvent.click(interruptor);
    await userEvent.type(within(form).getByTestId("dynamic-profissao"), "Médica");
    await userEvent.click(within(form).getByRole("button", { name: "Guardar dados" }));
    await waitFor(() => expect(api.guardarFormularioDoCliente).toHaveBeenCalled());
    expect(api.guardarFormularioDoCliente.mock.calls[0][1]).toEqual({ profissao: "Médica" });
  });

  it("sem alterações não faz pedido nenhum", async () => {
    const form = await abrir();
    await userEvent.click(within(form).getByRole("button", { name: "Guardar dados" }));
    expect(api.guardarFormularioDoCliente).not.toHaveBeenCalled();
    expect(await screen.findByText("Dados guardados.")).toBeInTheDocument();
  });

  it("um erro do servidor aparece junto ao formulário", async () => {
    api.guardarFormularioDoCliente.mockRejectedValue({ response: { status: 400, data: { detail: "«NIF»: NIF inválido." } } });
    const form = await abrir();
    await userEvent.type(within(form).getByTestId("dynamic-profissao"), "x");
    await userEvent.click(within(form).getByRole("button", { name: "Guardar dados" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("NIF inválido.");
    expect(screen.queryByText("Dados guardados.")).not.toBeInTheDocument();
  });

  it("com o 2.º titular já ligado mostra os campos preenchidos", async () => {
    api.obterFormularioDoCliente.mockResolvedValue(structuredClone(formularioComSegundo));
    const form = await abrir();
    expect(within(form).getByRole("switch", { name: "Adicionar 2.º titular" })).toBeChecked();
    expect(within(await within(form).findByTestId("campos-do-segundo-titular")).getByTestId("dynamic-titular2_name")).toHaveValue("Rui Cliente");
  });

  it("desligar o 2.º titular avisa que os dados serão apagados e envia só o interruptor", async () => {
    api.obterFormularioDoCliente.mockResolvedValue(structuredClone(formularioComSegundo));
    api.guardarFormularioDoCliente.mockResolvedValue({ success: true, campos_guardados: ["compra_tipo"], segundo_titular: false });
    const form = await abrir();
    await userEvent.click(within(form).getByRole("switch", { name: "Adicionar 2.º titular" }));
    expect(within(form).getByText(/os dados do 2\.º titular serão apagados/)).toBeInTheDocument();
    await userEvent.click(within(form).getByRole("button", { name: "Guardar dados" }));
    await waitFor(() => expect(api.guardarFormularioDoCliente).toHaveBeenCalled());
    expect(api.guardarFormularioDoCliente.mock.calls[0][1]).toEqual({ compra_tipo: "individual" });
  });

  it("o servidor decide o que é editável: sem edição não há botão de guardar", async () => {
    api.obterFormularioDoCliente.mockResolvedValue({ ...structuredClone(formulario), editavel: false });
    const form = await abrir();
    expect(within(form).queryByRole("button", { name: "Guardar dados" })).not.toBeInTheDocument();
    expect(within(form).getByTestId("dynamic-name")).toBeDisabled();
  });
});

// Contraprova de que as fixtures usadas acima são as do servidor.
describe("as fixtures", () => {
  it("a lead pendente pede comprovativo e as categorias trazem o Comprovativo como obrigatório", () => {
    expect(casoPendente.requer_comprovativo).toBe(true);
    expect(casoPendente.categorias.find((c) => c.value === "Comprovativo_Pagamento").obrigatorio).toBe(true);
    expect(FIXTURES.casoDeProcesso.categorias.find((c) => c.value === "Comprovativo_Pagamento").obrigatorio).toBe(false);
  });
});
