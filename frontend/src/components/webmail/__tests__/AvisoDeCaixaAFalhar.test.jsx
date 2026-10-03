/**
 * O aviso de uma caixa a falhar (Lote 7, ponto 4).
 *
 * A auditoria perguntava se o sistema lida graciosamente com uma password de
 * IMAP expirada. A sincronização automática morria num `logger.warning` e o
 * ecrã mostrava a lista antiga sem um único aviso — o utilizador só descobria
 * dias depois, e o diagnóstico natural apontava para o servidor.
 *
 * A forma dos dados é a REAL: as contas vêm de `publicize_email_account`
 * (`services/user_email_config_service.py`), que desde este lote inclui o
 * resumo de `services/mailbox_health.resumo_para_o_ecra`.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import AvisoDeCaixaAFalhar from "../AvisoDeCaixaAFalhar";

const CREDENCIAIS_RECUSADAS = {
  id: "cfg-1",
  email_address: "consultor@powerealestate.pt",
  label: "Power",
  sync_status: "failed",
  sync_error_class: "autenticacao",
  sync_requires_action: true,
  sync_message:
    "As credenciais desta caixa de correio foram recusadas pelo servidor. "
    + "Actualize a password em Perfil → Configuração de Webmail; até lá não "
    + "entram emails novos.",
  sync_failing_since: "2026-09-30T10:00:00Z",
  sync_failures: 3,
};

const SERVIDOR_INATINGIVEL = {
  id: "cfg-2",
  email_address: "outro@exemplo.pt",
  sync_status: "failed",
  sync_error_class: "rede",
  sync_requires_action: false,
  sync_message: "Não foi possível alcançar o servidor de email.",
};

const SAUDAVEL = {
  id: "cfg-3",
  email_address: "bom@exemplo.pt",
  sync_status: "ok",
  sync_requires_action: false,
};

function montar(contas) {
  return render(
    <MemoryRouter>
      <AvisoDeCaixaAFalhar contas={contas} />
    </MemoryRouter>,
  );
}

describe("AvisoDeCaixaAFalhar", () => {
  it("avisa quando as credenciais foram recusadas, e diz desde quando", () => {
    montar([CREDENCIAIS_RECUSADAS]);
    const aviso = screen.getByTestId("aviso-caixa-a-falhar");
    expect(aviso).toHaveTextContent("Power");
    expect(aviso).toHaveTextContent(/credenciais/i);
    expect(aviso).toHaveTextContent(/há \d+ dias|desde (hoje|ontem)/i);
  });

  it("oferece o caminho para corrigir", () => {
    // Sem isto, o aviso diz o que está mal e manda procurar onde se resolve.
    montar([CREDENCIAIS_RECUSADAS]);
    const ligacao = screen.getByTestId("aviso-caixa-corrigir");
    expect(ligacao).toHaveAttribute("href", expect.stringContaining("/perfil"));
  });

  it("NÃO aparece para uma falha de rede", () => {
    // Passa sozinha. Avisar das duas com a mesma força ensina a ignorar as
    // duas — é o `desactivado ≠ em baixo` do painel de sinais vitais.
    montar([SERVIDOR_INATINGIVEL]);
    expect(screen.queryByTestId("aviso-caixa-a-falhar")).not.toBeInTheDocument();
  });

  it("não aparece com as contas todas saudáveis", () => {
    montar([SAUDAVEL]);
    expect(screen.queryByTestId("aviso-caixa-a-falhar")).not.toBeInTheDocument();
  });

  it("não aparece sem contas, nem com entrada inválida", () => {
    for (const entrada of [[], null, undefined, {}]) {
      const { unmount } = montar(entrada);
      expect(screen.queryByTestId("aviso-caixa-a-falhar")).not.toBeInTheDocument();
      unmount();
    }
  });

  it("lista as DUAS caixas quando duas estão recusadas", () => {
    // Um utilizador multi-empresa tem uma caixa por empresa; avisar de uma só
    // mandava-o corrigir metade do problema.
    montar([
      CREDENCIAIS_RECUSADAS,
      { ...CREDENCIAIS_RECUSADAS, id: "cfg-9", label: "Precision",
        email_address: "x@precision.pt" },
      SAUDAVEL,
    ]);
    const aviso = screen.getByTestId("aviso-caixa-a-falhar");
    expect(aviso).toHaveTextContent("Power");
    expect(aviso).toHaveTextContent("Precision");
    expect(aviso).not.toHaveTextContent("bom@exemplo.pt");
  });

  it("usa o endereço quando não há rótulo", () => {
    montar([{ ...CREDENCIAIS_RECUSADAS, label: "" }]);
    expect(screen.getByTestId("aviso-caixa-a-falhar"))
      .toHaveTextContent("consultor@powerealestate.pt");
  });
});
