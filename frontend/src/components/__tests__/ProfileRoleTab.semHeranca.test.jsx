/**
 * Webmail de uma rede satélite: vazio, nunca herdado (QA, Out 2026).
 *
 * O utilizador da Domus abria a Configuração de Webmail e via a Caixa Geral da
 * Power com «Servidores IMAP/SMTP herdados da configuração global». O servidor
 * deixou de herdar para redes que não são a de omissão; aqui afirma-se o que o
 * ECRÃ faz com a resposta:
 *   - rede satélite sem caixa → nenhum aviso de herança, nenhuma conta, só o
 *     botão «Adicionar Conta de Email»;
 *   - contraprova: a rede de omissão continua a ver o aviso e a Caixa Geral;
 */
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
  post: vi.fn(),
  delete: vi.fn(),
}));

vi.mock("../../services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  default: api,
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() } }));
vi.mock("../ui/RichTextEditor", () => ({
  default: () => null,
  RichTextViewer: () => null,
}));

import ProfileRoleTab from "../ProfileRoleTab";

const ME = {
  active_company_display_name: "Bruno",
  active_company_professional_phone: "",
  active_company_job_title: "",
  active_company_signature: "",
  email_signature_effective: "",
  email_signature_source: "none",
};

const CONFIG_DA_POWER = {
  config_source: "system",
  is_configured: false,
  imap_server: "imap.power.pt",
  smtp_server: "smtp.power.pt",
};
const CONFIG_DA_ILHA = {
  config_source: "none",
  is_configured: false,
  imap_server: null,
  smtp_server: null,
};
const CAIXA_GERAL_DA_POWER = {
  id: "caixa-geral",
  email_address: "geral@powerealestate.pt",
  label: "Caixa Geral",
  is_caixa_geral: true,
  is_shared: true,
};

function servidor({ config, contas }) {
  api.get.mockImplementation(async (url) => {
    if (url.startsWith("/auth/me")) return { data: ME };
    if (url.startsWith("/users/me/email-config")) return { data: config };
    if (url.startsWith("/users/me/email-accounts")) return { data: { accounts: contas } };
    throw new Error(`pedido inesperado: ${url}`);
  });
}

const montar = (props = {}) =>
  render(
    <ProfileRoleTab
      companyId="cmp-domus"
      role="diretor"
      companyName="Domus"
      roleData={{}}
      onUpdate={() => {}}
      {...props}
    />,
  );

const AVISO_DE_HERANCA = /herdados da configuração global/i;

beforeEach(() => {
  vi.clearAllMocks();
});

describe("Configuração de Webmail da rede satélite", () => {
  it("sem caixa própria mostra só o botão de adicionar — nada herdado", async () => {
    servidor({ config: CONFIG_DA_ILHA, contas: [] });
    montar();

    expect(await screen.findByRole("button", { name: /adicionar conta de email/i })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText(/a carregar contas/i)).not.toBeInTheDocument());

    expect(screen.queryByText(AVISO_DE_HERANCA)).not.toBeInTheDocument();
    expect(screen.queryByText(/herdados da empresa/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Caixa Geral")).not.toBeInTheDocument();
    expect(screen.queryByText(/geral@powerealestate\.pt/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /editar conta de email/i })).not.toBeInTheDocument();
  });

  it("contraprova: a rede de omissão continua a ver o aviso e a Caixa Geral", async () => {
    servidor({ config: CONFIG_DA_POWER, contas: [CAIXA_GERAL_DA_POWER] });
    montar({ companyId: "cmp-power", companyName: "Power" });

    expect(await screen.findByText(AVISO_DE_HERANCA)).toBeInTheDocument();
    expect(await screen.findByText("geral@powerealestate.pt")).toBeInTheDocument();
  });
});
