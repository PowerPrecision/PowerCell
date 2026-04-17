/**
 * SystemConfigPage — Página de configurações do sistema, exclusiva para Admin/CEO.
 *
 * PORQUÊ: O PowerCell tem múltiplas integrações externas (AWS S3, OpenAI, Gmail,
 * Trello, envio de emails) que precisam de configuração centralizada. Esta página
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
import RichTextEditor from "../components/ui/RichTextEditor";
import SmartRichEditor from "../components/ui/SmartRichEditor";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
import { toast } from "sonner";
import {
  Settings,
  Cloud,
  Mail,
  Sparkles,
  Trello,
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
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Ícones por secção
const SECTION_ICONS = {
  storage: Cloud,
  email: Mail,
  ai: Sparkles,
  trello: Trello,
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
        <h4 className="font-medium text-sm text-muted-foreground">{field.label}</h4>
      </div>
    );
  }

  const inputType = field.type === "password" && !showPassword ? "password" : "text";

  switch (field.type) {
    case "select":
      return (
        <div className="space-y-2">
          <Label htmlFor={field.key}>{field.label}</Label>
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
            <p className="text-xs text-muted-foreground">{field.help_text}</p>
          )}
        </div>
      );

    case "boolean":
      return (
        <div className="flex items-center justify-between py-2">
          <div>
            <Label htmlFor={field.key}>{field.label}</Label>
            {field.help_text && (
              <p className="text-xs text-muted-foreground">{field.help_text}</p>
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
          <Label htmlFor={field.key}>{field.label}</Label>
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
            <p className="text-xs text-muted-foreground">{field.help_text}</p>
          )}
        </div>
      );

    case "number":
      return (
        <div className="space-y-2">
          <Label htmlFor={field.key}>{field.label}</Label>
          <Input
            id={field.key}
            type="number"
            value={value || ""}
            onChange={(e) => onChange(field.key, parseInt(e.target.value) || "")}
            placeholder={field.placeholder}
          />
          {field.help_text && (
            <p className="text-xs text-muted-foreground">{field.help_text}</p>
          )}
        </div>
      );

    case "textarea":
      return (
        <div className="space-y-2">
          <Label htmlFor={field.key}>{field.label}</Label>
          <RichTextEditor
            value={value || ""}
            onChange={(val) => onChange(field.key, val)}
            placeholder={field.placeholder}
            advanced
            minHeight={200}
            className="min-h-[200px]"
          />
          {field.help_text && (
            <p className="text-xs text-muted-foreground">{field.help_text}</p>
          )}
        </div>
      );

    default:
      return (
        <div className="space-y-2">
          <Label htmlFor={field.key}>{field.label}</Label>
          <Input
            id={field.key}
            type="text"
            value={value || ""}
            onChange={(e) => onChange(field.key, e.target.value)}
            placeholder={field.placeholder}
          />
          {field.help_text && (
            <p className="text-xs text-muted-foreground">{field.help_text}</p>
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
      toast.success("Configuração guardada");
    } catch (error) {
      toast.error("Erro ao guardar");
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
              <CardTitle className="text-lg">{section.title}</CardTitle>
              <CardDescription>{section.description}</CardDescription>
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

          {["storage", "email", "ai", "trello"].includes(sectionKey) && (
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
        fetchConfigs();
      }
      if (event.data?.type === "shared_google_oauth_error") {
        toast.error(`Autenticação cancelada: ${event.data.error}`);
      }
    };
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, []);

  const handleGoogleAuth = async (role, emailAddress) => {
    setAuthenticating(role);
    try {
      const params = new URLSearchParams({ role });
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
        const poll = setInterval(() => {
          if (popup.closed) {
            clearInterval(poll);
            setAuthenticating(null);
            fetchConfigs();
          }
        }, 500);
        setTimeout(() => { clearInterval(poll); setAuthenticating(null); }, 120000);
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
          <Card key={role}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <MailCheck className={`h-5 w-5 ${isConnected ? "text-green-600" : "text-muted-foreground"}`} />
                  <div>
                    <CardTitle className="text-lg">{label}</CardTitle>
                    <CardDescription>{description}</CardDescription>
                  </div>
                </div>
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

const SystemConfigPage = () => {
  const { token, user } = useAuth();
  const [searchParams] = useSearchParams();
  const [config, setConfig] = useState(null);
  const [fields, setFields] = useState({});
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState(() => searchParams.get("tab") || "storage");

  const fetchConfig = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/system-config`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        // Converter arrays para string em campos textarea
        if (data.config?.auto_draft?.eligible_doc_types) {
          data.config.auto_draft.eligible_doc_types = JSON.stringify(
            data.config.auto_draft.eligible_doc_types,
            null,
            2
          );
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
  }, [token]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const handleSave = async (section, data) => {
    // Pré-processar campos especiais
    const processedData = { ...data };
    if (section === "auto_draft" && typeof processedData.eligible_doc_types === "string") {
      try {
        processedData.eligible_doc_types = JSON.parse(processedData.eligible_doc_types);
      } catch {
        toast.error("Formato inválido em Tipos de Documento Elegíveis (deve ser JSON array)");
        return;
      }
    }

    const response = await fetch(`${API_URL}/api/system-config/${section}`, {
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
    return (
      <DashboardLayout>
        <div className="space-y-6">
          <div className="h-7 w-64 bg-muted animate-pulse rounded" />
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {[1,2,3,4,5,6].map(i => <div key={i} className="h-28 bg-muted animate-pulse rounded-lg" />)}
          </div>
        </div>
      </DashboardLayout>
    );
  }
  if (!["admin", "ceo"].includes(user?.role)) {
    return (
      <DashboardLayout>
        <div className="text-center py-12">
          <XCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
          <h2 className="text-xl font-semibold">Acesso Restrito</h2>
          <p className="text-muted-foreground">
            Apenas administradores podem aceder às configurações do sistema.
          </p>
        </div>
      </DashboardLayout>
    );
  }

  const sections = Object.keys(fields);

  // Componente de Manutenção do Sistema
  const MaintenanceSection = () => {
    const [repairingIndexes, setRepairingIndexes] = useState(false);
    const [cleaningJobs, setCleaningJobs] = useState(false);
    const [cleaningLogs, setCleaningLogs] = useState(false);
    const [indexStats, setIndexStats] = useState(null);

    const repairIndexes = async () => {
      setRepairingIndexes(true);
      try {
        const response = await fetch(`${API_URL}/api/admin/db/indexes/repair`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });
        const data = await response.json();
        if (data.success) {
          const dropped = data.cleanup?.dropped?.length || 0;
          toast.success(`Índices reparados! ${dropped > 0 ? `${dropped} índices antigos removidos.` : "Todos os índices OK."}`);
          // Actualizar stats
          fetchIndexStats();
        } else {
          toast.error("Erro ao reparar índices");
        }
      } catch (error) {
        toast.error("Erro de conexão");
      } finally {
        setRepairingIndexes(false);
      }
    };

    const fetchIndexStats = async () => {
      try {
        const response = await fetch(`${API_URL}/api/admin/db/indexes`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const data = await response.json();
        if (data.success) {
          setIndexStats(data.indexes);
        }
      } catch (error) {
        console.error("Erro ao carregar stats:", error);
      }
    };

    const cleanOldJobs = async () => {
      setCleaningJobs(true);
      try {
        const response = await fetch(`${API_URL}/api/admin/cleanup/jobs?days=7`, {
          method: "DELETE",
          headers: { Authorization: `Bearer ${token}` },
        });
        const data = await response.json();
        if (data.success) {
          toast.success(`${data.deleted_count || 0} jobs antigos removidos`);
        }
      } catch (error) {
        toast.error("Erro ao limpar jobs");
      } finally {
        setCleaningJobs(false);
      }
    };

    const cleanOldLogs = async () => {
      setCleaningLogs(true);
      try {
        const response = await fetch(`${API_URL}/api/admin/cleanup/error-logs?days=30`, {
          method: "DELETE",
          headers: { Authorization: `Bearer ${token}` },
        });
        const data = await response.json();
        if (data.success) {
          toast.success(`${data.deleted_count || 0} logs antigos removidos`);
        }
      } catch (error) {
        toast.error("Erro ao limpar logs");
      } finally {
        setCleaningLogs(false);
      }
    };

    const [migratingProcessNumbers, setMigratingProcessNumbers] = useState(false);
    
    // Estado para mapeamento S3 (Clientes/Processos)
    const [s3MappingData, setS3MappingData] = useState(null);
    const [loadingS3Mapping, setLoadingS3Mapping] = useState(false);
    const [savingS3Mapping, setSavingS3Mapping] = useState(false);
    const [selectedMappings, setSelectedMappings] = useState({});
    const [s3SearchTerm, setS3SearchTerm] = useState("");
    const [showUnmappedOnly, setShowUnmappedOnly] = useState(false);
    const [autoMapping, setAutoMapping] = useState(false);
    const [fixingNames, setFixingNames] = useState(false);
    
    // Estado para Sincronização Prod → Dev
    const [syncing, setSyncing] = useState(false);
    const [showSyncModal, setShowSyncModal] = useState(false);
    const [showSyncConfirmModal, setShowSyncConfirmModal] = useState(false);
    const [syncStatus, setSyncStatus] = useState(null);
    const [syncPolling, setSyncPolling] = useState(false);
    
    // Filtrar clientes para exibição
    const filteredS3Clients = s3MappingData?.processes?.filter(p => {
      const matchesSearch = !s3SearchTerm || 
        p.client_name?.toLowerCase().includes(s3SearchTerm.toLowerCase());
      const matchesUnmapped = !showUnmappedOnly || !p.s3_folder;
      return matchesSearch && matchesUnmapped;
    }) || [];
    
    const migrateProcessNumbers = async () => {
      setMigratingProcessNumbers(true);
      try {
        const response = await fetch(`${API_URL}/api/admin/migrate-process-numbers`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });
        const data = await response.json();
        if (data.updated > 0) {
          toast.success(`${data.updated} processos actualizados com números sequenciais (${data.first_number} a ${data.last_number})`);
        } else {
          toast.info(data.message || "Todos os processos já têm número atribuído");
        }
      } catch (error) {
        toast.error("Erro ao migrar números de processo");
      } finally {
        setMigratingProcessNumbers(false);
      }
    };

    // Carregar dados de mapeamento S3 (Clientes/Processos)
    const loadS3MappingData = async () => {
      setLoadingS3Mapping(true);
      try {
        const response = await fetch(`${API_URL}/api/admin/client-s3-mappings`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const data = await response.json();
        setS3MappingData(data);
        // Limpar selecções anteriores
        setSelectedMappings({});
      } catch (error) {
        toast.error("Erro ao carregar mapeamentos S3");
      } finally {
        setLoadingS3Mapping(false);
      }
    };

    // Guardar um mapeamento individual de cliente
    const saveClientS3Mapping = async (processId, s3Folder) => {
      setSavingS3Mapping(true);
      try {
        const url = s3Folder 
          ? `${API_URL}/api/admin/client-s3-mappings?process_id=${processId}&s3_folder=${encodeURIComponent(s3Folder)}`
          : `${API_URL}/api/admin/client-s3-mappings?process_id=${processId}`;
        
        const response = await fetch(url, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });
        const data = await response.json();
        if (data.success) {
          // Fallback para nome do cliente da lista local se não vier do backend
          const clientName = data.client_name || s3MappingData?.processes?.find(p => p.id === processId)?.client_name || "cliente";
          toast.success(`Mapeamento ${s3Folder ? "guardado" : "removido"} para ${clientName}`);
          // Actualizar lista local
          loadS3MappingData();
        } else {
          toast.error(data.detail || "Erro ao guardar mapeamento");
        }
      } catch (error) {
        toast.error("Erro ao guardar mapeamento");
      } finally {
        setSavingS3Mapping(false);
      }
    };

    // Guardar todos os mapeamentos alterados de clientes
    const saveAllClientS3Mappings = async () => {
      // Filtrar apenas mapeamentos que foram realmente alterados
      const changedMappings = Object.entries(selectedMappings)
        .filter(([processId, s3Folder]) => {
          const currentProcess = s3MappingData?.processes?.find(p => p.id === processId);
          const currentMapping = currentProcess?.s3_folder || "";
          const newMapping = s3Folder || "";
          return currentMapping !== newMapping;
        })
        .map(([processId, s3Folder]) => ({
          process_id: processId,
          s3_folder: s3Folder || null
        }));
      
      if (changedMappings.length === 0) {
        toast.info("Nenhuma alteração para guardar");
        return;
      }
      
      setSavingS3Mapping(true);
      try {
        const response = await fetch(`${API_URL}/api/admin/client-s3-mappings/bulk`, {
          method: "POST",
          headers: { 
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json"
          },
          body: JSON.stringify(changedMappings)
        });
        
        if (!response.ok) {
          const errorText = await response.text();
          console.error("Erro na resposta:", response.status, errorText);
          toast.error(`Erro ${response.status}: Falha ao guardar mapeamentos`);
          return;
        }
        
        const data = await response.json();
        if (data.success) {
          toast.success(`${data.updated} mapeamento(s) actualizado(s)`);
          setSelectedMappings({});
          loadS3MappingData();
        } else {
          toast.error(data.message || "Erro ao guardar mapeamentos");
        }
      } catch (error) {
        console.error("Erro ao guardar mapeamentos:", error);
        toast.error("Erro de rede ao guardar mapeamentos");
      } finally {
        setSavingS3Mapping(false);
      }
    };
    
    // Auto-mapear clientes para pastas S3
    const handleAutoMapClients = async () => {
      setAutoMapping(true);
      try {
        const response = await fetch(`${API_URL}/api/admin/client-s3-mappings/auto-map`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });
        const data = await response.json();
        
        if (response.ok) {
          const total = (data.mapped || 0) + (data.skipped || 0);
          if (data.mapped > 0) {
            toast.success(`${data.mapped} processos mapeados automaticamente (${data.skipped} já mapeados ou sem correspondência)`);
          } else {
            toast.info(`Nenhum novo mapeamento encontrado (${data.skipped} processos já mapeados ou sem correspondência)`);
          }
          if (data.errors && data.errors.length > 0) {
            toast.warning(`Alguns erros: ${data.errors.join(", ")}`);
          }
          loadS3MappingData();
        } else {
          toast.error(data.detail || "Erro no auto-mapeamento");
        }
      } catch (error) {
        toast.error("Erro ao auto-mapear clientes");
      } finally {
        setAutoMapping(false);
      }
    };
    
    // Corrigir nomes de clientes em falta
    const handleFixMissingNames = async () => {
      setFixingNames(true);
      try {
        const response = await fetch(`${API_URL}/api/admin/client-s3-mappings/fix-missing-names`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });
        const data = await response.json();
        
        if (response.ok) {
          if (data.fixed_count > 0) {
            toast.success(`${data.fixed_count} processos corrigidos com nomes extraídos das pastas S3 ou emails`);
          } else {
            toast.info("Todos os processos já têm nome definido");
          }
          loadS3MappingData();
        } else {
          toast.error(data.detail || "Erro ao corrigir nomes");
        }
      } catch (error) {
        toast.error("Erro ao corrigir nomes de clientes");
      } finally {
        setFixingNames(false);
      }
    };

    // Guardar todos os mapeamentos alterados (legado - manter para compatibilidade)
    const saveAllS3Mappings = async () => {
      setSavingS3Mapping(true);
      try {
        const mappings = Object.entries(selectedMappings).map(([userId, s3Folder]) => ({
          user_id: userId,
          s3_folder: s3Folder || null
        }));

        const response = await fetch(`${API_URL}/api/admin/user-s3-mappings/bulk`, {
          method: "POST",
          headers: { 
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json"
          },
          body: JSON.stringify(mappings)
        });
        const data = await response.json();
        if (data.success) {
          toast.success(`${data.updated} mapeamentos actualizados`);
          loadS3MappingData();
        } else {
          toast.error("Erro ao guardar mapeamentos");
        }
      } catch (error) {
        toast.error("Erro ao guardar mapeamentos");
      } finally {
        setSavingS3Mapping(false);
      }
    };

    // ─── Sincronização Prod → Dev ───
    const isDevEnvironment = process.env.REACT_APP_ENVIRONMENT === "development" || 
                             process.env.REACT_APP_ENVIRONMENT === "dev" || 
                             !process.env.REACT_APP_ENVIRONMENT;

    const fetchSyncStatus = async () => {
      try {
        const response = await fetch(`${API_URL}/api/admin/sync-database/status`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (response.ok) {
          const data = await response.json();
          setSyncStatus(data);
          return data;
        }
      } catch (error) {
        console.error("Erro ao obter status do sync:", error);
      }
      return null;
    };

    const handleStartSync = async () => {
      setSyncing(true);
      try {
        const response = await fetch(`${API_URL}/api/admin/sync-database`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({}),
        });

        if (!response.ok) {
          const data = await response.json().catch(() => ({}));
          toast.error(data.detail || `Erro ${response.status}: Não foi possível iniciar a sincronização`);
          setSyncing(false);
          return;
        }

        const data = await response.json();
        if (data.success) {
          toast.success("Sincronização iniciada em background");
          setShowSyncConfirmModal(false);
          setSyncPolling(true);
        } else {
          toast.error(data.detail || "Erro ao iniciar sincronização");
        }
      } catch (error) {
        toast.error("Erro de conexão ao iniciar sincronização");
      } finally {
        setSyncing(false);
      }
    };

    useEffect(() => {
      if (!syncPolling) return;
      const interval = setInterval(async () => {
        const status = await fetchSyncStatus();
        if (status && !status.in_progress && status.last_result) {
          setSyncPolling(false);
          if (status.last_result.success) {
            toast.success(`Sincronização concluída! ${status.last_result.total_documents} documentos copiados.`);
          } else {
            toast.error(`Erros na sincronização: ${status.last_result.errors?.length || 1} erro(s)`);
          }
        }
      }, 5000);
      return () => clearInterval(interval);
    }, [syncPolling]);

    return (
      <>
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Wrench className="h-5 w-5 text-primary" />
            <div>
              <CardTitle className="text-lg">Manutenção do Sistema</CardTitle>
              <CardDescription>Ferramentas de diagnóstico e reparação</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Reparação de Índices */}
          <div className="border rounded-lg p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="font-medium flex items-center gap-2">
                  <Database className="h-4 w-4" />
                  Índices da Base de Dados
                </h4>
                <p className="text-sm text-muted-foreground">
                  Remove índices antigos/incorretos e recria os correctos. Use se houver erros de "duplicate key".
                </p>
              </div>
              <Button onClick={repairIndexes} disabled={repairingIndexes}>
                {repairingIndexes ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <RefreshCw className="h-4 w-4 mr-2" />
                )}
                Reparar Índices
              </Button>
            </div>
            {indexStats && (
              <div className="bg-muted/50 rounded p-3 text-sm">
                <p className="font-medium mb-2">Estado actual:</p>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                  {Object.entries(indexStats).map(([coll, info]) => (
                    <div key={coll} className="flex items-center gap-1">
                      <CheckCircle className="h-3 w-3 text-green-500" />
                      <span>{coll}: {info.count || 0} índices</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <Button variant="outline" size="sm" onClick={fetchIndexStats}>
              <Eye className="h-4 w-4 mr-2" />
              Ver Estado dos Índices
            </Button>
          </div>

          {/* Limpeza de Jobs Antigos */}
          <div className="border rounded-lg p-4">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="font-medium flex items-center gap-2">
                  <Trash2 className="h-4 w-4" />
                  Limpar Jobs Antigos
                </h4>
                <p className="text-sm text-muted-foreground">
                  Remove jobs de importação concluídos há mais de 7 dias.
                </p>
              </div>
              <Button variant="outline" onClick={cleanOldJobs} disabled={cleaningJobs}>
                {cleaningJobs ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <Trash2 className="h-4 w-4 mr-2" />
                )}
                Limpar
              </Button>
            </div>
          </div>

          {/* Limpeza de Logs Antigos */}
          <div className="border rounded-lg p-4">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="font-medium flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4" />
                  Limpar Logs de Erro Antigos
                </h4>
                <p className="text-sm text-muted-foreground">
                  Remove logs de erro com mais de 30 dias.
                </p>
              </div>
              <Button variant="outline" onClick={cleanOldLogs} disabled={cleaningLogs}>
                {cleaningLogs ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <Trash2 className="h-4 w-4 mr-2" />
                )}
                Limpar
              </Button>
            </div>
          </div>

          {/* Migração de Números de Processo */}
          <div className="border rounded-lg p-4 border-blue-200 dark:border-blue-800 bg-blue-50/50 dark:bg-blue-950/30">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="font-medium flex items-center gap-2">
                  <Database className="h-4 w-4 text-blue-600" />
                  Migrar Números de Processo
                </h4>
                <p className="text-sm text-muted-foreground">
                  Atribui números sequenciais a processos antigos que não têm. Use após actualizações do sistema.
                </p>
              </div>
              <Button onClick={migrateProcessNumbers} disabled={migratingProcessNumbers}>
                {migratingProcessNumbers ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <RefreshCw className="h-4 w-4 mr-2" />
                )}
                Migrar
              </Button>
            </div>
          </div>

          {/* Mapeamento Clientes/Processos-S3 */}
          <div className="border rounded-lg p-4 border-purple-200 dark:border-purple-800 bg-purple-50/50 dark:bg-purple-950/30">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h4 className="font-medium flex items-center gap-2">
                  <FolderOpen className="h-4 w-4 text-purple-600" />
                  Mapeamento Clientes/Processos → Pastas S3
                </h4>
                <p className="text-sm text-muted-foreground">
                  Associe cada cliente/processo à sua pasta de documentos no S3. Clientes sem mapeamento usarão a pasta baseada no nome.
                </p>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" onClick={loadS3MappingData} disabled={loadingS3Mapping}>
                  {loadingS3Mapping ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  ) : (
                    <RefreshCw className="h-4 w-4 mr-2" />
                  )}
                  Carregar
                </Button>
              </div>
            </div>
            
            {s3MappingData && (
              <div className="space-y-4">
                {!s3MappingData.s3_configured && (
                  <div className="bg-yellow-50 dark:bg-yellow-950/30 border border-yellow-200 dark:border-yellow-800 rounded p-3 text-sm flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 text-yellow-600" />
                    <span>S3 não configurado. Configure as credenciais AWS nas definições de Storage.</span>
                  </div>
                )}
                
                {s3MappingData.s3_configured && (
                  <>
                    {/* Estatísticas */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mb-4">
                      <div className="bg-white dark:bg-gray-900 rounded p-3 border text-center">
                        <p className="text-2xl font-bold text-purple-600">{s3MappingData.stats?.total || 0}</p>
                        <p className="text-xs text-muted-foreground">Total de Clientes</p>
                      </div>
                      <div className="bg-white dark:bg-gray-900 rounded p-3 border text-center">
                        <p className="text-2xl font-bold text-green-600">{s3MappingData.stats?.mapped || 0}</p>
                        <p className="text-xs text-muted-foreground">Com Mapeamento</p>
                      </div>
                      <div className="bg-white dark:bg-gray-900 rounded p-3 border text-center">
                        <p className="text-2xl font-bold text-orange-600">{s3MappingData.stats?.unmapped || 0}</p>
                        <p className="text-xs text-muted-foreground">Sem Mapeamento</p>
                      </div>
                    </div>
                    
                    {/* Filtros */}
                    <div className="flex flex-wrap gap-3 items-center">
                      <Input
                        placeholder="Pesquisar por nome..."
                        value={s3SearchTerm}
                        onChange={(e) => setS3SearchTerm(e.target.value)}
                        className="max-w-xs"
                      />
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={showUnmappedOnly}
                          onChange={(e) => setShowUnmappedOnly(e.target.checked)}
                          className="rounded"
                        />
                        Apenas sem mapeamento
                      </label>
                      <Button 
                        variant="outline" 
                        size="sm"
                        onClick={handleAutoMapClients}
                        disabled={autoMapping}
                      >
                        {autoMapping ? (
                          <Loader2 className="h-4 w-4 animate-spin mr-2" />
                        ) : (
                          <Sparkles className="h-4 w-4 mr-2" />
                        )}
                        Auto-Mapear
                      </Button>
                      <Button 
                        variant="outline" 
                        size="sm"
                        onClick={handleFixMissingNames}
                        disabled={fixingNames}
                        className="text-orange-600 border-orange-300 hover:bg-orange-50"
                      >
                        {fixingNames ? (
                          <Loader2 className="h-4 w-4 animate-spin mr-2" />
                        ) : (
                          <UserCheck className="h-4 w-4 mr-2" />
                        )}
                        Corrigir Nomes
                      </Button>
                    </div>
                    
                    {/* Lista de Clientes */}
                    <div className="max-h-80 overflow-y-auto space-y-2">
                      {filteredS3Clients?.map((p) => (
                        <div key={p.id} className="flex items-center gap-3 p-2 bg-white dark:bg-gray-900 rounded border">
                          <div className="flex items-center gap-2 min-w-0 sm:min-w-[250px]">
                            <Users className="h-4 w-4 text-muted-foreground" />
                            <div className="text-sm">
                              <span className="font-medium block">{p.client_name || "Sem nome"}</span>
                              <span className="text-xs text-muted-foreground flex items-center gap-1">
                                {p.process_number ? `#${p.process_number}` : ""} 
                                {p.status && <Badge variant="outline" className="text-[10px]">{p.status}</Badge>}
                              </span>
                            </div>
                          </div>
                          <Link className="h-4 w-4 text-muted-foreground" />
                          <select
                            className="flex-1 px-3 py-1.5 rounded border bg-background text-sm"
                            value={selectedMappings[p.id] || p.s3_folder || ""}
                            onChange={(e) => setSelectedMappings(prev => ({
                              ...prev,
                              [p.id]: e.target.value || null
                            }))}
                          >
                            <option value="">-- Sem mapeamento --</option>
                            {s3MappingData.available_folders?.map((folder) => (
                              <option key={folder.path} value={folder.path}>
                                {folder.name}
                              </option>
                            ))}
                          </select>
                          <Button 
                            size="sm" 
                            variant="outline"
                            onClick={() => saveClientS3Mapping(p.id, selectedMappings[p.id] || p.s3_folder)}
                            disabled={savingS3Mapping}
                          >
                            {savingS3Mapping ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              <Save className="h-3 w-3" />
                            )}
                          </Button>
                        </div>
                      ))}
                      {filteredS3Clients?.length === 0 && (
                        <p className="text-center text-muted-foreground py-4">Nenhum cliente encontrado</p>
                      )}
                    </div>
                    
                    <div className="flex justify-between items-center pt-2 border-t">
                      <p className="text-xs text-muted-foreground">
                        {s3MappingData.available_folders?.length || 0} pastas S3 disponíveis • {s3MappingData.processes?.length || 0} clientes
                      </p>
                      <Button onClick={saveAllClientS3Mappings} disabled={savingS3Mapping || Object.keys(selectedMappings).length === 0}>
                        {savingS3Mapping ? (
                          <Loader2 className="h-4 w-4 animate-spin mr-2" />
                        ) : (
                          <Save className="h-4 w-4 mr-2" />
                        )}
                        Guardar Alterações ({Object.keys(selectedMappings).length})
                      </Button>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>

          {/* ═══ Sincronização Produção → Desenvolvimento (RGPD) ═══ */}
          {isDevEnvironment && user?.role === "admin" && (
            <div className="border rounded-lg p-4 border-red-200 dark:border-red-800 bg-red-50/50 dark:bg-red-950/30">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h4 className="font-medium flex items-center gap-2">
                    <Database className="h-4 w-4 text-red-600" />
                    Sincronizar BD com Produção (Anonimizado)
                  </h4>
                  <p className="text-sm text-muted-foreground mt-1">
                    Copia dados de Produção para Dev com anonimização RGPD. 
                    Dados pessoais (email, NIF, telefone) são mascarados automaticamente.
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3 mb-3">
                <Button
                  variant="destructive"
                  onClick={() => setShowSyncConfirmModal(true)}
                  disabled={syncing || syncPolling}
                >
                  {syncing || syncPolling ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  ) : (
                    <Database className="h-4 w-4 mr-2" />
                  )}
                  {syncPolling ? "Sincronizando..." : "Sincronizar BD com Produção"}
                </Button>
                {syncStatus?.last_result && (
                  <span className="text-xs text-muted-foreground">
                    Última: {syncStatus.last_result.success ? "Sucesso" : "Com erros"} — {syncStatus.last_result.total_documents || 0} docs
                  </span>
                )}
              </div>

              <div className="bg-red-100 dark:bg-red-900/30 rounded p-3 text-xs space-y-1 text-red-800 dark:text-red-200">
                <p className="font-semibold">⚠️ Atenção — Esta ação é irreversível:</p>
                <ul className="list-disc list-inside space-y-0.5 ml-1">
                  <li>Todos os dados atuais de Desenvolvimento serão <strong>apagados</strong></li>
                  <li>Dados de clientes serão <strong>anonimizados</strong> (email, NIF, telefone)</li>
                  <li>Links S3/AWS serão <strong>removidos</strong></li>
                  <li>Dados financeiros ultra-sensíveis serão <strong>limpos</strong></li>
                  <li>Consultores mantêm credenciais de login reais</li>
                </ul>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ═══ Modal de Confirmação Dupla para Sync ═══ */}
      <Dialog open={showSyncConfirmModal} onOpenChange={setShowSyncConfirmModal}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-600">
              <AlertTriangle className="h-5 w-5" />
              Confirmação de Sincronização
            </DialogTitle>
            <DialogDescription>
              Esta operação vai apagar todos os dados de Desenvolvimento e substituí-los por uma cópia anonimizada de Produção.
            </DialogDescription>
          </DialogHeader>

          <div className="bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg p-4 space-y-2 text-sm">
            <p className="font-medium text-red-800 dark:text-red-200">
              ⚠️ AVISO: Ação irreversível
            </p>
            <p>
              Isto vai <strong>apagar todos os dados atuais de Desenvolvimento</strong> e importar uma 
              cópia <strong>mascarada de Produção</strong>.
            </p>
            <ul className="list-disc list-inside space-y-1 ml-1 text-muted-foreground">
              <li>Emails de clientes → <code className="text-xs bg-muted px-1 rounded">user&#123;id&#125;@powercell.dev</code></li>
              <li>NIFs → NIFs falsos mas válidos</li>
              <li>Telefones → Números baralhados</li>
              <li>Nomes → Apelidos ofuscados</li>
              <li>Links S3 → Removidos</li>
              <li>Dados financeiros → Limpos</li>
              <li>Consultores → Emails e passwords mantidos para login</li>
            </ul>
          </div>

          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setShowSyncConfirmModal(false)}>
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={handleStartSync}
              disabled={syncing}
            >
              {syncing ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Database className="h-4 w-4 mr-2" />
              )}
              Confirmar e Sincronizar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      </>
    );
  };

  // Componente de Gestão RGPD
  const RGPDTab = () => {
    const [templateContent, setTemplateContent] = useState("");
    const [originalContent, setOriginalContent] = useState("");
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [templateMeta, setTemplateMeta] = useState({
      is_default: true,
      version: null,
      updated_at: null,
      updated_by: null,
    });
    const [versions, setVersions] = useState([]);
    const [loadingVersions, setLoadingVersions] = useState(false);
    const [changelog, setChangelog] = useState("");
    const [showRgpdPreview, setShowRgpdPreview] = useState(false);
    
    const isAdminOrCEO = user?.role === "admin" || user?.role === "ceo";

    useEffect(() => {
      fetchTemplate();
    }, [token]);

    const fetchTemplate = async () => {
      setLoading(true);
      try {
        const response = await fetch(`${API_URL}/api/rgpd/admin/template`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (response.ok) {
          const data = await response.json();
          setTemplateContent(data.content);
          setOriginalContent(data.content);
          setTemplateMeta({
            is_default: data.is_default,
            version: data.version,
            updated_at: data.updated_at,
            updated_by: data.updated_by,
          });
        }
      } catch (error) {
        console.error("Erro:", error);
        toast.error("Erro ao carregar o template RGPD");
      } finally {
        setLoading(false);
      }
    };

    const fetchVersions = async () => {
      setLoadingVersions(true);
      try {
        const response = await fetch(`${API_URL}/api/rgpd/admin/template/versions`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (response.ok) {
          const data = await response.json();
          setVersions(data.versions || []);
        }
      } catch (error) {
        console.error("Erro:", error);
      } finally {
        setLoadingVersions(false);
      }
    };

    const handleSave = async () => {
      if (!templateContent.trim()) {
        toast.error("O template não pode estar vazio");
        return;
      }
      setSaving(true);
      try {
        const response = await fetch(`${API_URL}/api/rgpd/admin/template`, {
          method: "PUT",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ content: templateContent, changelog: changelog || undefined }),
        });
        if (response.ok) {
          const data = await response.json();
          toast.success(`Template RGPD guardado (v${data.version || ""})`);
          setOriginalContent(templateContent);
          setChangelog("");
          fetchTemplate();
          fetchVersions();
        } else if (response.status === 403) {
          toast.error("Apenas Admin ou CEO podem editar o template");
        } else {
          toast.error("Erro ao guardar o template");
        }
      } catch (error) {
        toast.error("Erro ao guardar o template RGPD");
      } finally {
        setSaving(false);
      }
    };

    const handleReset = async () => {
      setSaving(true);
      try {
        const response = await fetch(`${API_URL}/api/rgpd/admin/template`, {
          method: "PUT",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ content: "", changelog: "Restaurado para template padrão" }),
        });
        if (response.ok) {
          toast.success("Template restaurado para o valor padrão");
          fetchTemplate();
          fetchVersions();
        }
      } catch (error) {
        toast.error("Erro ao restaurar o template padrão");
      } finally {
        setSaving(false);
      }
    };

    const hasChanges = templateContent !== originalContent;

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
      <div className="space-y-4">
        {/* Info Bar */}
        <Card>
          <CardContent className="py-3">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-3">
                <Info className="h-4 w-4 text-blue-500" />
                <span className="text-sm text-muted-foreground">
                  {templateMeta.is_default
                    ? "A utilizar o template padrão. Edite para personalizar."
                    : `Versão ${templateMeta.version || "1.0"} — Última atualização: ${
                        templateMeta.updated_at
                          ? new Date(templateMeta.updated_at).toLocaleString("pt-PT")
                          : "N/A"
                      } ${templateMeta.updated_by ? `por ${templateMeta.updated_by}` : ""}`}
                </span>
              </div>
              {templateMeta.is_default ? (
                <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200">
                  Template Padrão
                </Badge>
              ) : (
                <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">
                  v{templateMeta.version || "1.0"}
                </Badge>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Editor */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileEdit className="h-5 w-5" />
              Texto do Formulário RGPD
            </CardTitle>
            <CardDescription>
              Edite o texto legal do formulário de consentimento RGPD. As variáveis serão substituídas automaticamente pelos dados do cliente.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <SmartRichEditor
              value={templateContent}
              onChange={setTemplateContent}
              placeholder="Introduza o texto do template RGPD..."
              readOnly={!isAdminOrCEO}
              minHeight={300}
              advanced
            />

            {/* Variáveis disponíveis */}
            <div className="bg-muted/50 rounded-lg p-3">
              <p className="text-sm font-medium mb-2">Variáveis disponíveis:</p>
              <div className="flex flex-wrap gap-2">
                {[
                  "{{NOME_CLIENTE}}",
                  "{{NOME_EMPRESA}}",
                  "{{CONTRIBUINTE}}",
                  "{{MORADA}}",
                  "{{CODIGO_POSTAL}}",
                  "{{TIPO_DOCUMENTO}}",
                  "{{NUMERO_DOCUMENTO}}",
                  "{{VALIDADE_DOCUMENTO}}",
                  "{{DATA_ASSINATURA}}",
                ].map((variable) => (
                  <Badge key={variable} variant="secondary" className="font-mono text-xs">
                    {variable}
                  </Badge>
                ))}
              </div>
            </div>

            {/* Changelog input */}
            {isAdminOrCEO && hasChanges && (
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Notas da alteração (opcional)</Label>
                <Input
                  value={changelog}
                  onChange={(e) => setChangelog(e.target.value)}
                  placeholder="Ex: Adicionado ponto sobre partilha de dados com bancos"
                />
              </div>
            )}

            {/* Actions */}
            {isAdminOrCEO ? (
              <div className="flex items-center justify-between pt-2 border-t">
                <Button
                  variant="outline"
                  onClick={handleReset}
                  disabled={saving || templateMeta.is_default}
                >
                  <RotateCcw className="h-4 w-4 mr-2" />
                  Restaurar Padrão
                </Button>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    onClick={() => setShowRgpdPreview(true)}
                    className="gap-2"
                  >
                    👁️ Pré-visualizar RGPD
                  </Button>
                  {hasChanges && (
                    <span className="text-sm text-amber-600 font-medium">
                      Alterações por guardar
                    </span>
                  )}
                  <Button onClick={handleSave} disabled={saving || !hasChanges}>
                    {saving ? (
                      <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    ) : (
                      <Save className="h-4 w-4 mr-2" />
                    )}
                    Guardar Template
                  </Button>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground pt-2 border-t">
                Apenas utilizadores Admin ou CEO podem editar o template RGPD.
              </p>
            )}

          </CardContent>
        </Card>

        {/* RGPD Preview Dialog - outside Card to avoid layout interference */}
        <Dialog open={showRgpdPreview} onOpenChange={setShowRgpdPreview}>
          <DialogContent className="sm:max-w-[700px] max-h-[85vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Pré-visualização RGPD</DialogTitle>
              <DialogDescription>
                Visualização do texto tal como o cliente final o verá
              </DialogDescription>
            </DialogHeader>
            <div className="prose prose-sm max-w-none bg-white dark:bg-gray-900 border rounded-lg p-6 overflow-y-auto max-h-[70vh] break-words"
              dangerouslySetInnerHTML={{
                __html: (() => {
                  // 1. Escape HTML first to prevent unclosed tags from leaking
                  let safe = (templateContent || "")
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;');
                  // 2. Replace variables with styled example spans
                  safe = safe
                    .replace(/\{\{NOME_CLIENTE\}\}/g, '<span class="bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded font-medium text-blue-800 dark:text-blue-200">João Silva</span>')
                    .replace(/\{\{NOME_EMPRESA\}\}/g, '<span class="bg-amber-100 dark:bg-amber-900/60 px-1.5 py-0.5 rounded font-medium text-amber-800 dark:text-amber-200">Power Real Estate</span>')
                    .replace(/\{\{CONTRIBUINTE\}\}/g, '<span class="bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded font-medium text-blue-800 dark:text-blue-200">123456789</span>')
                    .replace(/\{\{MORADA\}\}/g, '<span class="bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded font-medium text-blue-800 dark:text-blue-200">Rua Example, 123, Lisboa</span>')
                    .replace(/\{\{CODIGO_POSTAL\}\}/g, '<span class="bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded font-medium text-blue-800 dark:text-blue-200">1000-001</span>')
                    .replace(/\{\{TIPO_DOCUMENTO\}\}/g, '<span class="bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded font-medium text-blue-800 dark:text-blue-200">Cartão de Cidadão</span>')
                    .replace(/\{\{NUMERO_DOCUMENTO\}\}/g, '<span class="bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded font-medium text-blue-800 dark:text-blue-200">CC 00000000</span>')
                    .replace(/\{\{VALIDADE_DOCUMENTO\}\}/g, '<span class="bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded font-medium text-blue-800 dark:text-blue-200">01/01/2030</span>')
                    .replace(/\{\{DATA_ASSINATURA\}\}/g, '<span class="bg-green-100 dark:bg-green-900/60 px-1.5 py-0.5 rounded font-medium text-green-800 dark:text-green-200">' + new Date().toLocaleDateString("pt-PT") + '</span>')
                    .replace(/\{\{NOME\}\}/g, '<span class="bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded font-medium text-blue-800 dark:text-blue-200">João Silva</span>');
                  // 3. Convert newlines
                  safe = safe.replace(/\n/g, '<br/>');
                  return safe;
                })()
              }}
            />
            <DialogFooter>
              <Button variant="outline" onClick={() => setShowRgpdPreview(false)}>
                Fechar
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Version History */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <History className="h-5 w-5 text-muted-foreground" />
                <div>
                  <CardTitle className="text-lg">Histórico de Versões</CardTitle>
                  <CardDescription>Cada alteração ao template cria uma nova versão para rastreio legal</CardDescription>
                </div>
              </div>
              <Button variant="outline" size="sm" onClick={fetchVersions} disabled={loadingVersions}>
                {loadingVersions ? (
                  <Loader2 className="h-3 w-3 animate-spin mr-1" />
                ) : (
                  <RefreshCw className="h-3 w-3 mr-1" />
                )}
                Atualizar
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {versions.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">
                Nenhuma versão anterior registada.
              </p>
            ) : (
              <div className="space-y-2 max-h-60 overflow-y-auto">
                {versions.map((v) => (
                  <div
                    key={v.id}
                    className={`flex items-center justify-between p-3 rounded-lg border ${
                      v.is_active
                        ? "bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800"
                        : "bg-muted/30"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      {v.is_active && <CheckCircle className="h-4 w-4 text-green-600" />}
                      <div>
                        <p className="text-sm font-medium">
                          Versão {v.version}
                          {v.is_active && (
                            <Badge variant="outline" className="ml-2 text-xs bg-green-100 text-green-700 border-green-300">
                              Ativa
                            </Badge>
                          )}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {v.created_at
                            ? new Date(v.created_at).toLocaleString("pt-PT")
                            : "N/A"}
                          {v.created_by ? ` — ${v.created_by}` : ""}
                        </p>
                        {v.changelog && (
                          <p className="text-xs text-muted-foreground italic mt-0.5">
                            {v.changelog}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    );
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Settings className="h-6 w-6" />
              Configurações do Sistema
            </h1>
            <p className="text-muted-foreground">
              Configure as integrações e definições da aplicação
            </p>
          </div>
          <Button variant="outline" onClick={fetchConfig}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Recarregar
          </Button>
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
                    <button
                      type="button"
                      onClick={() => setActiveTab("company_email")}
                      className={`w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-all ${
                        activeTab === "company_email"
                          ? "bg-primary/10 text-primary font-medium"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground"
                      }`}
                    >
                      <Building2 className={`h-4 w-4 shrink-0 ${activeTab === "company_email" ? "text-primary" : ""}`} />
                      <span className="truncate">Email por Empresa</span>
                      {activeTab === "company_email" && <div className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />}
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveTab("shared_email")}
                      className={`w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-all ${
                        activeTab === "shared_email"
                          ? "bg-primary/10 text-primary font-medium"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground"
                      }`}
                    >
                      <MailCheck className={`h-4 w-4 shrink-0 ${activeTab === "shared_email" ? "text-primary" : ""}`} />
                      <span className="truncate">Email Partilhado</span>
                      {activeTab === "shared_email" && <div className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />}
                    </button>
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
                  <SelectItem value="company_email">
                    <span className="flex items-center gap-2">
                      <Building2 className="h-4 w-4" />
                      Email por Empresa
                    </span>
                  </SelectItem>
                  <SelectItem value="shared_email">
                    <span className="flex items-center gap-2">
                      <MailCheck className="h-4 w-4" />
                      Email Partilhado
                    </span>
                  </SelectItem>
                  <SelectItem value="maintenance">
                    <span className="flex items-center gap-2">
                      <Wrench className="h-4 w-4" />
                      Manutenção
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
                {["rgpd", "company_email", "shared_email", "maintenance"].map((key) => {
                  const Icon = key === "rgpd" ? FileSignature : key === "company_email" ? Building2 : key === "shared_email" ? MailCheck : Wrench;
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
                      {key === "rgpd" ? "RGPD" : key === "company_email" ? "Email Empresa" : key === "shared_email" ? "Email Partilhado" : "Manutenção"}
                    </button>
                  );
                })}
              </div>
            </div>
          </aside>

          {/* ─── Right: Content Area ─── */}
          <main className="min-w-0 flex-1">
            {activeTab === "document_recipients" && <DocumentRecipientsManager token={token} user={user} />}
            {activeTab === "company_email" && <CompanyEmailConfigSection />}
            {activeTab === "shared_email" && <SharedEmailConfigSection />}
            {activeTab !== "document_recipients" && activeTab !== "rgpd" && activeTab !== "maintenance" && activeTab !== "company_email" && activeTab !== "shared_email" && (
              <ConfigSection
                section={fields[activeTab]}
                sectionKey={activeTab}
                config={config?.[activeTab]}
                fields={fields[activeTab]?.fields || []}
                onSave={handleSave}
                onTest={handleTest}
              />
            )}
            {activeTab === "rgpd" && <RGPDTab />}
            {activeTab === "maintenance" && <MaintenanceSection />}
          </main>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default SystemConfigPage;
