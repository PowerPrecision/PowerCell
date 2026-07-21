/**
 * SystemConfigPage — Página de configurações do sistema, exclusiva para Admin/CEO.
 *
 * PORQUÊ: O PowerCell tem múltiplas integrações externas (AWS S3, OpenAI, Gmail,
 * envio de emails) que precisam de configuração centralizada. Esta página
 * permite ao administrador configurar credenciais, activar/desactivar funcionalidades
 * e executar tarefas de manutenção sem aceder directamente ao backend ou a variáveis
 * de ambiente. Inclui ferramentas de diagnóstico (reparação de índices, limpeza de logs)
 * e sincronização entre ambientes de produção e desenvolvimento.
 *
 * DECISÕES ARQUITECTURAIS:
 * - Configuração dinâmica: os campos são definidos pelo backend via /api/system-config,
 * permitindo adicionar novas secções sem alterar o frontend.
 * - Secção de manutenção incluída como tab separada com ferramentas de DB, migrações
 * e mapeamento S3.
 * - DocumentRecipientsManager integrado como tab para gestão visual de destinatários
 * de documentação bancária.
 * - Protecção de passwords: campos do tipo "password" são mascarados com reveal sob
 * demanda (endpoint /reveal-secrets).
 * - Acesso restrito a roles admin e ceo — redireciona com mensagem clara para outros.
 *
 * @context {AuthContext} — Consome token, user para verificar permissões de acesso
 *
 * @route /admin/config — Página acessível apenas a admin/ceo
 *
 * @example
 * <SystemConfigPage />
 * // Acesso via rota protegida: /admin/config?tab=storage
 */
