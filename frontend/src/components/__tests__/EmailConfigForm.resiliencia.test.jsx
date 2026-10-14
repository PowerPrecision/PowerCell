/**
 * EmailConfigForm — as chamadas ao servidor podem falhar sem partir o ecrã (Lote 6, ponto 5).
 *
 * O `502 Bad Gateway` no ecrã de teste de SMTP da Domus é do servidor (ou da conta SMTP dessa
 * empresa), não das credenciais do utilizador. O ecrã tem de o dizer — e continuar a funcionar —
 * em vez de «Erro ao testar a ligação», que manda mexer em credenciais que podem estar certas.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const sessao = vi.hoisted(() => ({
  valor: { user: { id: "u-1", role: "consultor" }, effectiveRole: "consultor", effectiveCompanyId: "cmp-domus" },
}));
vi.mock("../../contexts/AuthContext", () => ({ useAuth: () => sessao.valor }));

const rede = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() }));
vi.mock("../../services/api", () => ({ default: rede }));

const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

import EmailConfigForm from "../EmailConfigForm";

const CONFIGURADA = {
  is_configured: true, email_address: "geral@domus.pt", imap_server: "imap.domus.pt", imap_port: 993,
  smtp_server: "smtp.domus.pt", smtp_port: 465, has_password: true, config_source: "user",
};
const erroHttp = (status, data = {}) => ({ response: { status, data } });
const semResposta = () => Object.assign(new Error("Network Error"), { code: "ERR_NETWORK", request: {} });

async function abrirEmEdicao(u) {
  render(<EmailConfigForm mode="self" companyId="cmp-domus" />);
  await u.click(await screen.findByRole("button", { name: /Editar Configuração/i }));
}

beforeEach(() => {
  Object.values(rede).forEach((f) => f.mockReset());
  Object.values(toast).forEach((f) => f.mockClear());
  rede.get.mockResolvedValue({ data: CONFIGURADA });
});

describe("EmailConfigForm — o servidor falha", () => {
  it("502 ao ENVIAR O EMAIL DE TESTE: diz que o servidor não respondeu e o ecrã continua", async () => {
    rede.post.mockRejectedValue(erroHttp(502, "<html>502 Bad Gateway</html>"));
    const u = userEvent.setup();
    await abrirEmEdicao(u);

    await u.click(await screen.findByRole("button", { name: /Enviar Email de Teste/i }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(expect.stringMatching(/servidor não respondeu \(erro 502\)/i)));
    // Um só aviso (o do interceptor é suprimido) e nunca o texto que culpa as credenciais.
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.error.mock.calls[0][0]).not.toMatch(/não foi possível enviar o email de teste/i);
    expect(rede.post.mock.calls[0][2]).toMatchObject({ skipErrorToast: true });
    expect(screen.getByRole("button", { name: /Enviar Email de Teste/i })).toBeEnabled();
  });

  it("ligação cortada ao testar a ligação IMAP/SMTP: diz que não há ligação e o botão volta", async () => {
    // 1.º POST = guardar; 2.º = testar. Falha o segundo, como num servidor que reinicia a meio.
    rede.post.mockResolvedValueOnce({ data: {} }).mockRejectedValueOnce(semResposta());
    const u = userEvent.setup();
    await abrirEmEdicao(u);

    await u.click(await screen.findByRole("button", { name: /Testar Ligação/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringMatching(/sem ligação ao servidor/i)));
    expect(screen.getByRole("button", { name: /Testar Ligação/i })).toBeEnabled();
  });

  it("um erro da APLICAÇÃO (400) mostra o motivo do servidor, não a mensagem de rede", async () => {
    rede.post.mockRejectedValue(erroHttp(400, { detail: "Credenciais SMTP recusadas pelo servidor." }));
    const u = userEvent.setup();
    await abrirEmEdicao(u);

    await u.click(await screen.findByRole("button", { name: /Enviar Email de Teste/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Credenciais SMTP recusadas pelo servidor."));
  });

  it("a LEITURA da configuração falha (502): diz-se, não rebenta e oferece tentar outra vez", async () => {
    rede.get.mockRejectedValueOnce(erroHttp(502, "<html>")).mockResolvedValueOnce({ data: CONFIGURADA });
    const u = userEvent.setup();
    render(<EmailConfigForm mode="self" companyId="cmp-domus" />);

    const aviso = await screen.findByTestId("email-config-erro-de-leitura");
    expect(aviso).toHaveTextContent(/servidor não respondeu/i);
    expect(aviso).toHaveTextContent(/não foi alterada/i);

    await u.click(screen.getByRole("button", { name: /Tentar novamente/i }));

    await waitFor(() => expect(screen.queryByTestId("email-config-erro-de-leitura")).not.toBeInTheDocument());
    expect(await screen.findByRole("button", { name: /Editar Configuração/i })).toBeInTheDocument();
  });

  it("contraprova: leitura bem sucedida não mostra aviso", async () => {
    render(<EmailConfigForm mode="self" companyId="cmp-domus" />);
    await screen.findByRole("button", { name: /Editar Configuração/i });
    expect(screen.queryByTestId("email-config-erro-de-leitura")).not.toBeInTheDocument();
  });
});
