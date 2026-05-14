/**
 * EmailAccountsPage — Página centralizada de "Gestão de Contas de Email" para o PowerCell CRM.
 *
 * CONSOLIDATES all email-related configurations into one organized page:
 *   Card 1: Email do Sistema (Transacional) — system_smtp SMTP config
 *   Card 2: Conta de Indexação (IMAP Recepção) — system_webmail IMAP config
 *   Card 3: Contas Partilhadas por Departamento (Google OAuth) — shared email per role
 *   Card 4: Configuração de Email por Empresa — per-company IMAP/SMTP defaults
 *
 * ACCESS: Restricted to admin and ceo roles only (same guard as SystemConfigPage).
 * Each card is independent with its own state, data fetching, and save handlers.
 *
 * @context {AuthContext} — Consumes token, user for verifying permissions and API calls
 * @route /admin/email-accounts — Página acessível apenas a admin/ceo
 */
import React, { useState, useEffect, useCallback } from "react";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Badge } from "../components/ui/badge";
import { Switch } from "../components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { hasAnyRole } from "../utils/roleUtils";
import RichTextEditor from "../components/ui/RichTextEditor";
import { toast } from "sonner";
import {
  Mail,
  Globe,
  Users,
  Building,
  Building2,
  ShieldCheck,
  Save,
  Loader2,
  Zap,
  CheckCircle,
  XCircle,
  RefreshCw,
  RotateCcw,
  MailCheck,
  Info,
  Plus,
  FileEdit,
  Trash2,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// ====================================================================
// Card 1: Email do Sistema (Transacional) — system_smtp
// Copied from IntegrationsConfigSection Bloco A
// ====================================================================

const SystemSmtpCard = () => {
  const { token } = useAuth();
  const [systemSmtp, setSystemSmtp] = useState({
    resend_api_key: "",
    smtp_from_email: "",
    smtp_from_name: "",
    email_signature: "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(null);

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const res = await fetch(`${API_URL}/api/system-config`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const response = await res.json();
          const data = response.config || response;
          if (data.system_smtp) {
            setSystemSmtp((prev) => ({
              ...prev,
              resend_api_key: data.system_smtp.resend_api_key || "",
              smtp_from_email: data.system_smtp.smtp_from_email || "",
              smtp_from_name: data.system_smtp.smtp_from_name || "",
              email_signature: data.system_smtp.email_signature || "",
            }));
          }
        }
      } catch (error) {
        console.error("Error fetching system_smtp config:", error);
      } finally {
        setLoading(false);
      }
    };
    fetchConfig();
  }, [token]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = { ...systemSmtp };
      const res = await fetch(`${API_URL}/api/system-config/system_smtp`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        toast.success("Configuração guardada com sucesso");
      } else {
        const data = await res.json();
        toast.error(data.detail || "Erro ao guardar configuração");
      }
    } catch (error) {
      toast.error("Erro ao guardar configuração");
    } finally {
      setSaving(false);
    }
  };

  const handleTestSmtp = async () => {
    setTesting("smtp");
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);
    try {
      const res = await fetch(`${API_URL}/api/system-config/test-connection/system-smtp`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        signal: controller.signal,
      });
      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          toast.success("✅ Resend API conectado com sucesso!");
        } else {
          toast.error(data.message || "Falha na conexão");
        }
      } else {
        const data = await res.json();
        toast.error(data.detail || data.message || "Falha na conexão");
      }
    } catch (err) {
      if (err.name === "AbortError") {
        toast.error("Timeout: o teste demorou demasiado tempo (30s)");
      } else {
        toast.error("Erro no teste de conexão");
      }
    } finally {
      clearTimeout(timeoutId);
      setTesting(null);
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
    <Card>
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-teal-100 dark:bg-teal-900/30">
              <Mail className="h-5 w-5 text-teal-700 dark:text-teal-400" />
            </div>
            <div>
              <CardTitle className="text-base">Email do Sistema (Transacional)</CardTitle>
              <CardDescription className="text-xs mt-0.5">
                Envio via Resend API — emails transacionais: links de documentação, convites, alertas automáticos e notificações do sistema. Sem Reply-To por política.
              </CardDescription>
            </div>
          </div>
          {systemSmtp.resend_api_key && (
            <Badge variant="secondary" className="text-xs bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
              Configurado
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="sys_resend_key">Resend API Key</Label>
            <Input id="sys_resend_key" type="password" placeholder="re_xxxxxxxxxxxx" value={systemSmtp.resend_api_key}
              onChange={(e) => setSystemSmtp((p) => ({ ...p, resend_api_key: e.target.value }))} />
            <p className="text-xs text-muted-foreground">Chave de API do Resend (obter em <a href="https://resend.com/api-keys" target="_blank" rel="noopener noreferrer" className="text-teal-600 hover:underline">resend.com/api-keys</a>)</p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="sys_smtp_from">Email do Remetente (From)</Label>
            <Input id="sys_smtp_from" placeholder="no-reply@powerealestate.pt" value={systemSmtp.smtp_from_email}
              onChange={(e) => setSystemSmtp((p) => ({ ...p, smtp_from_email: e.target.value }))} />
            <p className="text-xs text-muted-foreground">Endereço que aparecerá como remetente. O domínio deve estar verificado no Resend.</p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="sys_smtp_from_name">Nome do Remetente</Label>
            <Input id="sys_smtp_from_name" placeholder="Power Real Estate" value={systemSmtp.smtp_from_name}
              onChange={(e) => setSystemSmtp((p) => ({ ...p, smtp_from_name: e.target.value }))} />
            <p className="text-xs text-muted-foreground">Nome que aparecerá como remetente (ex: Power Real Estate)</p>
          </div>
        </div>
        {/* Resend API Info */}
        <div className="rounded-md border border-teal-200 bg-teal-50 dark:border-teal-900/50 dark:bg-teal-950/20 p-3">
          <div className="flex items-start gap-2">
            <Zap className="w-4 h-4 text-teal-600 dark:text-teal-400 mt-0.5 shrink-0" />
            <div className="text-xs text-teal-800 dark:text-teal-300">
              <p className="font-medium">Envio via Resend API (HTTPS)</p>
              <p className="mt-0.5">
                O Resend usa a porta 443 (HTTPS) para envio de emails, o que elimina
                problemas de bloqueio de portas SMTP (25/465/587) em ambientes como o Render.
                Não é necessário configurar host, porta ou username — apenas a API Key.
              </p>
            </div>
          </div>
        </div>
        {/* No-Reply Policy Notice */}
        <div className="rounded-md border border-green-200 bg-green-50 dark:border-green-900/50 dark:bg-green-950/20 p-3">
          <div className="flex items-start gap-2">
            <ShieldCheck className="w-4 h-4 text-green-600 dark:text-green-400 mt-0.5 shrink-0" />
            <div className="text-xs text-green-800 dark:text-green-300">
              <p className="font-medium">Reply-To desativado por política</p>
              <p className="mt-0.5">
                Não existe nenhum campo de &quot;Reply-To&quot; nesta configuração. Todos os emails enviados
                via este Bloco usam exclusivamente o endereço &quot;From&quot; configurado acima, sem qualquer
                cabeçalho de resposta. Um aviso automático é adicionado ao rodapé de cada email.
              </p>
            </div>
          </div>
        </div>
        {/* Email Signature */}
        <div className="space-y-2">
          <Label>Assinatura de Email</Label>
          <RichTextEditor
            value={systemSmtp.email_signature || ""}
            onChange={(val) => setSystemSmtp((p) => ({ ...p, email_signature: val }))}
            placeholder="Escreva a assinatura que será anexada automaticamente ao final de todos os emails enviados por esta conta..."
            minHeight={120}
          />
          <p className="text-xs text-muted-foreground">
            Esta assinatura será automaticamente anexada ao final de todos os emails transacionais enviados pelo sistema.
          </p>
        </div>
        <div className="flex items-center gap-3 pt-2">
          <Button onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
            Guardar
          </Button>
          <Button variant="outline" onClick={handleTestSmtp} disabled={testing === "smtp"}>
            {testing === "smtp" ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Zap className="h-4 w-4 mr-2" />}
            Testar Conexão
          </Button>
        </div>
      </CardContent>
    </Card>
  );
};

// ====================================================================
// Card 2: Conta de Indexação (IMAP Recepção) — system_webmail
// Copied from IntegrationsConfigSection Bloco C
// ====================================================================

const IndexationImapCard = () => {
  const { token } = useAuth();
  const [systemWebmail, setSystemWebmail] = useState({
    imap_host: "",
    imap_port: "993",
    email_user: "",
    app_password: "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const res = await fetch(`${API_URL}/api/system-config`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const response = await res.json();
          const data = response.config || response;
          if (data.system_webmail) {
            setSystemWebmail((prev) => ({
              ...prev,
              imap_host: data.system_webmail.imap_host || "",
              imap_port: String(data.system_webmail.imap_port || 993),
              email_user: data.system_webmail.email_user || "",
              app_password: data.system_webmail.app_password ? "••••••••" : "",
            }));
          }
        }
      } catch (error) {
        console.error("Error fetching system_webmail config:", error);
      } finally {
        setLoading(false);
      }
    };
    fetchConfig();
  }, [token]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = { ...systemWebmail, imap_port: parseInt(systemWebmail.imap_port) || 993 };
      const res = await fetch(`${API_URL}/api/system-config/system_webmail`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        toast.success("Configuração IMAP guardada com sucesso");
      } else {
        const data = await res.json();
        toast.error(data.detail || "Erro ao guardar configuração IMAP");
      }
    } catch (error) {
      toast.error("Erro ao guardar configuração IMAP");
    } finally {
      setSaving(false);
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
    <Card>
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-amber-100 dark:bg-amber-900/30">
              <Globe className="h-5 w-5 text-amber-700 dark:text-amber-400" />
            </div>
            <div>
              <CardTitle className="text-base">Conta de Indexação (IMAP Recepção)</CardTitle>
              <CardDescription className="text-xs mt-0.5">
                Conta IMAP para sincronização e receção de emails do departamento de indexação (apenas receção, sem envio).
              </CardDescription>
            </div>
          </div>
          {systemWebmail.imap_host && (
            <Badge variant="secondary" className="text-xs bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
              Configurado
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="wm_imap_host">IMAP Host</Label>
            <Input id="wm_imap_host" placeholder="imap.gmail.com" value={systemWebmail.imap_host}
              onChange={(e) => setSystemWebmail((p) => ({ ...p, imap_host: e.target.value }))} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="wm_imap_port">IMAP Port</Label>
            <Input id="wm_imap_port" type="number" placeholder="993" value={systemWebmail.imap_port}
              onChange={(e) => setSystemWebmail((p) => ({ ...p, imap_port: e.target.value }))} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="wm_email">Email / User</Label>
            <Input id="wm_email" placeholder="indexacao@empresa.pt" value={systemWebmail.email_user}
              onChange={(e) => setSystemWebmail((p) => ({ ...p, email_user: e.target.value }))} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="wm_pass">App Password</Label>
            <Input id="wm_pass" type="password" placeholder="••••••••" value={systemWebmail.app_password}
              onChange={(e) => setSystemWebmail((p) => ({ ...p, app_password: e.target.value }))} />
            <p className="text-xs text-muted-foreground">Password de aplicação (não a password da conta)</p>
          </div>
        </div>
        <div className="flex items-center gap-3 pt-2">
          <Button onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
            Guardar
          </Button>
        </div>
      </CardContent>
    </Card>
  );
};

// ====================================================================
// Card 3: Contas Partilhadas por Departamento (Google OAuth)
// Copied from SharedEmailConfigSection
// ====================================================================

const SHARED_EMAIL_ROLES = [
  { role: "indexacao", label: "Indexação", description: "Email partilhado do departamento de indexação" },
  { role: "suporte", label: "Suporte", description: "Email partilhado do departamento de suporte" },
  { role: "comercial", label: "Comercial", description: "Email partilhado do departamento comercial" },
  { role: "admin", label: "Administração", description: "Email partilhado da administração" },
];

const SharedEmailCard = () => {
  const { token } = useAuth();
  const [configs, setConfigs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [authenticating, setAuthenticating] = useState(null);
  const [syncing, setSyncing] = useState(null);

  const fetchConfigs = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/shared-email`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setConfigs(data.configs || []);
      }
    } catch (error) {
      console.error("Erro ao carregar configs de email partilhado:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfigs();
  }, []);

  // Escutar postMessage do popup OAuth
  useEffect(() => {
    const handleMessage = (event) => {
      if (event.data?.type === "shared_google_oauth_success") {
        toast.success(`Google OAuth conectado para ${event.data.email}`);
        setAuthenticating(null);
        fetchConfigs();
      }
      if (event.data?.type === "shared_google_oauth_error") {
        toast.error(`Autenticação cancelada: ${event.data.error}`);
        setAuthenticating(null);
      }
    };
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, []);

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
        toast.error(data.detail || "Erro ao iniciar autenticação Google");
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
    } catch (error) {
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
        toast.success(`Sincronização iniciada: ${data.new_emails || 0} novos emails`);
        fetchConfigs();
      } else {
        const data = await res.json();
        toast.error(data.detail || "Erro ao sincronizar");
      }
    } catch (error) {
      toast.error("Erro ao sincronizar");
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
    } catch (error) {
      toast.error("Erro ao desconectar");
    }
  };

  const getConfig = (role) => configs.find((c) => c.role === role);

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
    <Card>
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
      <CardContent className="space-y-4">
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
                        <span>Conectado: {new Date(cfg.oauth_connected_at).toLocaleDateString("pt-PT")}</span>
                      )}
                      {cfg.last_sync_at && (
                        <span>Último sync: {new Date(cfg.last_sync_at).toLocaleDateString("pt-PT")}</span>
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
                      <Button variant="outline" size="sm" onClick={() => handleSync(role)} disabled={isSyncingRole} className="gap-2">
                        {isSyncingRole ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                        Sincronizar Agora
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => handleGoogleAuth(role)} disabled={isAuth} className="gap-2">
                        {isAuth ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
                        Reautenticar / Trocar Conta
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => handleDisconnect(role)} className="gap-2 text-destructive hover:text-destructive ml-auto">
                        <XCircle className="h-4 w-4" />
                        Desconectar
                      </Button>
                    </>
                  ) : (
                    <Button onClick={() => handleGoogleAuth(role)} disabled={isAuth} className="gap-2 bg-emerald-600 hover:bg-emerald-700">
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
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
};

// ====================================================================
// Card 4: Configuração de Email por Empresa
// Copied from CompanyEmailConfigSection
// ====================================================================

const CompanyEmailCard = () => {
  const { token } = useAuth();
  const [configs, setConfigs] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editingCompany, setEditingCompany] = useState(null);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [selectedCompany, setSelectedCompany] = useState("");
  const [formData, setFormData] = useState({
    company_name: "",
    imap_server: "",
    imap_port: 993,
    smtp_server: "",
    smtp_port: 465,
    require_ssl: true,
  });
  const [deletingCompany, setDeletingCompany] = useState(null);

  const fetchConfigs = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/company-email-configs`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setConfigs(data.configs || []);
      }
    } catch (error) {
      console.error("Erro ao carregar configs:", error);
    } finally {
      setLoading(false);
    }
  };

  const fetchCompanies = async () => {
    try {
      const res = await fetch(`${API_URL}/api/admin/company-email-configs/available-companies`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setCompanies(data.companies || []);
      }
    } catch (error) {
      console.error("Erro ao carregar empresas:", error);
    }
  };

  useEffect(() => {
    fetchConfigs();
    fetchCompanies();
  }, []);

  const handleEdit = (config) => {
    setEditingCompany(config.company_name);
    setFormData({
      company_name: config.company_name,
      imap_server: config.imap_server || "",
      imap_port: config.imap_port || 993,
      smtp_server: config.smtp_server || "",
      smtp_port: config.smtp_port || 465,
      require_ssl: config.require_ssl !== false,
    });
  };

  const handleCreate = () => {
    if (!selectedCompany) {
      toast.error("Selecione uma empresa");
      return;
    }
    setFormData({
      company_name: selectedCompany,
      imap_server: "",
      imap_port: 993,
      smtp_server: "",
      smtp_port: 465,
      require_ssl: true,
    });
    setShowCreateDialog(true);
  };

  const handleSave = async () => {
    if (!formData.imap_server || !formData.smtp_server) {
      toast.error("Preencha os servidores IMAP e SMTP");
      return;
    }
    setSaving(true);
    try {
      const isUpdate = !!editingCompany;
      const method = isUpdate ? "PUT" : "POST";
      const url = isUpdate
        ? `${API_URL}/api/admin/company-email-configs/${encodeURIComponent(editingCompany)}`
        : `${API_URL}/api/admin/company-email-configs`;

      const res = await fetch(url, {
        method,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(formData),
      });

      if (res.ok) {
        toast.success(isUpdate ? "Configuração atualizada" : "Configuração criada");
        setEditingCompany(null);
        setShowCreateDialog(false);
        setSelectedCompany("");
        fetchConfigs();
        fetchCompanies();
      } else {
        const data = await res.json();
        toast.error(data.detail || "Erro ao guardar");
      }
    } catch (error) {
      toast.error("Erro de conexão");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (companyName) => {
    if (!window.confirm(`Remover a configuração de email para "${companyName}"?`)) return;
    setDeletingCompany(companyName);
    try {
      const res = await fetch(
        `${API_URL}/api/admin/company-email-configs/${encodeURIComponent(companyName)}`,
        {
          method: "DELETE",
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      if (res.ok) {
        toast.success("Configuração removida");
        fetchConfigs();
        fetchCompanies();
      } else {
        toast.error("Erro ao remover");
      }
    } catch (error) {
      toast.error("Erro de conexão");
    } finally {
      setDeletingCompany(null);
    }
  };

  const companiesWithoutConfig = companies.filter((c) => !c.has_email_config);

  return (
    <Card>
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-indigo-100 dark:bg-indigo-900/30">
              <Building className="h-5 w-5 text-indigo-700 dark:text-indigo-400" />
            </div>
            <div>
              <CardTitle className="text-base">Configuração de Email por Empresa</CardTitle>
              <CardDescription className="text-xs mt-0.5">
                Configuração padrão de IMAP/SMTP por empresa (usada como fallback para emails pessoais dos colaboradores)
              </CardDescription>
            </div>
          </div>
          {configs.length > 0 && (
            <Badge variant="secondary" className="text-xs bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
              {configs.length} {configs.length === 1 ? "empresa" : "empresas"}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Info box about inheritance */}
        <div className="flex items-start gap-3 p-3 bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800 rounded-lg">
          <Info className="h-4 w-4 text-blue-500 mt-0.5 shrink-0" />
          <div className="text-blue-800 dark:text-blue-300 text-sm">
            <p className="font-medium">Caminho da Herança</p>
            <ol className="list-decimal list-inside mt-1 space-y-0.5 text-blue-700 dark:text-blue-400">
              <li><strong>User Config</strong> — Configuração individual do utilizador</li>
              <li><strong>Company Config</strong> — Servidores padrão da empresa (esta secção)</li>
              <li><strong>System Config</strong> — Configuração global do sistema (fallback)</li>
            </ol>
            <p className="mt-2 text-blue-700 dark:text-blue-400 text-xs">
              A password e o email do utilizador são sempre individuais. Apenas os servidores (IMAP/SMTP) são herdados.
            </p>
          </div>
        </div>

        {/* Create new */}
        {companiesWithoutConfig.length > 0 && !showCreateDialog && (
          <div className="flex items-center gap-3">
            <Select value={selectedCompany} onValueChange={setSelectedCompany}>
              <SelectTrigger className="w-64">
                <SelectValue placeholder="Selecione uma empresa..." />
              </SelectTrigger>
              <SelectContent>
                {companiesWithoutConfig.map((c) => (
                  <SelectItem key={c.company_name} value={c.company_name}>
                    {c.company_name} ({c.total_users} utilizadores)
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button onClick={handleCreate} disabled={!selectedCompany} className="gap-2">
              <Plus className="h-4 w-4" />
              Adicionar Configuração
            </Button>
          </div>
        )}

        {/* Create/Edit Form */}
        {(showCreateDialog || editingCompany) && (
          <div className="border rounded-lg p-4 space-y-4 bg-muted/30">
            <div className="flex items-center justify-between">
              <h4 className="font-medium">
                {editingCompany ? `Editar: ${editingCompany}` : "Nova Configuração"}
              </h4>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => { setEditingCompany(null); setShowCreateDialog(false); }}>
                  Cancelar
                </Button>
                <Button size="sm" onClick={handleSave} disabled={saving} className="gap-2">
                  {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                  Guardar
                </Button>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Empresa</Label>
                <Input value={formData.company_name} disabled />
              </div>
              <div className="space-y-2" />
              <div className="space-y-2">
                <Label htmlFor="ce_imap_server">Servidor IMAP</Label>
                <Input
                  id="ce_imap_server"
                  value={formData.imap_server}
                  onChange={(e) => setFormData({ ...formData, imap_server: e.target.value })}
                  placeholder="imap.empresa.pt"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ce_imap_port">Porta IMAP</Label>
                <Input
                  id="ce_imap_port"
                  type="number"
                  value={formData.imap_port}
                  onChange={(e) => setFormData({ ...formData, imap_port: parseInt(e.target.value) || 993 })}
                  placeholder="993"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ce_smtp_server">Servidor SMTP</Label>
                <Input
                  id="ce_smtp_server"
                  value={formData.smtp_server}
                  onChange={(e) => setFormData({ ...formData, smtp_server: e.target.value })}
                  placeholder="smtp.empresa.pt"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ce_smtp_port">Porta SMTP</Label>
                <Input
                  id="ce_smtp_port"
                  type="number"
                  value={formData.smtp_port}
                  onChange={(e) => setFormData({ ...formData, smtp_port: parseInt(e.target.value) || 465 })}
                  placeholder="465"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ce_require_ssl">Requer SSL/TLS</Label>
                <div className="flex items-center gap-3 h-9">
                  <Switch
                    id="ce_require_ssl"
                    checked={formData.require_ssl}
                    onCheckedChange={(v) => setFormData({ ...formData, require_ssl: v })}
                  />
                  <span className="text-sm text-muted-foreground">
                    {formData.require_ssl ? "Ativado" : "Desativado"}
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Existing configs list */}
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : configs.length === 0 ? (
          <p className="text-center text-muted-foreground py-6">
            Nenhuma empresa com configuração de email definida.
          </p>
        ) : (
          <div className="space-y-3">
            {configs.map((cfg) => (
              <div key={cfg.id} className="border rounded-lg p-4 hover:bg-muted/30 transition-colors">
                <div className="flex items-start justify-between">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <Building2 className="h-4 w-4 text-muted-foreground" />
                      <span className="font-medium">{cfg.company_name}</span>
                      <Badge variant="secondary" className="text-xs">
                        {cfg.total_users} {cfg.total_users === 1 ? "utilizador" : "utilizadores"}
                      </Badge>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm text-muted-foreground">
                      <div>
                        <span className="text-xs uppercase tracking-wider">IMAP</span>
                        <p>{cfg.imap_server}:{cfg.imap_port}</p>
                      </div>
                      <div>
                        <span className="text-xs uppercase tracking-wider">SMTP</span>
                        <p>{cfg.smtp_server}:{cfg.smtp_port}</p>
                      </div>
                      <div>
                        <span className="text-xs uppercase tracking-wider">SSL/TLS</span>
                        <p className="flex items-center gap-1">
                          <ShieldCheck className={`h-3 w-3 ${cfg.require_ssl !== false ? "text-green-500" : "text-muted-foreground"}`} />
                          {cfg.require_ssl !== false ? "Ativado" : "Desativado"}
                        </p>
                      </div>
                      <div>
                        <span className="text-xs uppercase tracking-wider">Utilizadores</span>
                        <p>{cfg.total_users}</p>
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="icon" onClick={() => handleEdit(cfg)} title="Editar">
                      <FileEdit className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleDelete(cfg.company_name)}
                      disabled={deletingCompany === cfg.company_name}
                      className="text-destructive hover:text-destructive"
                      title="Eliminar"
                    >
                      {deletingCompany === cfg.company_name ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Companies without config summary */}
        {companiesWithoutConfig.length > 0 && (
          <div className="mt-4 pt-4 border-t">
            <p className="text-xs text-muted-foreground mb-2">
              Empresas sem configuração (utilizadores usarão System Config como fallback):
            </p>
            <div className="flex flex-wrap gap-2">
              {companiesWithoutConfig.map((c) => (
                <Badge key={c.company_name} variant="outline" className="text-xs">
                  {c.company_name} ({c.total_users})
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

// ====================================================================
// Main Page Component
// ====================================================================

const EmailAccountsPage = ({ embedded = false }) => {
  const { token, user } = useAuth();
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
      <div className="space-y-6">
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

          {/* Card 4: Configuração de Email por Empresa */}
          <div className="xl:col-span-2">
            <CompanyEmailCard />
          </div>
        </div>
      </div>
  );
};

export default EmailAccountsPage;