import React, { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Badge } from "../components/ui/badge";
import { Switch } from "../components/ui/switch";
import { Textarea } from "../components/ui/textarea";
// Tabs removed — replaced with vertical master-detail layout
import DocumentRecipientsManager from "../components/DocumentRecipientsManager";
import MaintenanceSection from "./systemConfig/MaintenanceSection";
import RGPDTab from "./systemConfig/RGPDTab";
import IntegrationsConfigSection from "./systemConfig/IntegrationsConfigSection";
import SystemEmailsSection from "./systemConfig/SystemEmailsSection";
import RichTextEditor from "../components/ui/RichTextEditor";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
import { hasAnyRole, hasRole } from "../utils/roleUtils";
import { safeString } from "../utils/safeString";
import { formatDate, formatDateTime } from "../lib/utils";
import { toast } from "sonner";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import { getSystemChangelogs, generateChangelogAI, diagnoseChangelog, createAnnouncement } from "../services/api";
import { sanitizeHtml } from "../utils/sanitize";
import {
  Settings,
  Cloud,
  Mail,
  Sparkles,
  Building,
  Building2,
  Save,
  Loader2,
  CheckCircle,
  XCircle,
  RefreshCw,
  TestTube,
  Eye,
  EyeOff,
  Wrench,
  Database,
  AlertTriangle,
  Trash2,
  Users,
  FolderOpen,
  Link,
  UserCheck,
  FileEdit,
  FileSignature,
  History,
  Info,
  RotateCcw,
  Plus,
  ShieldCheck,
  MailCheck,
  Plug,
  HardDrive,
  Globe,
  Zap,
  Pencil,
  MessageSquare,
  X,
  Megaphone,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Ícones por secção
const SECTION_ICONS = {
  storage: Cloud,
  email: Mail,
  ai: Sparkles,
  settings: Building,
  maintenance: Wrench,
  document_recipients: Building2,
  auto_draft: FileEdit,
  rgpd: FileSignature,
  company_email: Building2,
  shared_email: MailCheck,
};

// Componente para campo de configuração
const ConfigFieldInput = ({ field, value, onChange, allValues, sectionName }) => {
  const [showPassword, setShowPassword] = useState(false);
  const [revealedValue, setRevealedValue] = useState(null);
  const [loadingReveal, setLoadingReveal] = useState(false);

  const handleRevealSecret = async () => {
    setLoadingReveal(true);
    try {
      const token = localStorage.getItem("token");
      const res = await fetch(`${API_URL}/api/system-config/reveal-secrets?section=${sectionName}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        const secretVal = data.secrets?.[field.key];
        if (secretVal) {
          setRevealedValue(secretVal);
          setShowPassword(true);
        }
      }
    } catch (err) {
      console.error("Erro ao revelar password:", err);
    } finally {
      setLoadingReveal(false);
    }
  };

  // Reset revealed value when password field value changes
  useEffect(() => {
    if (field.type === "password" && value && value !== "••••••••" && value !== revealedValue) {
      setRevealedValue(null);
    }
  }, [value]);

  // Verificar dependências
  if (field.depends_on) {
    const [depKey, depValue] = Object.entries(field.depends_on)[0];
    const actualValue = allValues[depKey];
    
    // Comparação flexível para lidar com diferentes tipos (boolean/string)
    const matches = 
      actualValue === depValue || 
      String(actualValue) === String(depValue) ||
      (depValue === true && (actualValue === true || actualValue === "true")) ||
      (depValue === false && (actualValue === false || actualValue === "false"));
    
    if (!matches) {
      return null;
    }
  }

  // Ignorar campos de divisor (dividers) - são só para UI
  if (field.key?.startsWith("_divider")) {
    return (
      <div className="pt-6 pb-2 border-t mt-4">
        <h4 className="font-medium text-sm text-muted-foreground">{safeString(field.label)}</h4>
      </div>
    );
  }

  const inputType = field.type === "password" && !showPassword ? "password" : "text";

  switch (field.type) {
    case "select":
      return (
        <div className="space-y-2">
          <Label htmlFor={field.key}>{safeString(field.label)}</Label>
          <Select
            value={value || ""}
            onValueChange={(v) => onChange(field.key, v)}
          >
            <SelectTrigger id={field.key}>
              <SelectValue placeholder="Seleccione..." />
            </SelectTrigger>
            <SelectContent>
              {field.options?.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {field.help_text && (
            <p className="text-xs text-muted-foreground">{safeString(field.help_text)}</p>
          )}
        </div>
      );

    case "boolean":
      return (
        <div className="flex items-center justify-between py-2">
          <div>
            <Label htmlFor={field.key}>{safeString(field.label)}</Label>
            {field.help_text && (
              <p className="text-xs text-muted-foreground">{safeString(field.help_text)}</p>
            )}
          </div>
          <Switch
            id={field.key}
            checked={value || false}
            onCheckedChange={(v) => onChange(field.key, v)}
          />
        </div>
      );

    case "password":
      return (
        <div className="space-y-2">
          <Label htmlFor={field.key}>{safeString(field.label)}</Label>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Input
                id={field.key}
                type={inputType}
                value={showPassword && revealedValue ? revealedValue : (value || "")}
                onChange={(e) => { setRevealedValue(null); onChange(field.key, e.target.value); }}
                placeholder={field.placeholder}
                className="pr-10"
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7 p-0"
                onClick={() => { if (showPassword) { setShowPassword(false); setRevealedValue(null); } else { handleRevealSecret(); } }}
                title={showPassword ? "Ocultar valor" : "Mostrar valor actual"}
              >
                {loadingReveal ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : showPassword ? (
                  <EyeOff className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
          {field.help_text && (
            <p className="text-xs text-muted-foreground">{safeString(field.help_text)}</p>
          )}
        </div>
      );

    case "number":
      return (
        <div className="space-y-2">
          <Label htmlFor={field.key}>{safeString(field.label)}</Label>
          <Input
            id={field.key}
            type="number"
            value={value || ""}
            onChange={(e) => onChange(field.key, parseInt(e.target.value) || "")}
            placeholder={field.placeholder}
          />
          {field.help_text && (
            <p className="text-xs text-muted-foreground">{safeString(field.help_text)}</p>
          )}
        </div>
      );

    case "textarea":
      return (
        <div className="space-y-2">
          <Label htmlFor={field.key}>{safeString(field.label)}</Label>
          <RichTextEditor
            value={value || ""}
            onChange={(val) => onChange(field.key, val)}
            placeholder={field.placeholder}
            advanced
            minHeight={200}
            className="min-h-[200px]"
          />
          {field.help_text && (
            <p className="text-xs text-muted-foreground">{safeString(field.help_text)}</p>
          )}
        </div>
      );

    default:
      return (
        <div className="space-y-2">
          <Label htmlFor={field.key}>{safeString(field.label)}</Label>
          <Input
            id={field.key}
            type="text"
            value={value || ""}
            onChange={(e) => onChange(field.key, e.target.value)}
            placeholder={field.placeholder}
          />
          {field.help_text && (
            <p className="text-xs text-muted-foreground">{safeString(field.help_text)}</p>
          )}
        </div>
      );
  }
};

// Componente para secção de configuração
const ConfigSection = ({ section, sectionKey, config, fields, onSave, onTest }) => {
  const [localConfig, setLocalConfig] = useState(config || {});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    setLocalConfig(config || {});
    setHasChanges(false);
  }, [config]);

  const handleChange = (key, value) => {
    setLocalConfig((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
    setTestResult(null);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(sectionKey, localConfig);
      setHasChanges(false);
      toast.success("Configuração guardada", { id: "config-save" });
    } catch (error) {
      toast.error("Erro ao guardar", { id: "config-save" });
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const result = await onTest(sectionKey);
      setTestResult(result);
      if (result.success) {
        toast.success(result.message);
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      setTestResult({ success: false, message: "Erro ao testar" });
    } finally {
      setTesting(false);
    }
  };

  const Icon = SECTION_ICONS[sectionKey] || Settings;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Icon className="h-5 w-5 text-primary" />
            <div>
              <CardTitle className="text-lg">{safeString(section.title)}</CardTitle>
              <CardDescription>{safeString(section.description)}</CardDescription>
            </div>
          </div>
          {hasChanges && (
            <Badge variant="outline" className="bg-yellow-50 text-yellow-700">
              Alterações por guardar
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {fields.map((field) => (
          <ConfigFieldInput
            key={field.key}
            field={field}
            value={localConfig[field.key]}
            onChange={handleChange}
            allValues={localConfig}
            sectionName={sectionKey}
          />
        ))}

        {/* Test result */}
        {testResult && (
          <div
            className={`flex items-center gap-2 p-3 rounded-lg ${
              testResult.success
                ? "bg-green-50 text-green-700"
                : "bg-red-50 text-red-700"
            }`}
          >
            {testResult.success ? (
              <CheckCircle className="h-4 w-4" />
            ) : (
              <XCircle className="h-4 w-4" />
            )}
            <span className="text-sm">{testResult.message}</span>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2 pt-4 border-t">
          <Button onClick={handleSave} disabled={saving || !hasChanges}>
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <Save className="h-4 w-4 mr-2" />
            )}
            Guardar
          </Button>

          {["storage", "email", "ai"].includes(sectionKey) && (
            <Button variant="outline" onClick={handleTest} disabled={testing}>
              {testing ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <TestTube className="h-4 w-4 mr-2" />
              )}
              Testar Ligação
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

// ====================================================================
// Integrations Config Section (SMTP, Storage, Webmail)
// ====================================================================


// ====================================================================
// Shared Email Config Section (Google OAuth + IMAP per Role)
// ====================================================================

const SHARED_EMAIL_ROLES = [
  { role: "indexacao", label: "Indexação", description: "Email partilhado do departamento de indexação" },
  { role: "suporte", label: "Suporte", description: "Email partilhado do departamento de suporte" },
  { role: "comercial", label: "Comercial", description: "Email partilhado do departamento comercial" },
  { role: "admin", label: "Administração", description: "Email partilhado da administração" },
];

const SharedEmailConfigSection = () => {
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
        toast.error(extractErrorMessage(data.detail, "Erro ao sincronizar"));
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
    <div className="space-y-6">
      <Card>
        <CardContent className="py-3">
          <div className="flex items-start gap-3">
            <Info className="h-4 w-4 text-blue-500 mt-0.5 shrink-0" />
            <div className="text-sm text-muted-foreground">
              <p className="font-medium text-foreground mb-1">Email Partilhado por Departamento</p>
              <p>
                Configure uma conta Google para cada departamento. O sistema sincroniza
                automaticamente os emails recebidos. Os utilizadores do departamento
                podem consultar estes emails nos respetivos processos.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {SHARED_EMAIL_ROLES.map(({ role, label, description }) => {
        const cfg = getConfig(role);
        const isConnected = cfg?.has_google_oauth;
        const isAuth = authenticating === role;
        const isSyncingRole = syncing === role;

        return (
          <Card key={role} className={!isConnected ? "opacity-75" : ""}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <MailCheck className={`h-5 w-5 ${isConnected ? "text-green-600" : "text-muted-foreground"}`} />
                  <div>
                    <CardTitle className="text-lg">{label}</CardTitle>
                    <CardDescription>{description}</CardDescription>
                  </div>
                </div>
                {/* PACOTE BU — Switch toggle para ligar/desligar a conta partilhada */}
                <div className="flex items-center gap-3">
                  <Switch
                    checked={!!isConnected}
                    onCheckedChange={(checked) => {
                      if (checked) {
                        handleGoogleAuth(role);
                      } else {
                        handleDisconnect(role);
                      }
                    }}
                    disabled={isAuth || isSyncingRole}
                    data-testid={`shared-email-toggle-${role}`}
                  />
                  {isConnected ? (
                    <Badge className="bg-green-50 text-green-700 border-green-200">
                      <CheckCircle className="h-3 w-3 mr-1" />
                      Conectado
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-muted-foreground">
                      Não configurado
                    </Badge>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {isConnected && (
                <div className="bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-full bg-green-100 dark:bg-green-900/50 flex items-center justify-center">
                      <CheckCircle className="h-5 w-5 text-green-600" />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-medium text-green-800 dark:text-green-200">
                        ✅ Conta Google associada com sucesso
                      </p>
                      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1 text-xs text-green-700 dark:text-green-300">
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
                  </div>
                </div>
              )}

              {!isConnected && (
                <div className="bg-muted/30 border rounded-lg p-4 space-y-3">
                  <p className="text-sm text-muted-foreground">
                    Nenhuma conta Google associada. Autentique para ativar a sincronização de emails.
                  </p>
                  {cfg?.email_address && (
                    <div className="flex items-center gap-2">
                      <Label className="text-xs text-muted-foreground">Email partilhado:</Label>
                      <Input value={cfg.email_address} disabled className="max-w-xs h-8 text-sm bg-muted" />
                    </div>
                  )}
                </div>
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
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
};

// ====================================================================
// Company Email Config Section
// ====================================================================
const CompanyEmailConfigSection = () => {
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
        toast.error(extractErrorMessage(data.detail, "Erro ao guardar"));
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
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Building2 className="h-5 w-5 text-primary" />
            <div>
              <CardTitle className="text-lg">Configuração de Email por Empresa</CardTitle>
              <CardDescription>
                Defina servidores IMAP/SMTP padrão para cada empresa. Os utilizadores herdam estes servidores automaticamente.
              </CardDescription>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Info box about inheritance */}
        <div className="flex items-start gap-3 p-3 bg-blue-50 border border-blue-200 rounded-lg text-blue-800 text-sm">
          <Info className="h-4 w-4 mt-0.5 shrink-0" />
          <div>
            <p className="font-medium">Caminho da Herança</p>
            <ol className="list-decimal list-inside mt-1 space-y-0.5 text-blue-700">
              <li><strong>User Config</strong> — Configuração individual do utilizador</li>
              <li><strong>Company Config</strong> — Servidores padrão da empresa (esta secção)</li>
              <li><strong>System Config</strong> — Configuração global do sistema (fallback)</li>
            </ol>
            <p className="mt-2 text-blue-700 text-xs">
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
                      <Building className="h-4 w-4 text-muted-foreground" />
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


// =====================================================================
// PORTAL SETTINGS SECTION — Configuração do Portal do Cliente
// =====================================================================

const PortalSettingsSection = ({ token }) => {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [template, setTemplate] = useState("");
  const [preview, setPreview] = useState("");
  const [showPreview, setShowPreview] = useState(false);

  const fetchSettings = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/admin/portal-settings`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setSettings(data);
        setTemplate(data.welcome_message_template || "");
      } else {
        toast.error("Erro ao carregar definições do portal");
      }
    } catch {
      toast.error("Erro de ligação");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/portal-settings`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ welcome_message_template: template }),
      });
      if (res.ok) {
        toast.success("Mensagem de boas-vindas guardada");
        fetchSettings();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(extractErrorMessage(err.detail, "Erro ao guardar"));
      }
    } catch {
      toast.error("Erro de ligação");
    } finally {
      setSaving(false);
    }
  };

  const handlePreview = async () => {
    try {
      const res = await fetch(`${API_URL}/api/admin/portal-settings/preview`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ welcome_message_template: template }),
      });
      if (res.ok) {
        const data = await res.json();
        setPreview(data.preview);
        setShowPreview(true);
      }
    } catch {
      toast.error("Erro ao gerar pré-visualização");
    }
  };

  const handleReset = async () => {
    if (!window.confirm("Repor a mensagem de boas-vindas para o padrão? As alterações serão perdidas.")) return;
    try {
      const res = await fetch(`${API_URL}/api/admin/portal-settings/reset-welcome`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setTemplate(data.welcome_message_template);
        toast.success("Template reposto para o padrão");
      }
    } catch {
      toast.error("Erro ao repor template");
    }
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
          <span className="ml-2 text-muted-foreground">A carregar definições do portal...</span>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <MessageSquare className="h-5 w-5 text-primary" />
            Portal do Cliente
          </CardTitle>
          <CardDescription>
            Configure a mensagem de boas-vindas que os clientes veem no chat do portal.
            Use variáveis para personalizar automaticamente o conteúdo.
          </CardDescription>
        </CardHeader>
      </Card>

      {/* Welcome Message Editor */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Mensagem de Boas-Vindas</CardTitle>
          <CardDescription>
            Esta mensagem aparece como a primeira mensagem no chat do portal do cliente.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Variables Help */}
          <div className="rounded-lg border bg-muted/30 p-4">
            <p className="text-sm font-medium mb-2 flex items-center gap-1.5">
              <Info className="h-4 w-4 text-primary" />
              Variáveis disponíveis
            </p>
            <div className="flex flex-wrap gap-2">
              {settings?.available_variables?.map((v) => (
                <Badge key={v.key} variant="outline" className="font-mono text-xs">
                  {v.key} <span className="font-sans text-muted-foreground ml-1">— {v.description}</span>
                </Badge>
              ))}
            </div>
          </div>

          {/* Template Textarea */}
          <div className="space-y-2">
            <Label htmlFor="welcome-template">Template da mensagem</Label>
            <Textarea
              id="welcome-template"
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
              rows={14}
              className="font-mono text-sm leading-relaxed resize-y"
              placeholder="Escreva a mensagem de boas-vindas..."
            />
            <p className="text-xs text-muted-foreground">
              {template.length} caracteres
              {template.length > 2000 && " — recomendamos mensagens com menos de 2000 caracteres"}
            </p>
          </div>

          {/* Actions */}
          <div className="flex flex-wrap gap-2 pt-2">
            <Button onClick={handleSave} disabled={saving || !template.trim()} className="gap-2">
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              Guardar
            </Button>
            <Button variant="outline" onClick={handlePreview} disabled={!template.trim()} className="gap-2">
              <Eye className="h-4 w-4" />
              Pré-visualizar
            </Button>
            <Button variant="outline" onClick={handleReset} className="gap-2">
              <RotateCcw className="h-4 w-4" />
              Repor padrão
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Preview Dialog */}
      <Dialog open={showPreview} onOpenChange={setShowPreview}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Eye className="h-5 w-5 text-primary" />
              Pré-visualização
            </DialogTitle>
            <DialogDescription>
              Como a mensagem vai aparecer para o cliente "João Silva" com o consultor "Ana Rodrigues"
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-xl border bg-gray-50 p-4 max-h-80 overflow-y-auto">
            <div className="flex justify-start">
              <div className="max-w-[85%] rounded-2xl px-4 py-2.5 bg-white border border-gray-200 shadow-sm">
                <p className="text-xs font-semibold text-gray-600 mb-0.5">PowerCell</p>
                <p className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">{preview}</p>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowPreview(false)}>Fechar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Last updated */}
      {settings?.updated_at && (
        <p className="text-xs text-muted-foreground text-right">
          Última atualização: {formatDateTime(settings.updated_at)}
        </p>
      )}
    </div>
  );
};


// =====================================================================
// PACOTE G — SECÇÃO: Documentos Obrigatórios (mandatory_documents)
// Permite ao CEO/Diretor gerir a checklist de documentos que são pedidos
// automaticamente a cada novo processo (pre_registo ou criação interna).
// =====================================================================
const MandatoryDocumentsSection = ({ token }) => {
  const [enabled, setEnabled] = useState(true);
  const [documents, setDocuments] = useState([]);
  const [newName, setNewName] = useState("");
  const [newCategory, setNewCategory] = useState("outros");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const CATEGORIES = [
    { value: "identificacao", label: "Identificação" },
    { value: "irs", label: "IRS" },
    { value: "recibo_vencimento", label: "Recibo de Vencimento" },
    { value: "comprovativo_morada", label: "Comprovativo de Morada" },
    { value: "extrato_bancario", label: "Extrato Bancário" },
    { value: "mapa_responsabilidades", label: "Mapa de Responsabilidades" },
    { value: "caderneta_predial", label: "Caderneta Predial" },
    { value: "certidao_teor", label: "Certidão de Teor" },
    { value: "outros", label: "Outros" },
  ];

  const fetchConfig = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/system-config`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        // PACOTE CY — fix read path: data.config.mandatory_documents (não data.mandatory_documents)
        const md = (data.config && data.config.mandatory_documents) || data.mandatory_documents || {};
        setEnabled(md.enabled !== false);
        setDocuments(Array.isArray(md.documents) ? md.documents : []);
      } else {
        toast.error("Erro ao carregar documentos obrigatórios");
      }
    } catch {
      toast.error("Erro de ligação");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const handleAdd = () => {
    const name = newName.trim();
    if (!name) {
      toast.error("Indique um nome para o documento");
      return;
    }
    // Evitar duplicados (case-insensitive)
    if (documents.some((d) => (d.name || "").toLowerCase() === name.toLowerCase())) {
      toast.error("Este documento já está na lista");
      return;
    }
    setDocuments([...documents, { name, category: newCategory }]);
    setNewName("");
  };

  const handleRemove = (idx) => {
    setDocuments(documents.filter((_, i) => i !== idx));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/api/system-config/mandatory_documents`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ enabled, documents }),
      });
      if (res.ok) {
        toast.success("Checklist de documentos obrigatórios guardada");
        fetchConfig();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(extractErrorMessage(err.detail, "Erro ao guardar"));
      }
    } catch {
      toast.error("Erro de ligação");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileEdit className="h-5 w-5 text-primary" />
            Documentos Obrigatórios por Defeito
          </CardTitle>
          <CardDescription>
            Lista gerida pelo CEO/Diretor. Quando um processo é criado (via formulário público
            ou criação interna), estes pedidos são gerados automaticamente. Assim que o cliente
            submeter todos, o sistema envia um email de confirmação em nome do intermediário.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between rounded-lg border p-3">
            <div>
              <Label className="font-medium">Ativar checklist automática</Label>
              <p className="text-xs text-muted-foreground mt-0.5">
                Se inativo, novos processos não geram pedidos automáticos.
              </p>
            </div>
            <Switch checked={enabled} onCheckedChange={setEnabled} />
          </div>

          <div className="rounded-lg border p-3 space-y-3">
            <Label className="font-medium">Adicionar documento</Label>
            <div className="flex flex-col sm:flex-row gap-2">
              <Input
                placeholder="Ex: Bilhete de Identidade / Cartão de Cidadão"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleAdd();
                  }
                }}
                className="flex-1"
              />
              <Select value={newCategory} onValueChange={setNewCategory}>
                <SelectTrigger className="w-full sm:w-56">
                  <SelectValue placeholder="Categoria" />
                </SelectTrigger>
                <SelectContent>
                  {CATEGORIES.map((c) => (
                    <SelectItem key={c.value} value={c.value}>
                      {c.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button type="button" onClick={handleAdd} variant="secondary">
                <Plus className="h-4 w-4 mr-1" /> Adicionar
              </Button>
            </div>
          </div>

          {/* PACOTE I — Lista de Etiquetas (Tags): badges com ícone X.
              Layout flex-wrap para os badges fluírem em múltiplas linhas.
              Cada badge mostra o nome do documento + categoria (se não for
              "outros") + botão X para remover. */}
          <div className="flex flex-wrap gap-2 min-h-[3rem] p-3 rounded-lg border bg-muted/30 items-center">
            {documents.length === 0 ? (
              <span className="text-sm text-muted-foreground italic">
                Sem documentos na checklist. Adicione acima para começar.
              </span>
            ) : (
              documents.map((doc, idx) => {
                const cat = CATEGORIES.find((c) => c.value === doc.category);
                const hasCat = doc.category && doc.category !== "outros";
                return (
                  <Badge
                    key={`${doc.name}-${idx}`}
                    variant="secondary"
                    className="pl-3 pr-1 py-1 text-sm gap-1.5"
                  >
                    <span className="truncate max-w-[16rem]">{doc.name}</span>
                    {hasCat && (
                      <Badge variant="outline" className="px-1 py-0 text-[10px] font-normal">
                        {cat?.label || doc.category}
                      </Badge>
                    )}
                    <button
                      type="button"
                      onClick={() => handleRemove(idx)}
                      className="ml-0.5 rounded-full hover:bg-destructive/20 hover:text-destructive p-0.5 transition-colors"
                      aria-label={`Remover ${doc.name}`}
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </Badge>
                );
              })
            )}
          </div>

          <div className="flex items-center justify-between pt-2 border-t">
            <p className="text-xs text-muted-foreground">
              {documents.length} documento{documents.length !== 1 ? "s" : ""} na checklist
            </p>
            <Button onClick={handleSave} disabled={saving}>
              {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
              Guardar Checklist
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};


const SystemConfigPage = ({ embedded = false }) => {
  const { token, user } = useAuth();
  const [searchParams] = useSearchParams();
  const [config, setConfig] = useState(null);
  const [fields, setFields] = useState({});
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState(() => searchParams.get("tab") || "storage");

  // MULTI-EMPRESA: seletor de empresa no topo
  const [selectedCompanyId, setSelectedCompanyId] = useState("default");
  const [availableCompanies, setAvailableCompanies] = useState([]);

  // Carregar lista de empresas disponíveis
  useEffect(() => {
    const fetchCompanies = async () => {
      try {
        const res = await fetch(`${API_URL}/api/system-config/companies`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const data = await res.json();
          setAvailableCompanies(data.companies || []);
        }
      } catch (err) {
        console.error("Erro ao carregar empresas:", err);
      }
    };
    fetchCompanies();
  }, [token]);

  const fetchConfig = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/system-config?company_id=${encodeURIComponent(selectedCompanyId)}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        // Converter arrays para string separada por vírgulas em campos de texto
        if (data.config?.auto_draft?.eligible_doc_types != null) {
          const docTypes = data.config.auto_draft.eligible_doc_types;
          data.config.auto_draft.eligible_doc_types = Array.isArray(docTypes)
            ? docTypes.join(", ")
            : String(docTypes);
        }
        setConfig(data.config);
        setFields(data.fields);
      } else {
        toast.error("Erro ao carregar configurações");
      }
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao carregar configurações");
    } finally {
      setLoading(false);
    }
  }, [token, selectedCompanyId]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  // Recarregar config quando a empresa selecionada mudar
  useEffect(() => {
    if (selectedCompanyId) {
      setLoading(true);
      fetchConfig();
    }
  }, [selectedCompanyId]);

  const handleSave = async (section, data) => {
    // Pré-processar campos especiais
    const processedData = { ...data };
    if (section === "auto_draft" && typeof processedData.eligible_doc_types === "string") {
      const trimmed = processedData.eligible_doc_types.trim();
      if (!trimmed) {
        processedData.eligible_doc_types = [];
      } else {
        // Parsear string separada por vírgulas em array
        processedData.eligible_doc_types = trimmed
          .split(',')
          .map(s => s.trim())
          .filter(Boolean);
      }
    }
    // Pré-processar audit_trail: critical_fields (textarea → lista) e retention_days (string → int)
    if (section === "audit_trail") {
      if (typeof processedData.critical_fields === "string") {
        const trimmed = processedData.critical_fields.trim();
        if (!trimmed) {
          processedData.critical_fields = ["financial_data", "credit_data", "status"];
        } else {
          try {
            const parsed = JSON.parse(trimmed);
            processedData.critical_fields = Array.isArray(parsed) ? parsed : ["financial_data", "credit_data", "status"];
          } catch {
            processedData.critical_fields = ["financial_data", "credit_data", "status"];
          }
        }
      }
      if (typeof processedData.retention_days === "string") {
        const val = parseInt(processedData.retention_days, 10);
        processedData.retention_days = isNaN(val) ? 365 : val;
      }
    }

    const response = await fetch(`${API_URL}/api/system-config/${section}?company_id=${encodeURIComponent(selectedCompanyId)}`, {
      method: "PATCH",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(processedData),
    });

    if (!response.ok) {
      throw new Error("Erro ao guardar");
    }

    // Recarregar config
    await fetchConfig();
  };

  const handleTest = async (service) => {
    const response = await fetch(
      `${API_URL}/api/system-config/test-connection/${service}`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      }
    );

    return await response.json();
  };

  if (loading) {
    const loadingContent = (
      <div className="space-y-6">
        <div className="h-7 w-64 bg-muted animate-pulse rounded" />
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1,2,3,4,5,6].map(i => <div key={i} className="h-28 bg-muted animate-pulse rounded-lg" />)}
        </div>
      </div>
    );
    return embedded ? loadingContent : <DashboardLayout>{loadingContent}</DashboardLayout>;
  }
  if (!hasAnyRole(user, ["admin", "ceo"])) {
    const accessDeniedContent = (
      <div className="text-center py-12">
        <XCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
        <h2 className="text-xl font-semibold">Acesso Restrito</h2>
        <p className="text-muted-foreground">
          Apenas administradores podem aceder às configurações do sistema.
        </p>
      </div>
    );
    return embedded ? accessDeniedContent : <DashboardLayout>{accessDeniedContent}</DashboardLayout>;
  }

  const sections = Object.keys(fields).filter(key => key !== "email");


  const pageContent = (
    <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Settings className="h-6 w-6" />
              Configurações do Sistema
            </h1>
            <p className="text-muted-foreground">
              Configure as integrações e definições da aplicação
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* MULTI-EMPRESA: Seletor de Empresa */}
            {availableCompanies.length > 0 && (
              <div className="flex items-center gap-2">
                <Building2 className="h-4 w-4 text-muted-foreground shrink-0" />
                <Select
                  value={selectedCompanyId}
                  onValueChange={(v) => {
                    setSelectedCompanyId(v);
                    setActiveTab("settings"); // Reset to settings when company changes
                  }}
                >
                  <SelectTrigger className="w-56">
                    <SelectValue placeholder="Selecionar empresa..." />
                  </SelectTrigger>
                  <SelectContent>
                    {availableCompanies.map((c) => (
                      <SelectItem key={c.company_id} value={c.company_id}>
                        {c.company_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <Button variant="outline" onClick={fetchConfig}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Recarregar
            </Button>
          </div>
        </div>

        {/* Vertical Master-Detail Layout */}
        <div className="flex flex-col lg:flex-row gap-6">
          {/* ─── Left: Sidebar Navigation (Desktop) / Dropdown+Chips (Mobile) ─── */}
          <aside className="w-full lg:w-64 xl:w-72 shrink-0">
            {/* Desktop: Vertical sidebar */}
            <div className="hidden lg:block sticky top-20">
              <Card className="py-2">
                <CardContent className="p-2">
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider px-2 mb-2">Categorias</p>
                  <nav className="space-y-1">
                    {sections.map((key) => {
                      const Icon = SECTION_ICONS[key] || Settings;
                      const isActive = activeTab === key;
                      return (
                        <button
                          key={key}
                          type="button"
                          onClick={() => setActiveTab(key)}
                          className={`w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-all ${
                            isActive
                              ? "bg-primary/10 text-primary font-medium"
                              : "text-muted-foreground hover:bg-muted hover:text-foreground"
                          }`}
                        >
                          <Icon className={`h-4 w-4 shrink-0 ${isActive ? "text-primary" : ""}`} />
                          <span className="truncate">{fields[key]?.title?.split(" ")[0] || key}</span>
                          {isActive && <div className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />}
                        </button>
                      );
                    })}
                    <div className="my-1.5 border-t border-border" />
                    <button
                      type="button"
                      onClick={() => setActiveTab("rgpd")}
                      className={`w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-all ${
                        activeTab === "rgpd"
                          ? "bg-primary/10 text-primary font-medium"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground"
                      }`}
                    >
                      <FileSignature className={`h-4 w-4 shrink-0 ${activeTab === "rgpd" ? "text-primary" : ""}`} />
                      <span className="truncate">RGPD</span>
                      {activeTab === "rgpd" && <div className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />}
                    </button>
                    {/* Nota: "Integrações" e "Emails Sistema" foram movidos para o tab Comunicações no Painel de Administração */}
                    <button
                      type="button"
                      onClick={() => setActiveTab("maintenance")}
                      className={`w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-all ${
                        activeTab === "maintenance"
                          ? "bg-primary/10 text-primary font-medium"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground"
                      }`}
                    >
                      <Wrench className={`h-4 w-4 shrink-0 ${activeTab === "maintenance" ? "text-primary" : ""}`} />
                      <span className="truncate">Manutenção</span>
                      {activeTab === "maintenance" && <div className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />}
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveTab("portal")}
                      className={`w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-all ${
                        activeTab === "portal"
                          ? "bg-primary/10 text-primary font-medium"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground"
                      }`}
                    >
                      <MessageSquare className={`h-4 w-4 shrink-0 ${activeTab === "portal" ? "text-primary" : ""}`} />
                      <span className="truncate">Portal</span>
                      {activeTab === "portal" && <div className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />}
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveTab("mandatory_documents")}
                      className={`w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-all ${
                        activeTab === "mandatory_documents"
                          ? "bg-primary/10 text-primary font-medium"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground"
                      }`}
                    >
                      <FileEdit className={`h-4 w-4 shrink-0 ${activeTab === "mandatory_documents" ? "text-primary" : ""}`} />
                      <span className="truncate">Docs Obrigatórios</span>
                      {activeTab === "mandatory_documents" && <div className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />}
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveTab("changelog")}
                      className={`w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-all ${
                        activeTab === "changelog"
                          ? "bg-primary/10 text-primary font-medium"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground"
                      }`}
                    >
                      <Megaphone className={`h-4 w-4 shrink-0 ${activeTab === "changelog" ? "text-primary" : ""}`} />
                      <span className="truncate">Atualizações</span>
                      {activeTab === "changelog" && <div className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />}
                    </button>
                  </nav>
                </CardContent>
              </Card>
              <p className="text-xs text-muted-foreground/60 px-1 mt-2">Cada categoria guarda as suas definições independentemente.</p>
            </div>

            {/* Mobile: Dropdown + Chips */}
            <div className="lg:hidden space-y-3">
              <Select value={activeTab} onValueChange={setActiveTab}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Selecionar categoria" />
                </SelectTrigger>
                <SelectContent>
                  {sections.map((key) => {
                    const Icon = SECTION_ICONS[key] || Settings;
                    return (
                      <SelectItem key={key} value={key}>
                        <span className="flex items-center gap-2">
                          <Icon className="h-4 w-4" />
                          {fields[key]?.title?.split(" ")[0] || key}
                        </span>
                      </SelectItem>
                    );
                  })}
                  <SelectItem value="rgpd">
                    <span className="flex items-center gap-2">
                      <FileSignature className="h-4 w-4" />
                      RGPD
                    </span>
                  </SelectItem>
                  {/* Nota: Integrações e Emails Sistema movidos para Comunicações */}
                  <SelectItem value="maintenance">
                    <span className="flex items-center gap-2">
                      <Wrench className="h-4 w-4" />
                      Manutenção
                    </span>
                  </SelectItem>
                  <SelectItem value="portal">
                    <span className="flex items-center gap-2">
                      <MessageSquare className="h-4 w-4" />
                      Portal
                    </span>
                  </SelectItem>
                  <SelectItem value="mandatory_documents">
                    <span className="flex items-center gap-2">
                      <FileEdit className="h-4 w-4" />
                      Docs Obrigatórios
                    </span>
                  </SelectItem>
                  <SelectItem value="changelog">
                    <span className="flex items-center gap-2">
                      <Megaphone className="h-4 w-4" />
                      Atualizações
                    </span>
                  </SelectItem>
                </SelectContent>
              </Select>
              {/* Horizontal scrollable chips for quick access */}
              <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1" style={{scrollbarWidth: "none", msOverflowStyle: "none"}}>
                {sections.map((key) => {
                  const Icon = SECTION_ICONS[key] || Settings;
                  const isActive = activeTab === key;
                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setActiveTab(key)}
                      className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium whitespace-nowrap transition-all shrink-0 ${
                        isActive
                          ? "border-primary bg-primary/10 text-primary"
                          : "border-muted text-muted-foreground hover:border-muted-foreground/50"
                      }`}
                    >
                      <Icon className="h-3.5 w-3.5" />
                      {fields[key]?.title?.split(" ")[0] || key}
                    </button>
                  );
                })}
                {["rgpd", "maintenance", "portal", "mandatory_documents", "changelog"].map((key) => {
                  const Icon = key === "rgpd" ? FileSignature : key === "portal" ? MessageSquare : key === "mandatory_documents" ? FileEdit : key === "changelog" ? Megaphone : Wrench;
                  const isActive = activeTab === key;
                  const label = key === "rgpd" ? "RGPD" : key === "portal" ? "Portal" : key === "mandatory_documents" ? "Docs Obrigatórios" : key === "changelog" ? "Atualizações" : "Manutenção";
                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setActiveTab(key)}
                      className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium whitespace-nowrap transition-all shrink-0 ${
                        isActive
                          ? "border-primary bg-primary/10 text-primary"
                          : "border-muted text-muted-foreground hover:border-muted-foreground/50"
                      }`}
                    >
                      <Icon className="h-3.5 w-3.5" />
                      {label}
                    </button>
                  );
                })}
              </div>
            </div>
          </aside>

          {/* ─── Right: Content Area ─── */}
          <main className="min-w-0 flex-1">
            {activeTab === "document_recipients" && <DocumentRecipientsManager token={token} user={user} />}
            {activeTab === "integrations" && <IntegrationsConfigSection />}
            {activeTab === "system_emails" && <SystemEmailsSection token={token} />}
            {activeTab === "portal" && <PortalSettingsSection token={token} />}
            {activeTab === "mandatory_documents" && <MandatoryDocumentsSection token={token} />}
            {activeTab !== "document_recipients" && activeTab !== "rgpd" && activeTab !== "maintenance" && activeTab !== "integrations" && activeTab !== "system_emails" && activeTab !== "portal" && activeTab !== "mandatory_documents" && activeTab !== "changelog" && (
              <ConfigSection
                section={fields[activeTab]}
                sectionKey={activeTab}
                config={config?.[activeTab]}
                fields={fields[activeTab]?.fields || []}
                onSave={handleSave}
                onTest={handleTest}
              />
            )}
            {activeTab === "rgpd" && <RGPDTab token={token} user={user} />}
            {activeTab === "maintenance" && <MaintenanceSection token={token} user={user} />}
            {activeTab === "changelog" && <ChangelogSection token={token} />}
          </main>
        </div>
      </div>
  );

  return embedded ? pageContent : <DashboardLayout>{pageContent}</DashboardLayout>;
};

export default SystemConfigPage;

// Named exports para uso no SystemAdminPanel (tab Comunicações)
export { default as IntegrationsConfigSection } from "./systemConfig/IntegrationsConfigSection";
export { default as SystemEmailsSection } from "./systemConfig/SystemEmailsSection";


// ═══════════════════════════════════════════════════════════════
// ChangelogSection — Mural de Atualizações gerado por IA
// ═══════════════════════════════════════════════════════════════

/**
 * Conversor simples de Markdown para HTML (sem dependências externas).
 * O output é posteriormente sanitizado por DOMPurify antes de ser renderizado.
 */
function markdownToHtml(md) {
  if (!md || typeof md !== 'string') return '';
  let html = md
    .replace(/^### (.+)$/gm, '<h3 class="text-sm font-semibold mt-3 mb-1">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-base font-bold mt-4 mb-2">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-lg font-bold mt-4 mb-2">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>')
    .replace(/^[-*] (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
    .replace(/\n\n/g, '</p><p class="mb-2">')
    .replace(/\n/g, '<br/>');
  html = `<p class="mb-2">${html}</p>`;
  html = html.replace(/<p class="mb-2"><\/p>/g, '');
  return html;
}

const ChangelogSection = ({ token }) => {
  const [changelogs, setChangelogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [diagnosing, setDiagnosing] = useState(false);
  const [diagnosticResult, setDiagnosticResult] = useState(null);
  // CORREÇÃO (Pacote AE-fix): default 'worklog' em vez de 'git' porque
  // no Render a pasta .git não está disponível no container de deploy.
  // worklog.md é um ficheiro físico que está sempre presente.
  const [sourceType, setSourceType] = useState("worklog");

  const fetchChangelogs = useCallback(async () => {
    try {
      const res = await getSystemChangelogs(10);
      setChangelogs(res.data || []);
    } catch (err) {
      console.error("Erro ao carregar changelogs:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchChangelogs(); }, [fetchChangelogs]);

  // ── Diagnóstico (Pacote AI): verifica ficheiros + credenciais IA ──
  const handleDiagnose = async () => {
    setDiagnosing(true);
    setDiagnosticResult(null);
    try {
      const res = await diagnoseChangelog();
      setDiagnosticResult(res.data);
      if (res.data?.can_generate) {
        toast.success("Diagnóstico: tudo OK! Pode gerar notas de atualização.");
      } else {
        toast.warning(res.data?.blocking_issue || "Problema detetado — veja o relatório abaixo.");
      }
    } catch (err) {
      toast.error(extractErrorMessage(err, "Erro ao executar diagnóstico"));
    } finally {
      setDiagnosing(false);
    }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const res = await generateChangelogAI({ source_type: sourceType });
      toast.success("Notas de atualização geradas com sucesso!");
      // Adicionar o novo changelog ao início da lista
      if (res.data?.changelog) {
        setChangelogs(prev => [res.data.changelog, ...prev]);
      } else {
        fetchChangelogs(); // Refresh da lista
      }
    } catch (err) {
      toast.error(extractErrorMessage(err, "Erro ao gerar notas de atualização"));
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold">📢 Mural de Atualizações (IA)</h3>
        <p className="text-sm text-muted-foreground mt-1">
          Gere notas de lançamento amigáveis a partir de logs técnicos. A IA transforma o trabalho da equipa em anúncios claros para todos os utilizadores.
        </p>
      </div>

      {/* ── Gerar novo changelog ── */}
      <Card className="border-primary/20">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            Gerar Notas de Atualização
          </CardTitle>
          <CardDescription className="text-xs">
            A IA analisa os commits/changes recentes e redige um anúncio de lançamento amigável
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="flex-1">
              <Label className="text-xs mb-1.5 block">Fonte de dados</Label>
              <Select value={sourceType} onValueChange={setSourceType}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="worklog">Ficheiro worklog.md (recomendado)</SelectItem>
                  <SelectItem value="changelog_file">Ficheiro CHANGELOG.md</SelectItem>
                  <SelectItem value="git">Commits Git (pode falhar no Render)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end gap-2">
              <Button onClick={handleGenerate} disabled={generating} className="gap-2">
                {generating ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    A gerar...
                  </>
                ) : (
                  <>
                    ✨ Gerar Notas de Atualização (IA)
                  </>
                )}
              </Button>
              <Button variant="outline" onClick={handleDiagnose} disabled={diagnosing} className="gap-2" title="Diagnosticar problemas">
                {diagnosing ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    A diagnosticar...
                  </>
                ) : (
                  <>
                    🔍 Diagnosticar
                  </>
                )}
              </Button>
            </div>
          </div>

          {/* ── Resultado do diagnóstico (Pacote AI) ── */}
          {diagnosticResult && (
            <div className={`mt-4 p-4 rounded-lg border ${diagnosticResult.can_generate ? "bg-emerald-50 border-emerald-200" : "bg-amber-50 border-amber-200"}`}>
              <h4 className="text-sm font-semibold mb-2 flex items-center gap-2">
                {diagnosticResult.can_generate ? "✅" : "⚠️"} Relatório de Diagnóstico
              </h4>
              {diagnosticResult.blocking_issue && (
                <p className="text-xs text-amber-700 mb-3 font-medium">{diagnosticResult.blocking_issue}</p>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                {/* Ficheiros */}
                <div className="bg-white/60 p-3 rounded">
                  <p className="font-medium mb-1">Ficheiros de Fonte</p>
                  <p>worklog.md local: {diagnosticResult.checks?.files?.worklog_md_local_exists ? "✅" : "❌"} {diagnosticResult.checks?.files?.worklog_md_local_path || "(não encontrado)"}</p>
                  <p>worklog.md legível: {diagnosticResult.checks?.files?.worklog_md_readable ? "✅" : "❌"}</p>
                  <p>CHANGELOG.md local: {diagnosticResult.checks?.files?.changelog_md_local_exists ? "✅" : "❌"} {diagnosticResult.checks?.files?.changelog_md_local_path || "(não encontrado)"}</p>
                  <p>CHANGELOG.md legível: {diagnosticResult.checks?.files?.changelog_md_readable ? "✅" : "❌"}</p>
                  {diagnosticResult.checks?.files?.worklog_md_sample && (
                    <p className="text-muted-foreground mt-1 truncate">Sample: {diagnosticResult.checks.files.worklog_md_sample}</p>
                  )}
                </div>
                {/* Credenciais IA */}
                <div className="bg-white/60 p-3 rounded">
                  <p className="font-medium mb-1">Credenciais de IA</p>
                  <p>Configuradas: {diagnosticResult.checks?.ai_credentials?.configured ? "✅" : "❌"}</p>
                  <p>Modelo: {diagnosticResult.checks?.ai_credentials?.model || "N/A"}</p>
                  <p>OPENAI_API_KEY env: {diagnosticResult.checks?.ai_credentials?.has_openai_env_key ? "✅" : "❌"}</p>
                  <p>EMERGENT_LLM_KEY env: {diagnosticResult.checks?.ai_credentials?.has_emergent_env_key ? "✅" : "❌"}</p>
                  {diagnosticResult.checks?.ai_credentials?.error && (
                    <p className="text-red-600 mt-1">Erro: {diagnosticResult.checks.ai_credentials.error}</p>
                  )}
                </div>
                {/* Git */}
                <div className="bg-white/60 p-3 rounded">
                  <p className="font-medium mb-1">Git Log</p>
                  <p>Disponível: {diagnosticResult.checks?.git?.available ? "✅" : "❌"}</p>
                  {diagnosticResult.checks?.git?.sample && (
                    <p className="text-muted-foreground mt-1 truncate">Sample: {diagnosticResult.checks.git.sample}</p>
                  )}
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Lista de changelogs ── */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : changelogs.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Megaphone className="h-10 w-10 text-muted-foreground/40 mx-auto mb-3" />
            <p className="text-muted-foreground">Nenhuma atualização publicada ainda.</p>
            <p className="text-xs text-muted-foreground mt-1">Clique no botão acima para gerar a primeira nota de atualização com IA.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {changelogs.map((entry) => (
            <Card key={entry.id} className="overflow-hidden">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Badge variant="outline" className="text-xs px-2 py-0.5">
                      v{safeString(entry.version)}
                    </Badge>
                    {entry.generated_by === "ai" && (
                      <Badge className="text-[10px] bg-primary/10 text-primary border-primary/20" variant="outline">
                        ✨ IA
                      </Badge>
                    )}
                  </CardTitle>
                  <span className="text-xs text-muted-foreground">
                    {formatDateTime(entry.published_at)}
                  </span>
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                <div
                  className="prose prose-sm dark:prose-invert max-w-none text-sm leading-relaxed changelog-content"
                  dangerouslySetInnerHTML={{
                    __html: sanitizeHtml(markdownToHtml(entry.content_markdown))
                  }}
                />
                {/* PACOTE AW: Botão Publicar no Mural da Equipa */}
                <div className="mt-4 pt-3 border-t flex items-center justify-end">
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-1.5 text-primary border-primary/30 hover:bg-primary/5"
                    onClick={async () => {
                      try {
                        await createAnnouncement({
                          content: entry.content_markdown,
                          title: `Notas de Atualização v${safeString(entry.version)}`,
                        });
                        toast.success("Nota publicada no mural da equipa!");
                      } catch (err) {
                        toast.error(extractErrorMessage(err, "Erro ao publicar no mural."));
                      }
                    }}
                  >
                    <Megaphone className="h-3.5 w-3.5" />
                    Publicar no Mural da Equipa
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};
