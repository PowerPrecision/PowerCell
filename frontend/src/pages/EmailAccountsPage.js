/**
 * EmailAccountsPage — Página centralizada de "Gestão de Contas de Email" para o PowerCell CRM.
 *
 * CONSOLIDATES all email-related configurations into one organized page:
 *   Card 1: Email do Sistema (Transacional) — system_smtp SMTP config
 *   Card 2: Conta de Indexação (IMAP Recepção) — system_webmail IMAP config
 *   Card 3: Contas Partilhadas por Departamento (Google OAuth) — shared email per role
 *
 * Cada cartão foi extraído para um componente independente em
 * `components/emailAccounts/` (Refactor UX — Fev 2026). Esta página é
 * apenas um wrapper que valida permissões e organiza o layout.
 *
 * ACCESS: Restricted to admin and ceo roles only (same guard as SystemConfigPage).
 *
 * @context {AuthContext} — Consumes user for verifying permissions
 * @route /admin/email-accounts — Página acessível apenas a admin/ceo
 */
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { hasAnyRole } from "../utils/roleUtils";
import { Mail, XCircle } from "lucide-react";
import { SystemSmtpCard } from "../components/emailAccounts/SystemSmtpCard";
import { IndexationImapCard } from "../components/emailAccounts/IndexationImapCard";
import { SharedEmailCard } from "../components/emailAccounts/SharedEmailCard";

const EmailAccountsPage = ({ embedded = false }) => {
  const { user } = useAuth();
  const wrapLayout = (children) => embedded ? children : <DashboardLayout>{children}</DashboardLayout>;

  if (!hasAnyRole(user, ["admin", "ceo"])) {
    return wrapLayout(
      <div className="text-center py-12">
        <XCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
        <h2 className="text-xl font-semibold">Acesso Restrito</h2>
        <p className="text-muted-foreground">
          Apenas administradores podem aceder à gestão de contas de email.
        </p>
      </div>
    );
  }

  return wrapLayout(
      <div className="space-y-6" data-testid="email-accounts-page">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Mail className="h-6 w-6" />
              Gestão de Contas de Email
            </h1>
            <p className="text-muted-foreground">
              Configure todas as contas de email e canais de comunicação do sistema num único ecrã
            </p>
          </div>
        </div>

        {/* Cards Grid */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          {/* Card 1: Email do Sistema (Transacional) */}
          <SystemSmtpCard />

          {/* Card 2: Conta de Indexação (IMAP Recepção) */}
          <IndexationImapCard />

          {/* Card 3: Contas Partilhadas por Departamento */}
          <div className="xl:col-span-2">
            <SharedEmailCard />
          </div>

          {/* PACOTE BG: CompanyEmailCard removido — a configuração de email
              por empresa passa a ser feita no detalhe de cada Empresa
              (CompaniesAdminTab). */}
        </div>
      </div>
  );
};

export default EmailAccountsPage;
