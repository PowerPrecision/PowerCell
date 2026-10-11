/**
 * O Portal do Parceiro MONTADO — entrada: login, convite, conta e a moldura.
 *
 * Como a `ProcessesPage`, o `WebmailPage` e o `SystemConfigPage`: nem o
 * eslint, nem o build, nem os testes de componente avaliam o render, e foi
 * por aí que se esconderam defeitos de forma. Daí o primeiro teste ser o mais
 * estúpido possível: montar e sobreviver.
 */
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import convite from "@/test/fixtures/parceiro/convite.json";
import sessao from "@/test/fixtures/parceiro/sessao.json";

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
import { anunciarSessaoExpirada, lerToken } from "@/utils/partnerSession";
import { FIXTURES, erroHttp, montar, prepararApi } from "./montagem";

beforeEach(() => prepararApi());

describe("montar e sobreviver", () => {
  it("a raiz sem sessão mostra o login — e não pede dados nenhuns", async () => {
    montar("/parceiro", { autenticado: false });
    expect(await screen.findByRole("button", { name: "Entrar" })).toBeInTheDocument();
    expect(api.obterPainel).not.toHaveBeenCalled();
    expect(api.listarCasos).not.toHaveBeenCalled();
  });

  it("com sessão, o painel monta", async () => {
    montar("/parceiro");
    expect(await screen.findByRole("region", { name: "Resumo" })).toBeInTheDocument();
  });

  it("uma rota desconhecida cai no painel", async () => {
    montar("/parceiro/nao-existe/nada");
    expect(await screen.findByRole("region", { name: "Resumo" })).toBeInTheDocument();
  });
});

