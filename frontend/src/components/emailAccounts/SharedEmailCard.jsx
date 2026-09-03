/**
 * SharedEmailCard — Card 3: Contas Partilhadas por Departamento (Google OAuth)
 * Extraído de EmailAccountsPage.js (Refactor UX — Fev 2026).
 * Mantém exatamente a mesma lógica e gestão de estado (React Query/hooks).
 */
import { useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../../contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../ui/card";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Badge } from "../ui/badge";
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from "../ui/accordion";
import { toast } from "sonner";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import { formatDate } from "../../lib/utils";
import {
  Users,
  Save,
  Loader2,
  CheckCircle,
  XCircle,
  RefreshCw,
  RotateCcw,
  MailCheck,
  Info,
  Plug,
} from "lucide-react";
import { API_URL } from "./emailAccountsApi";
import { testCompanyEmailConnection } from "../../services/api";

const SHARED_EMAIL_ROLES = [
  { role: "indexacao", label: "Indexação", description: "Email partilhado do departamento de indexação" },
  { role: "suporte", label: "Suporte", description: "Email partilhado do departamento de suporte" },
  { role: "comercial", label: "Comercial", description: "Email partilhado do departamento comercial" },
  { role: "admin", label: "Administração", description: "Email partilhado da administração" },
];

const EMPTY_SHARED_MANUAL_FORM = {
  email_address: "",
  display_name: "",
  smtp_server: "",
  smtp_port: 465,
  imap_server: "",
  imap_port: 993,
  imap_user: "",
  imap_password: "",
};

export const SharedEmailCard = () => {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const [authenticating, setAuthenticating] = useState(null);
  const [syncing, setSyncing] = useState(null);
  const [manualOpenRole, setManualOpenRole] = useState(null);
  const [manualForm, setManualForm] = useState(EMPTY_SHARED_MANUAL_FORM);
  const [savingManual, setSavingManual] = useState(null);
  const [testingManual, setTestingManual] = useState(null);

  const {
    data: configs = [],
    isLoading: loading,
    refetch: fetchConfigs,
  } = useQuery({
    queryKey: ["shared-email"],
    enabled: Boolean(token),
    queryFn: async () => {
      const res = await fetch(`${API_URL}/api/admin/shared-email`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Erro ao carregar configs de email partilhado");
      const data = await res.json();
      return data.configs || [];
    },
  });

  // Escutar postMessage do popup OAuth
  useEffect(() => {
    const handleMessage = (event) => {
      if (event.data?.type === "shared_google_oauth_success") {
        toast.success(`Google OAuth conectado para ${event.data.email}`);
        setAuthenticating(null);
        queryClient.invalidateQueries({ queryKey: ["shared-email"] });
      }
      if (event.data?.type === "shared_google_oauth_error") {
        toast.error(`Autenticação cancelada: ${event.data.error}`);
        setAuthenticating(null);
      }
    };
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [queryClient]);

  const handleGoogleAuth = async (role, emailAddress) => {
    setAuthenticating(role);
    try {
      const params = new URLSearchParams();
      if (emailAddress) params.set("email_address", emailAddress);

      const res = await fetch(`${API_URL}/api/admin/shared-email/${role}/google/login?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const data = await res.json();
        toast.error(extractErrorMessage(data.detail, "Erro ao iniciar autenticação Google"));
        setAuthenticating(null);
        return;
      }
      const data = await res.json();

      const popup = window.open(
        data.authorization_url,
        "google_oauth",
        "width=600,height=700,left=200,top=100"
      );

      if (popup) {
        // Timeout de segurança — limpa o estado de autenticação após 2 minutos
        setTimeout(() => { setAuthenticating(null); }, 120000);
      } else {
        toast.error("Popup bloqueado. Permita popups para este site.");
        setAuthenticating(null);
      }
    } catch {
      toast.error("Erro ao iniciar autenticação Google");
      setAuthenticating(null);
    }
  };

  const handleSync = async (role) => {
    setSyncing(role);
    try {
      const res = await fetch(`${API_URL}/api/admin/shared-email/${role}/sync`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        toast.success(
          `Sincronização concluída: ${data.total_synced || 0} novos, ` +
          `${data.total_duplicates || 0} duplicados`
        );
        fetchConfigs();
      } else {
        const data = await res.json();
        // Mostrar mensagem de erro detalhada do backend
        const errorMsg = extractErrorMessage(data.detail, "Erro ao sincronizar");
        if (res.status === 404) {
          toast.error(`Configuração em falta — ${errorMsg}`, { duration: 6000 });
        } else if (res.status === 422) {
          toast.error(`OAuth necessário — ${errorMsg}`, { duration: 6000 });
        } else if (res.status === 503) {
          toast.error(`Serviço indisponível — ${errorMsg}`, { duration: 6000 });
        } else {
          toast.error(errorMsg, { duration: 6000 });
        }
      }
    } catch {
      toast.error("Erro de ligação ao sincronizar");
    } finally {
      setSyncing(null);
    }
  };

  const handleDisconnect = async (role) => {
    if (!window.confirm("Desconectar a conta Google deste departamento?")) return;
    try {
      const res = await fetch(`${API_URL}/api/admin/shared-email/${role}/google`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        toast.success("Conta Google desconectada");
        fetchConfigs();
      } else {
        toast.error("Erro ao desconectar");
      }
    } catch {
      toast.error("Erro ao desconectar");
    }
  };

  const getConfig = (role) => configs.find((c) => c.role === role);

  // PACOTE — Webmail: configuração manual IMAP/SMTP por departamento
  // (alternativa ao Google OAuth), via PUT /api/admin/shared-email/{role}.
  const toggleManualForm = (role) => {
    if (manualOpenRole === role) {
      setManualOpenRole(null);
      return;
    }
    const cfg = getConfig(role);
    setManualForm({
      email_address: cfg?.email_address || "",
      display_name: cfg?.display_name || "",
      smtp_server: cfg?.smtp_server || "",
      smtp_port: cfg?.smtp_port || 465,
      imap_server: cfg?.imap_server || "",
      imap_port: cfg?.imap_port || 993,
      imap_user: cfg?.email_address || "",
      imap_password: "",
    });
    setManualOpenRole(role);
  };

  const handleSaveManual = async (role) => {
    if (!manualForm.email_address || !manualForm.imap_server || !manualForm.smtp_server) {
      toast.error("Preencha o email, o servidor SMTP e o servidor IMAP");
      return;
    }
    setSavingManual(role);
    try {
      const res = await fetch(`${API_URL}/api/admin/shared-email/${role}`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          role,
          email_address: manualForm.email_address,
          display_name: manualForm.display_name,
          smtp_server: manualForm.smtp_server,
          smtp_port: manualForm.smtp_port,
          imap_server: manualForm.imap_server,
          imap_port: manualForm.imap_port,
          encrypted_password: manualForm.imap_password,
        }),
      });
      if (res.ok) {
        toast.success("Configuração IMAP/SMTP guardada");
        setManualOpenRole(null);
        queryClient.invalidateQueries({ queryKey: ["shared-email"] });
      } else {
        const data = await res.json();
        toast.error(extractErrorMessage(data.detail, "Erro ao guardar configuração"));
      }
    } catch {
      toast.error("Erro de conexão");
    } finally {
      setSavingManual(null);
    }
  };

  // BUGFIX (Bug 4, Fev 2026): botão "Testar Ligação" no formulário manual —
  // testa SMTP e IMAP reais com os valores atuais do formulário (sem gravar),
  // via o endpoint genérico de teste já usado em Empresas/Admin. O utilizador
  // IMAP é reutilizado como utilizador SMTP (mesmo padrão do handleSaveManual).
  const handleTestManualConnection = async (role) => {
    if (!manualForm.imap_server && !manualForm.smtp_server) {
      toast.error("Preencha o servidor SMTP e/ou IMAP para testar a ligação");
      return;
    }
    if (!manualForm.imap_password) {
      toast.error("Introduza a password para testar a ligação");
      return;
    }
    setTestingManual(role);
    try {
      const res = await testCompanyEmailConnection({
        smtp_host: manualForm.smtp_server,
        smtp_port: manualForm.smtp_port,
        smtp_email: manualForm.imap_user,
        smtp_password: manualForm.imap_password,
        imap_host: manualForm.imap_server,
        imap_port: manualForm.imap_port,
        imap_email: manualForm.imap_user,
        imap_password: manualForm.imap_password,
      });
      const messages = Object.values(res.data?.results || {}).map((r) => r.message);
      toast.success(messages.join(" | ") || "Ligação validada com sucesso.");
    } catch (err) {
      toast.error(extractErrorMessage(err.response?.data?.detail, "Falha ao testar a ligação."));
    } finally {
      setTestingManual(null);
    }
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="py-12 flex justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card data-testid="shared-email-card">
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-purple-100 dark:bg-purple-900/30">
              <Users className="h-5 w-5 text-purple-700 dark:text-purple-400" />
            </div>
            <div>
              <CardTitle className="text-base">Contas Partilhadas por Departamento (Google OAuth)</CardTitle>
              <CardDescription className="text-xs mt-0.5">
                Contas de email partilhadas por departamento com autenticação Google OAuth
              </CardDescription>
            </div>
          </div>
          {configs.some((c) => c.has_google_oauth) && (
            <Badge variant="secondary" className="text-xs bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
              {configs.filter((c) => c.has_google_oauth).length} conectadas
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {/* PACOTE: colapsável fechado por defeito — funcionalidade pouco usada,
            mantém o ecrã de /contas-email limpo. Expande sob pedido. */}
        <Accordion type="single" collapsible className="w-full">
          <AccordionItem value="shared-email-departments" className="border-none">
            <AccordionTrigger className="py-2 hover:no-underline" data-testid="shared-email-accordion-trigger">
              <span className="text-sm text-muted-foreground">
                Ver departamentos configurados
                {configs.some((c) => c.has_google_oauth) && (
                  <span className="ml-2 text-emerald-600 dark:text-emerald-400 font-medium">
                    ({configs.filter((c) => c.has_google_oauth).length} conectadas)
                  </span>
                )}
              </span>
            </AccordionTrigger>
            <AccordionContent className="space-y-4 pt-2">
        {/* Info banner */}
        <div className="flex items-start gap-3 p-3 bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800 rounded-lg">
          <Info className="h-4 w-4 text-blue-500 mt-0.5 shrink-0" />
          <div className="text-sm text-blue-800 dark:text-blue-300">
            <p className="font-medium">Email Partilhado por Departamento</p>
            <p className="text-blue-700 dark:text-blue-400 mt-0.5">
              Configure uma conta Google para cada departamento. O sistema sincroniza
              automaticamente os emails recebidos. Os utilizadores do departamento
              podem consultar estes emails nos respetivos processos.
            </p>
          </div>
        </div>

        {/* Role sub-cards */}
        <div className="space-y-3">
          {SHARED_EMAIL_ROLES.map(({ role, label, description }) => {
            const cfg = getConfig(role);
            const isConnected = cfg?.has_google_oauth;
            const isAuth = authenticating === role;
            const isSyncingRole = syncing === role;

            return (
              <div key={role} className="border rounded-lg p-4 space-y-3 hover:bg-muted/20 transition-colors">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <MailCheck className={`h-5 w-5 ${isConnected ? "text-green-600" : "text-muted-foreground"}`} />
                    <div>
                      <p className="text-sm font-medium">{label}</p>
                      <p className="text-xs text-muted-foreground">{description}</p>
                    </div>
                  </div>
                  {isConnected ? (
                    <Badge className="bg-green-50 text-green-700 border-green-200 dark:bg-green-900/30 dark:text-green-400 dark:border-green-800">
                      <CheckCircle className="h-3 w-3 mr-1" />
                      Conectado
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-muted-foreground">
                      Não configurado
                    </Badge>
                  )}
                </div>

                {isConnected && (
                  <div className="bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 rounded-lg p-3">
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-green-700 dark:text-green-300">
                      <span>Email: <strong>{cfg.google_email || cfg.email_address || "—"}</strong></span>
                      {cfg.oauth_connected_at && (
                        <span>Conectado: {formatDate(cfg.oauth_connected_at)}</span>
                      )}
                      {cfg.last_sync_at && (
                        <span>Último sync: {formatDate(cfg.last_sync_at)}</span>
                      )}
                      {cfg.total_emails_synced > 0 && (
                        <span>Emails: {cfg.total_emails_synced}</span>
                      )}
                    </div>
                  </div>
                )}

                {!isConnected && cfg?.email_address && (
                  <div className="flex items-center gap-2">
                    <Label className="text-xs text-muted-foreground">Email partilhado:</Label>
                    <Input value={cfg.email_address} disabled className="max-w-xs h-8 text-sm bg-muted" />
                  </div>
                )}

                {!isConnected && !cfg?.email_address && (
                  <p className="text-sm text-muted-foreground">
                    Nenhuma conta Google associada. Autentique para ativar a sincronização de emails.
                  </p>
                )}

                <div className="flex items-center gap-2 pt-2 border-t">
                  {isConnected ? (
                    <>
                      <Button variant="outline" size="sm" onClick={() => handleSync(role)} disabled={isSyncingRole} className="gap-2" data-testid={`shared-email-sync-btn-${role}`}>
                        {isSyncingRole ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                        Sincronizar Agora
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => handleGoogleAuth(role)} disabled={isAuth} className="gap-2" data-testid={`shared-email-reauth-btn-${role}`}>
                        {isAuth ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
                        Reautenticar / Trocar Conta
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => handleDisconnect(role)} className="gap-2 text-destructive hover:text-destructive ml-auto" data-testid={`shared-email-disconnect-btn-${role}`}>
                        <XCircle className="h-4 w-4" />
                        Desconectar
                      </Button>
                    </>
                  ) : (
                    <Button onClick={() => handleGoogleAuth(role)} disabled={isAuth} className="gap-2 bg-emerald-600 hover:bg-emerald-700" data-testid={`shared-email-google-auth-btn-${role}`}>
                      {isAuth ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <svg className="h-4 w-4" viewBox="0 0 24 24">
                          <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
                          <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                          <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                          <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                        </svg>
                      )}
                      Autenticar com o Google
                    </Button>
                  )}
                </div>

                {/* PACOTE — Webmail: alternativa manual (IMAP/SMTP) ao Google OAuth */}
                <div className="pt-3 border-t">
                  <button
                    type="button"
                    data-testid={`shared-email-manual-toggle-${role}`}
                    onClick={() => toggleManualForm(role)}
                    className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <MailCheck className="h-4 w-4" />
                    Configuração manual IMAP/SMTP (alternativa ao Google)
                  </button>

                  {manualOpenRole === role && (
                    <div className="mt-3 border rounded-lg p-4 bg-muted/30 space-y-4">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="space-y-2">
                          <Label htmlFor={`se_email_${role}`}>Email da caixa partilhada</Label>
                          <Input
                            id={`se_email_${role}`}
                            data-testid={`shared-email-manual-email-${role}`}
                            value={manualForm.email_address}
                            onChange={(e) => setManualForm({ ...manualForm, email_address: e.target.value })}
                            placeholder={`${role}@empresa.pt`}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor={`se_display_${role}`}>Nome visível</Label>
                          <Input
                            id={`se_display_${role}`}
                            value={manualForm.display_name}
                            onChange={(e) => setManualForm({ ...manualForm, display_name: e.target.value })}
                            placeholder={`Email de ${label}`}
                          />
                        </div>

                        {/* SMTP primeiro */}
                        <div className="space-y-2">
                          <Label htmlFor={`se_smtp_server_${role}`}>Servidor SMTP</Label>
                          <Input
                            id={`se_smtp_server_${role}`}
                            data-testid={`shared-email-manual-smtp-host-${role}`}
                            value={manualForm.smtp_server}
                            onChange={(e) => setManualForm({ ...manualForm, smtp_server: e.target.value })}
                            placeholder="smtp.empresa.pt"
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor={`se_smtp_port_${role}`}>Porta SMTP</Label>
                          <Input
                            id={`se_smtp_port_${role}`}
                            type="number"
                            value={manualForm.smtp_port}
                            onChange={(e) => setManualForm({ ...manualForm, smtp_port: parseInt(e.target.value) || 465 })}
                            placeholder="465"
                          />
                        </div>

                        {/* IMAP imediatamente a seguir ao SMTP */}
                        <div className="space-y-2">
                          <Label htmlFor={`se_imap_host_${role}`}>Servidor IMAP</Label>
                          <Input
                            id={`se_imap_host_${role}`}
                            data-testid={`shared-email-manual-imap-host-${role}`}
                            value={manualForm.imap_server}
                            onChange={(e) => setManualForm({ ...manualForm, imap_server: e.target.value })}
                            placeholder="imap.empresa.pt"
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor={`se_imap_port_${role}`}>Porta IMAP</Label>
                          <Input
                            id={`se_imap_port_${role}`}
                            data-testid={`shared-email-manual-imap-port-${role}`}
                            type="number"
                            value={manualForm.imap_port}
                            onChange={(e) => setManualForm({ ...manualForm, imap_port: parseInt(e.target.value) || 993 })}
                            placeholder="993"
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor={`se_imap_user_${role}`}>Utilizador IMAP</Label>
                          <Input
                            id={`se_imap_user_${role}`}
                            data-testid={`shared-email-manual-imap-user-${role}`}
                            value={manualForm.imap_user}
                            onChange={(e) => setManualForm({ ...manualForm, imap_user: e.target.value, email_address: e.target.value })}
                            placeholder={`${role}@empresa.pt`}
                          />
                          <p className="text-xs text-muted-foreground">Usado também como utilizador SMTP</p>
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor={`se_imap_password_${role}`}>Password IMAP</Label>
                          <Input
                            id={`se_imap_password_${role}`}
                            data-testid={`shared-email-manual-imap-password-${role}`}
                            type="password"
                            value={manualForm.imap_password}
                            onChange={(e) => setManualForm({ ...manualForm, imap_password: e.target.value })}
                            placeholder={cfg?.has_imap_password ? "•••••••• (deixe vazio para manter)" : "Password"}
                          />
                        </div>
                      </div>
                      <div className="flex justify-end gap-2 pt-2 border-t">
                        <Button variant="outline" size="sm" onClick={() => setManualOpenRole(null)} data-testid={`shared-email-manual-cancel-${role}`}>
                          Cancelar
                        </Button>
                        <Button
                          variant="secondary"
                          size="sm"
                          data-testid={`shared-email-manual-test-${role}`}
                          onClick={() => handleTestManualConnection(role)}
                          disabled={testingManual === role}
                          className="gap-2"
                        >
                          {testingManual === role ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plug className="h-3 w-3" />}
                          Testar Ligação
                        </Button>
                        <Button
                          size="sm"
                          data-testid={`shared-email-manual-save-${role}`}
                          onClick={() => handleSaveManual(role)}
                          disabled={savingManual === role}
                          className="gap-2"
                        >
                          {savingManual === role ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                          Guardar
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </CardContent>
    </Card>
  );
};

export default SharedEmailCard;