describe("login", () => {
  it("credenciais erradas: a mensagem do servidor, a palavra-passe limpa e fica no login", async () => {
    api.entrar.mockRejectedValue(erroHttp(401, "Email ou palavra-passe incorrectos."));
    montar("/parceiro/entrar", { autenticado: false });
    await userEvent.type(await screen.findByLabelText("Email"), "rui@parceiros.pt");
    await userEvent.type(screen.getByLabelText("Palavra-passe"), "errada");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Email ou palavra-passe incorrectos.");
    expect(screen.getByLabelText("Palavra-passe")).toHaveValue("");
    expect(screen.queryByRole("region", { name: "Resumo" })).not.toBeInTheDocument();
    expect(lerToken()).toBeNull();
  });

  it("o bloqueio por tentativas mostra a mensagem do travão", async () => {
    api.entrar.mockRejectedValue(erroHttp(429, { message: "Muitas tentativas falhadas. Tente novamente em 10 minutos." }));
    montar("/parceiro/entrar", { autenticado: false });
    await userEvent.type(await screen.findByLabelText("Email"), "rui@parceiros.pt");
    await userEvent.type(screen.getByLabelText("Palavra-passe"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Tente novamente em 10 minutos");
  });

  it("o botão só activa com email e palavra-passe", async () => {
    montar("/parceiro/entrar", { autenticado: false });
    const botao = await screen.findByRole("button", { name: "Entrar" });
    expect(botao).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Email"), "a@b.pt");
    expect(botao).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Palavra-passe"), "x");
    expect(botao).toBeEnabled();
  });

  it("entrar guarda o token e leva ao painel com os números do servidor", async () => {
    api.entrar.mockResolvedValue(sessao);
    montar("/parceiro/entrar", { autenticado: false });
    await userEvent.type(await screen.findByLabelText("Email"), "rui@parceiros.pt");
    await userEvent.type(screen.getByLabelText("Palavra-passe"), "Parceiro#2026x");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));

    // Espera-se pelo ELEMENTO que se afirma (a moldura «Resumo» existe desde o
    // primeiro render, ainda com esqueletos): a presença dele é a afirmação.
    const resumo = await screen.findByRole("region", { name: "Resumo" });
    expect((await within(resumo).findByText("Escriturados")).nextSibling).toHaveTextContent("1");
    expect(lerToken()).toBe(sessao.access_token);
    expect(api.entrar).toHaveBeenCalledWith("rui@parceiros.pt", "Parceiro#2026x");
  });

  it("quem já tem sessão e abre o login vai para o painel", async () => {
    montar("/parceiro/entrar");
    expect(await screen.findByRole("region", { name: "Resumo" })).toBeInTheDocument();
  });

  it("um link profundo sem sessão volta ao sítio certo depois do login", async () => {
    api.entrar.mockResolvedValue(sessao);
    montar("/parceiro/casos/a-novo", { autenticado: false });
    await userEvent.type(await screen.findByLabelText("Email"), "rui@parceiros.pt");
    await userEvent.type(screen.getByLabelText("Palavra-passe"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("heading", { name: FIXTURES.casoDeProcesso.client_name })).toBeInTheDocument();
  });

  it("um token guardado que o servidor já não aceita cai no login (e não num ecrã vazio)", async () => {
    api.obterPerfil.mockRejectedValue(erroHttp(401, "Sessão inválida"));
    montar("/parceiro");
    expect(await screen.findByRole("button", { name: "Entrar" })).toBeInTheDocument();
    expect(lerToken()).toBeNull();
  });
});

describe("a moldura", () => {
  it("mostra o nome do parceiro e termina a sessão sem deixar nada", async () => {
    montar("/parceiro");
    expect(await screen.findByTestId("nome-do-parceiro")).toHaveTextContent(FIXTURES.perfil.name);
    await userEvent.click(screen.getByRole("button", { name: "Terminar sessão" }));
    expect(await screen.findByRole("button", { name: "Entrar" })).toBeInTheDocument();
    expect(lerToken()).toBeNull();
  });

  it("uma sessão que morre a meio (401 do servidor) leva ao login", async () => {
    montar("/parceiro");
    await screen.findByRole("region", { name: "Resumo" });
    act(() => anunciarSessaoExpirada());
    expect(await screen.findByRole("button", { name: "Entrar" })).toBeInTheDocument();
  });

  it("a navegação principal tem Painel e A minha conta", async () => {
    montar("/parceiro");
    const nav = await screen.findByRole("navigation", { name: "Navegação principal" });
    expect(within(nav).getByRole("link", { name: "Painel" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "A minha conta" })).toBeInTheDocument();
  });
});

describe("o convite", () => {
  const preencher = async (password, confirmacao = password) => {
    await userEvent.type(await screen.findByLabelText("Palavra-passe"), password);
    await userEvent.type(screen.getByLabelText("Repetir palavra-passe"), confirmacao);
  };

  it("mostra a quem o convite se destina", async () => {
    api.lerConvite.mockResolvedValue(convite);
    montar("/parceiro/convite/TOKEN-DO-CONVITE", { autenticado: false });
    expect(await screen.findByText(convite.email, { exact: false })).toBeInTheDocument();
    expect(api.lerConvite).toHaveBeenCalledWith("TOKEN-DO-CONVITE");
  });

  it("um convite inválido ou expirado diz-se com clareza, sem formulário", async () => {
    api.lerConvite.mockRejectedValue(erroHttp(400, "Convite inválido ou expirado."));
    montar("/parceiro/convite/velho", { autenticado: false });
    expect(await screen.findByRole("alert")).toHaveTextContent(/inválido ou expirou/i);
    expect(screen.queryByLabelText("Palavra-passe")).not.toBeInTheDocument();
  });

  it("palavras-passe diferentes não chegam ao servidor", async () => {
    api.lerConvite.mockResolvedValue(convite);
    montar("/parceiro/convite/TOKEN-DO-CONVITE", { autenticado: false });
    await preencher("Parceiro#2026x", "Outra#2026x");
    await userEvent.click(screen.getByRole("checkbox", { name: /termos/i }));
    await userEvent.click(screen.getByRole("button", { name: "Activar conta" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/não coincidem/i);
    expect(api.aceitarConvite).not.toHaveBeenCalled();
  });

  it("no primeiro acesso é preciso aceitar os termos para activar", async () => {
    api.lerConvite.mockResolvedValue(convite);
    montar("/parceiro/convite/TOKEN-DO-CONVITE", { autenticado: false });
    await preencher("Parceiro#2026x");
    const botao = screen.getByRole("button", { name: "Activar conta" });
    expect(botao).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox", { name: /termos/i }));
    expect(botao).toBeEnabled();
  });

  it("activar envia o token do link, a palavra-passe e os termos — e entra no painel", async () => {
    api.lerConvite.mockResolvedValue(convite);
    api.aceitarConvite.mockResolvedValue(sessao);
    montar("/parceiro/convite/TOKEN-DO-CONVITE", { autenticado: false });
    await preencher("Parceiro#2026x");
    await userEvent.click(screen.getByRole("checkbox", { name: /termos/i }));
    await userEvent.click(screen.getByRole("button", { name: "Activar conta" }));
    expect(await screen.findByRole("region", { name: "Resumo" })).toBeInTheDocument();
    expect(api.aceitarConvite).toHaveBeenCalledWith({
      token: "TOKEN-DO-CONVITE", password: "Parceiro#2026x", accept_terms: true,
    });
    expect(lerToken()).toBe(sessao.access_token);
  });

  it("uma palavra-passe fraca mostra a mensagem do servidor", async () => {
    api.lerConvite.mockResolvedValue(convite);
    api.aceitarConvite.mockRejectedValue(erroHttp(400, "Password deve conter pelo menos um dígito"));
    montar("/parceiro/convite/TOKEN-DO-CONVITE", { autenticado: false });
    await preencher("Fraquinha#");
    await userEvent.click(screen.getByRole("checkbox", { name: /termos/i }));
    await userEvent.click(screen.getByRole("button", { name: "Activar conta" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("pelo menos um dígito");
  });

  it("repor o acesso (conta já activa) não volta a pedir os termos", async () => {
    api.lerConvite.mockResolvedValue({ ...convite, first_access: false });
    montar("/parceiro/convite/TOKEN-DO-CONVITE", { autenticado: false });
    await preencher("Parceiro#2026x");
    expect(screen.queryByRole("checkbox", { name: /termos/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Activar conta" })).toBeEnabled();
  });
});

describe("a conta", () => {
  it("muda a palavra-passe e diz que mudou", async () => {
    api.mudarPalavraPasse.mockResolvedValue(sessao);
    montar("/parceiro/conta");
    await userEvent.type(await screen.findByLabelText("Palavra-passe actual"), "Parceiro#2026x");
    await userEvent.type(screen.getByLabelText("Palavra-passe nova"), "Outra#Pass2027");
    await userEvent.type(screen.getByLabelText("Repetir palavra-passe nova"), "Outra#Pass2027");
    await userEvent.click(screen.getByRole("button", { name: "Alterar palavra-passe" }));
    expect(await screen.findByRole("status")).toHaveTextContent(/alterada/i);
    expect(api.mudarPalavraPasse).toHaveBeenCalledWith("Parceiro#2026x", "Outra#Pass2027");
    expect(lerToken()).toBe(sessao.access_token);
  });

  it("a palavra-passe actual errada mostra o motivo e não deixa sessão nova", async () => {
    api.mudarPalavraPasse.mockRejectedValue(erroHttp(400, "A palavra-passe actual não está correcta."));
    montar("/parceiro/conta");
    await userEvent.type(await screen.findByLabelText("Palavra-passe actual"), "errada");
    await userEvent.type(screen.getByLabelText("Palavra-passe nova"), "Outra#Pass2027");
    await userEvent.type(screen.getByLabelText("Repetir palavra-passe nova"), "Outra#Pass2027");
    await userEvent.click(screen.getByRole("button", { name: "Alterar palavra-passe" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("actual não está correcta");
  });

  it("as novas têm de coincidir antes de ir ao servidor", async () => {
    montar("/parceiro/conta");
    await userEvent.type(await screen.findByLabelText("Palavra-passe actual"), "x");
    await userEvent.type(screen.getByLabelText("Palavra-passe nova"), "Outra#Pass2027");
    await userEvent.type(screen.getByLabelText("Repetir palavra-passe nova"), "Diferente#2027");
    await userEvent.click(screen.getByRole("button", { name: "Alterar palavra-passe" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/não coincidem/i);
    expect(api.mudarPalavraPasse).not.toHaveBeenCalled();
  });
});
