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
import { safeDateStr } from "../lib/utils";
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
  Plug,
  HardDrive,
  Globe,
  Zap,
  Pencil,
  MessageSquare,
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
// Integrations Config Section (SMTP, Storage, Webmail)
// ====================================================================

const IntegrationsConfigSection = () => {
  const { token } = useAuth();
  const [systemSmtp, setSystemSmtp] = useState({
    resend_api_key: "",
    smtp_from_email: "",
    smtp_from_name: "",
  });
  const [storage, setStorage] = useState({
    provider: "none",
    aws_access_key_id: "",
    aws_secret_access_key: "",
    aws_bucket_name: "",
    aws_region: "eu-west-3",
    onedrive_tenant_id: "",
    onedrive_client_id: "",
    onedrive_client_secret: "",
    onedrive_drive_id: "",
  });
  const [systemWebmail, setSystemWebmail] = useState({
    imap_host: "",
    imap_port: "993",
    email_user: "",
    app_password: "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(null);
  const [testing, setTesting] = useState(null);
  // Resultado do teste isolado por secção (evita bleed de notificações entre sub-menus)
  const [testResults, setTestResults] = useState({});

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
            }));
          }
          if (data.storage) {
            setStorage((prev) => ({
              ...prev,
              provider: data.storage.provider || "none",
              aws_access_key_id: data.storage.aws_access_key_id || "",
              aws_secret_access_key: data.storage.aws_secret_access_key ? "••••••••" : "",
              aws_bucket_name: data.storage.aws_bucket_name || "",
              aws_region: data.storage.aws_region || "eu-west-3",
              onedrive_tenant_id: data.storage.onedrive_tenant_id || "",
              onedrive_client_id: data.storage.onedrive_client_id || "",
              onedrive_client_secret: data.storage.onedrive_client_secret ? "••••••••" : "",
              onedrive_drive_id: data.storage.onedrive_drive_id || "",
            }));
          }
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
        console.error("Error fetching integrations config:", error);
      } finally {
        setLoading(false);
      }
    };
    fetchConfig();
  }, [token]);

  const handleSave = async (section) => {
    setSaving(section);
    try {
      let sectionName, payload;
      if (section === "system_smtp") {
        sectionName = "system_smtp";
        payload = { ...systemSmtp };
      } else if (section === "storage") {
        sectionName = "storage";
        payload = { ...storage };
      } else if (section === "system_webmail") {
        sectionName = "system_webmail";
        payload = { ...systemWebmail, imap_port: parseInt(systemWebmail.imap_port) || 993 };
      }

      const res = await fetch(`${API_URL}/api/system-config/${sectionName}`, {
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
      setSaving(null);
    }
  };

  const handleTestSmtp = async () => {
    setTesting("smtp");
    setTestResults(prev => ({ ...prev, smtp: null }));
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
          setTestResults(prev => ({ ...prev, smtp: { success: true, message: data.message || "Conexão bem sucedida" } }));
          toast.success("✅ Resend API conectado com sucesso!");
        } else {
          setTestResults(prev => ({ ...prev, smtp: { success: false, message: data.message || "Falha na conexão" } }));
          toast.error(data.message || "Falha na conexão");
        }
      } else {
        const data = await res.json();
        setTestResults(prev => ({ ...prev, smtp: { success: false, message: data.detail || data.message || "Falha na conexão" } }));
        toast.error(data.detail || data.message || "Falha na conexão");
      }
    } catch (err) {
      const msg = err.name === "AbortError" ? "Timeout: o teste demorou demasiado tempo (30s)" : "Erro no teste de conexão";
      setTestResults(prev => ({ ...prev, smtp: { success: false, message: msg } }));
      toast.error(msg);
    } finally {
      clearTimeout(timeoutId);
      setTesting(null);
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
      <div>
        <h3 className="text-lg font-semibold">Integrações de Sistema</h3>
        <p className="text-sm text-muted-foreground mt-1">
          Configure os provedores de email, armazenamento e webmail partilhado. Estas configurações são globais e aplicam-se a todo o sistema.
        </p>
      </div>

      {/* Bloco A: Email de Sistema (Resend API) */}
      <Card>
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-lg bg-teal-100 dark:bg-teal-900/30">
                <Mail className="h-5 w-5 text-teal-700 dark:text-teal-400" />
              </div>
              <div>
                <CardTitle className="text-base">Email de Sistema (Transacional)</CardTitle>
                <CardDescription className="text-xs mt-0.5">
                  Envio via Resend API — links de documentação, convites e alertas automáticos
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
              <p className="text-xs text-muted-foreground">Endereço que aparecerá como remetente nos emails do sistema. O domínio deve estar verificado no Resend.</p>
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
          <div className="flex items-center gap-3 pt-2">
            <Button onClick={() => handleSave("system_smtp")} disabled={saving === "system_smtp"}>
              {saving === "system_smtp" ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
              Guardar
            </Button>
            <Button variant="outline" onClick={handleTestSmtp} disabled={testing === "smtp"}>
              {testing === "smtp" ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Zap className="h-4 w-4 mr-2" />}
              Testar Conexão
            </Button>
            {testResults.smtp && (
              <div className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded ${
                testResults.smtp.success
                  ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"
                  : "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300"
              }`}>
                {testResults.smtp.success ? <CheckCircle className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
                {testResults.smtp.message}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Bloco B: Armazenamento de Ficheiros */}
      <Card>
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-lg bg-blue-100 dark:bg-blue-900/30">
                <HardDrive className="h-5 w-5 text-blue-700 dark:text-blue-400" />
              </div>
              <div>
                <CardTitle className="text-base">Armazenamento de Ficheiros</CardTitle>
                <CardDescription className="text-xs mt-0.5">
                  Provedor e credenciais para documentos dos clientes
                </CardDescription>
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Provedor</Label>
            <Select value={storage.provider} onValueChange={(v) => setStorage((p) => ({ ...p, provider: v }))}>
              <SelectTrigger className="w-full md:w-72">
                <SelectValue placeholder="Selecionar provedor" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Nenhum (desativado)</SelectItem>
                <SelectItem value="local">Local (filesystem)</SelectItem>
                <SelectItem value="aws_s3">Amazon S3 / Cloudflare R2 / MinIO</SelectItem>
                <SelectItem value="onedrive">Microsoft OneDrive (em breve)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {storage.provider === "aws_s3" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 p-4 rounded-lg bg-muted/50 border">
              <div className="space-y-2">
                <Label htmlFor="st_bucket">Bucket</Label>
                <Input id="st_bucket" placeholder="meu-bucket" value={storage.aws_bucket_name}
                  onChange={(e) => setStorage((p) => ({ ...p, aws_bucket_name: e.target.value }))} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="st_region">Region</Label>
                <Input id="st_region" placeholder="eu-west-3" value={storage.aws_region}
                  onChange={(e) => setStorage((p) => ({ ...p, aws_region: e.target.value }))} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="st_access_key">Access Key</Label>
                <Input id="st_access_key" placeholder="AKIA..." value={storage.aws_access_key_id}
                  onChange={(e) => setStorage((p) => ({ ...p, aws_access_key_id: e.target.value }))} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="st_secret_key">Secret Key</Label>
                <Input id="st_secret_key" type="password" placeholder="••••••••" value={storage.aws_secret_access_key}
                  onChange={(e) => setStorage((p) => ({ ...p, aws_secret_access_key: e.target.value }))} />
              </div>
            </div>
          )}

          {storage.provider === "onedrive" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 p-4 rounded-lg bg-muted/50 border">
              <div className="space-y-2">
                <Label htmlFor="od_tenant">Tenant ID</Label>
                <Input id="od_tenant" placeholder="xxxxxxxx-xxxx-xxxx-xxxx" value={storage.onedrive_tenant_id}
                  onChange={(e) => setStorage((p) => ({ ...p, onedrive_tenant_id: e.target.value }))} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="od_client_id">Client ID</Label>
                <Input id="od_client_id" placeholder="xxxxxxxx-xxxx-xxxx-xxxx" value={storage.onedrive_client_id}
                  onChange={(e) => setStorage((p) => ({ ...p, onedrive_client_id: e.target.value }))} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="od_client_secret">Client Secret</Label>
                <Input id="od_client_secret" type="password" placeholder="••••••••" value={storage.onedrive_client_secret}
                  onChange={(e) => setStorage((p) => ({ ...p, onedrive_client_secret: e.target.value }))} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="od_drive_id">Drive ID</Label>
                <Input id="od_drive_id" placeholder="xxxxxxxx-xxxx-xxxx-xxxx" value={storage.onedrive_drive_id}
                  onChange={(e) => setStorage((p) => ({ ...p, onedrive_drive_id: e.target.value }))} />
              </div>
            </div>
          )}

          {storage.provider === "local" && (
            <div className="p-4 rounded-lg bg-muted/50 border">
              <p className="text-sm text-muted-foreground">
                O armazenamento local usa o filesystem do servidor. Sem configuração adicional necessária.
                Os ficheiros serão guardados em <code className="bg-muted px-1 py-0.5 rounded text-xs">/tmp/powercell_uploads</code>.
              </p>
            </div>
          )}

          <div className="flex items-center gap-3 pt-2">
            <Button onClick={() => handleSave("storage")} disabled={saving === "storage"}>
              {saving === "storage" ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
              Guardar Storage
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Bloco C: Conta Global de Indexação */}
      <Card>
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-lg bg-amber-100 dark:bg-amber-900/30">
                <Globe className="h-5 w-5 text-amber-700 dark:text-amber-400" />
              </div>
              <div>
                <CardTitle className="text-base">Conta Global de Indexação (Webmail Partilhado)</CardTitle>
                <CardDescription className="text-xs mt-0.5">
                  Conta IMAP partilhada para sincronização de emails do departamento de indexação
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
            <Button onClick={() => handleSave("system_webmail")} disabled={saving === "system_webmail"}>
              {saving === "system_webmail" ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
              Guardar
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
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
                          <span>Conectado: {new Date(safeDateStr(cfg.oauth_connected_at)).toLocaleDateString("pt-PT")}</span>
                        )}
                        {cfg.last_sync_at && (
                          <span>Último sync: {new Date(safeDateStr(cfg.last_sync_at)).toLocaleDateString("pt-PT")}</span>
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
        toast.error(err.detail || "Erro ao guardar");
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
          Última atualização: {new Date(safeDateStr(settings.updated_at)).toLocaleString("pt-PT")}
        </p>
      )}
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
                        <p className="text-2xl font-bold text-purple-600">{safeString(s3MappingData.stats?.total ?? 0)}</p>
                        <p className="text-xs text-muted-foreground">Total de Clientes</p>
                      </div>
                      <div className="bg-white dark:bg-gray-900 rounded p-3 border text-center">
                        <p className="text-2xl font-bold text-green-600">{safeString(s3MappingData.stats?.mapped ?? 0)}</p>
                        <p className="text-xs text-muted-foreground">Com Mapeamento</p>
                      </div>
                      <div className="bg-white dark:bg-gray-900 rounded p-3 border text-center">
                        <p className="text-2xl font-bold text-orange-600">{safeString(s3MappingData.stats?.unmapped ?? 0)}</p>
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
          {isDevEnvironment && hasRole(user, "admin") && (
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
    
    const isAdminOrCEO = hasAnyRole(user, ["admin", "ceo"]);

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
          toast.success(`Template RGPD guardado (v${data.version || ""})`, { id: "rgpd-save" });
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

    // Insert a variable at the current textarea cursor position
    const insertVariable = (variableKey) => {
      const textarea = document.querySelector('.rgpd-editor-textarea');
      if (textarea) {
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        const before = templateContent.substring(0, start);
        const after = templateContent.substring(end);
        const insertion = `{{${variableKey}}}`;
        setTemplateContent(before + insertion + after);
        // Restore cursor position after React re-render
        requestAnimationFrame(() => {
          textarea.selectionStart = textarea.selectionEnd = start + insertion.length;
          textarea.focus();
        });
      } else {
        // Fallback: append at end
        setTemplateContent((prev) => prev + `{{${variableKey}}}`);
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
                    : `Versão ${safeString(templateMeta.version) || "1.0"} — Última atualização: ${
                        templateMeta.updated_at
                          ? new Date(safeDateStr(templateMeta.updated_at)).toLocaleString("pt-PT")
                          : "N/A"
                      } ${templateMeta.updated_by ? `por ${safeString(templateMeta.updated_by)}` : ""}`}
                </span>
              </div>
              {templateMeta.is_default ? (
                <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200">
                  Template Padrão
                </Badge>
              ) : (
                <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">
                  v{safeString(templateMeta.version) || "1.0"}
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
            {/* Variable chips — click to insert at cursor position */}
            {isAdminOrCEO && (
              <div className="space-y-1.5">
                <p className="text-xs text-muted-foreground font-medium">
                  Clique numa variável para inserir no texto:
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {[
                    { key: "NOME_CLIENTE", label: "Nome Cliente" },
                    { key: "NOME", label: "Nome" },
                    { key: "NOME_EMPRESA", label: "Empresa" },
                    { key: "MORADA_EMPRESA", label: "Morada Empresa" },
                    { key: "CONTACTO_EMPRESA", label: "Contacto Empresa" },
                    { key: "CONTRIBUINTE", label: "NIF" },
                    { key: "MORADA", label: "Morada" },
                    { key: "LOCALIDADE", label: "Localidade" },
                    { key: "CODIGO_POSTAL", label: "C. Postal" },
                    { key: "TIPO_DOCUMENTO", label: "Tipo Doc." },
                    { key: "NUMERO_DOCUMENTO", label: "Nº Doc." },
                    { key: "VALIDADE_DOCUMENTO", label: "Validade" },
                    { key: "DATA_ASSINATURA", label: "Data Assinatura" },
                  ].map(({ key, label }) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => insertVariable(key)}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-border bg-muted/40 hover:bg-muted text-xs font-mono text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Textarea editor — plain text, no WYSIWYG corruption of {{variables}} */}
            <textarea
              value={safeString(templateContent)}
              onChange={(e) => setTemplateContent(e.target.value)}
              disabled={!isAdminOrCEO}
              placeholder="Introduza o texto do template RGPD... Use {{NOME_CLIENTE}} para variáveis dinâmicas."
              spellCheck={false}
              className="rgpd-editor-textarea w-full rounded-lg border border-input bg-background p-4 font-mono text-sm leading-relaxed resize-y focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1 text-foreground placeholder:text-muted-foreground"
              style={{ minHeight: "380px" }}
            />
            {isAdminOrCEO && (
              <p className="text-[11px] text-muted-foreground">
                Use as variáveis acima para personalizar o documento. Não edite as chavetas {'{{ }}'} manualmente — use os botões.
              </p>
            )}

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
                    .replace(/\{\{LOCALIDADE\}\}/g, '<span class="bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded font-medium text-blue-800 dark:text-blue-200">Lisboa</span>')
                    .replace(/\{\{CODIGO_POSTAL\}\}/g, '<span class="bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded font-medium text-blue-800 dark:text-blue-200">1000-001</span>')
                    .replace(/\{\{TIPO_DOCUMENTO\}\}/g, '<span class="bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded font-medium text-blue-800 dark:text-blue-200">Cartão de Cidadão</span>')
                    .replace(/\{\{NUMERO_DOCUMENTO\}\}/g, '<span class="bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded font-medium text-blue-800 dark:text-blue-200">CC 00000000</span>')
                    .replace(/\{\{VALIDADE_DOCUMENTO\}\}/g, '<span class="bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded font-medium text-blue-800 dark:text-blue-200">01/01/2030</span>')
                    .replace(/\{\{DATA_ASSINATURA\}\}/g, '<span class="bg-green-100 dark:bg-green-900/60 px-1.5 py-0.5 rounded font-medium text-green-800 dark:text-green-200">' + new Date().toLocaleDateString("pt-PT") + '</span>')
                    .replace(/\{\{NOME\}\}/g, '<span class="bg-blue-100 dark:bg-blue-900/60 px-1.5 py-0.5 rounded font-medium text-blue-800 dark:text-blue-200">João Silva</span>')
                    .replace(/\{\{MORADA_EMPRESA\}\}/g, '<span class="bg-amber-100 dark:bg-amber-900/60 px-1.5 py-0.5 rounded font-medium text-amber-800 dark:text-amber-200">Rua da Empresa, 1, Lisboa</span>')
                    .replace(/\{\{CONTACTO_EMPRESA\}\}/g, '<span class="bg-amber-100 dark:bg-amber-900/60 px-1.5 py-0.5 rounded font-medium text-amber-800 dark:text-amber-200">info@empresa.pt / 210000000</span>');
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
                          Versão {safeString(v.version)}
                          {v.is_active && (
                            <Badge variant="outline" className="ml-2 text-xs bg-green-100 text-green-700 border-green-300">
                              Ativa
                            </Badge>
                          )}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {v.created_at
                            ? new Date(safeDateStr(v.created_at)).toLocaleString("pt-PT")
                            : "N/A"}
                          {v.created_by ? ` — ${safeString(v.created_by)}` : ""}
                        </p>
                        {v.changelog && (
                          <p className="text-xs text-muted-foreground italic mt-0.5">
                            {safeString(v.changelog)}
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
                {["rgpd", "maintenance", "portal"].map((key) => {
                  const Icon = key === "rgpd" ? FileSignature : key === "portal" ? MessageSquare : Wrench;
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
                      {key === "rgpd" ? "RGPD" : key === "portal" ? "Portal" : "Manutenção"}
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
            {activeTab !== "document_recipients" && activeTab !== "rgpd" && activeTab !== "maintenance" && activeTab !== "integrations" && activeTab !== "system_emails" && activeTab !== "portal" && (
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
  );

  return embedded ? pageContent : <DashboardLayout>{pageContent}</DashboardLayout>;
};

// =====================================================================
// SYSTEM EMAILS SECTION — Configuração de remetentes por propósito
// =====================================================================

const SYSTEM_EMAIL_PURPOSES = [
  {
    key: "DOCUMENTS",
    label: "Envio de Documentos",
    description: "Emails enviados quando partilha documentação com clientes via links temporários ou envio direto.",
    icon: FolderOpen,
    color: "bg-blue-500/10 text-blue-600 border-blue-200",
  },
  {
    key: "RGPD",
    label: "Pedidos de RGPD",
    description: "Emails de confirmação de assinatura RGPD enviados aos clientes após consentimento.",
    icon: ShieldCheck,
    color: "bg-emerald-500/10 text-emerald-600 border-emerald-200",
  },
  {
    key: "SYSTEM_ALERTS",
    label: "Alertas do Sistema",
    description: "Notificações automáticas do sistema (processos parados, prazos, alertas de IA).",
    icon: AlertTriangle,
    color: "bg-amber-500/10 text-amber-600 border-amber-200",
  },
  {
    key: "NOTIFICATIONS",
    label: "Notificações Gerais",
    description: "Notificações a utilizadores e clientes (novos processos, atualizações de estado, etc.).",
    icon: Zap,
    color: "bg-purple-500/10 text-purple-600 border-purple-200",
  },
];

const SystemEmailsSection = ({ token }) => {
  const [configs, setConfigs] = useState({});
  const [loading, setLoading] = useState(true);
  const [editingPurpose, setEditingPurpose] = useState(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(null);
  const [testResult, setTestResult] = useState(null);

  // Form state
  const [form, setForm] = useState({ host: "", port: 465, user: "", password: "", from_name: "", from_email: "", use_ssl: true, use_tls: false, is_active: true });

  const fetchConfigs = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/system-config/system-emails`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        const map = {};
        (data || []).forEach((c) => { map[c.purpose] = c; });
        setConfigs(map);
      }
    } catch (e) {
      // silent
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { fetchConfigs(); }, [fetchConfigs]);

  const handleEdit = (purpose) => {
    const existing = configs[purpose];
    setForm({
      host: existing?.host || "",
      port: existing?.port || 465,
      user: existing?.user || "",
      password: "", // never pre-fill
      from_name: existing?.from_name || "",
      from_email: existing?.from_email || "",
      use_ssl: existing?.use_ssl !== false,
      use_tls: existing?.use_tls || false,
      is_active: existing?.is_active !== false,
    });
    setEditingPurpose(purpose);
    setTestResult(null);
  };

  const handleSave = async () => {
    if (!form.host || !form.user) {
      toast.error("Preencha o Host e o Utilizador");
      return;
    }
    setSaving(true);
    try {
      const body = { ...form };
      if (!body.password) delete body.password; // don't send empty password
      const isUpdate = configs[editingPurpose]?.has_password && !body.password;

      const res = await fetch(`${API_URL}/api/system-config/system-emails/${editingPurpose}`, {
        method: configs[editingPurpose] ? "PUT" : "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        toast.success("Configuração guardada com sucesso");
        setEditingPurpose(null);
        fetchConfigs();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || "Erro ao guardar");
      }
    } catch (e) {
      toast.error("Erro de ligação");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async (purpose) => {
    setTesting(purpose);
    setTestResult(null);
    try {
      const res = await fetch(`${API_URL}/api/system-config/system-emails/${purpose}/test`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json().catch(() => ({}));
      setTestResult({ purpose, success: data.success, message: data.message });
    } catch (e) {
      setTestResult({ purpose, success: false, message: "Erro de ligação" });
    } finally {
      setTesting(null);
    }
  };

  const handleDelete = async (purpose) => {
    if (!window.confirm(`Eliminar a configuração de "${purpose}"?`)) return;
    try {
      const res = await fetch(`${API_URL}/api/system-config/system-emails/${purpose}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        toast.success("Configuração eliminada");
        fetchConfigs();
        if (editingPurpose === purpose) setEditingPurpose(null);
      }
    } catch (e) {
      toast.error("Erro ao eliminar");
    }
  };

  if (loading) return <div className="flex items-center justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <MailCheck className="h-5 w-5 text-primary" />
          Emails do Sistema
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          Configure remetentes SMTP independentes para cada contexto do sistema. Se não configurado, o sistema usará o email principal.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {SYSTEM_EMAIL_PURPOSES.map((purpose) => {
          const Icon = purpose.icon;
          const config = configs[purpose.key];
          const isEditing = editingPurpose === purpose.key;

          return (
            <Card key={purpose.key} className="overflow-hidden">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`rounded-lg border p-2 ${purpose.color}`}>
                      <Icon className="h-4 w-4" />
                    </div>
                    <div>
                      <CardTitle className="text-base">{safeString(purpose.label)}</CardTitle>
                      <p className="text-xs text-muted-foreground mt-0.5">{safeString(purpose.description)}</p>
                    </div>
                  </div>
                  {config?.is_active ? (
                    <Badge variant="default" className="bg-emerald-500 text-white text-xs">Ativo</Badge>
                  ) : config ? (
                    <Badge variant="secondary" className="text-xs">Inativo</Badge>
                  ) : null}
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                {isEditing ? (
                  <div className="space-y-3 border rounded-lg p-4 bg-muted/30">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <Label className="text-xs">Servidor SMTP</Label>
                        <Input className="h-8 text-sm mt-1" placeholder="smtp.gmail.com" value={form.host} onChange={(e) => setForm((f) => ({ ...f, host: e.target.value }))} />
                      </div>
                      <div>
                        <Label className="text-xs">Porta</Label>
                        <Input className="h-8 text-sm mt-1" type="number" placeholder="465" value={form.port} onChange={(e) => setForm((f) => ({ ...f, port: parseInt(e.target.value) || 465 }))} />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <Label className="text-xs">Utilizador (Email)</Label>
                        <Input className="h-8 text-sm mt-1" placeholder="user@empresa.pt" value={form.user} onChange={(e) => setForm((f) => ({ ...f, user: e.target.value }))} />
                      </div>
                      <div>
                        <Label className="text-xs">Password</Label>
                        <Input className="h-8 text-sm mt-1" type="password" placeholder={config?.has_password ? "••••••••" : "Password SMTP"} value={form.password} onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))} />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <Label className="text-xs">Nome Remetente</Label>
                        <Input className="h-8 text-sm mt-1" placeholder="Power Real Estate" value={form.from_name} onChange={(e) => setForm((f) => ({ ...f, from_name: e.target.value }))} />
                      </div>
                      <div>
                        <Label className="text-xs">Email Remetente</Label>
                        <Input className="h-8 text-sm mt-1" placeholder="noreply@empresa.pt" value={form.from_email} onChange={(e) => setForm((f) => ({ ...f, from_email: e.target.value }))} />
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <label className="flex items-center gap-2 text-xs">
                        <input type="checkbox" checked={form.use_ssl} onChange={(e) => setForm((f) => ({ ...f, use_ssl: e.target.checked }))} />
                        SSL (porta 465)
                      </label>
                      <label className="flex items-center gap-2 text-xs">
                        <input type="checkbox" checked={form.use_tls} onChange={(e) => setForm((f) => ({ ...f, use_tls: e.target.checked }))} />
                        TLS (porta 587)
                      </label>
                    </div>
                    <div className="flex items-center gap-2 pt-1">
                      <Button size="sm" onClick={handleSave} disabled={saving}>
                        {saving ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Save className="h-3 w-3 mr-1" />}
                        Guardar
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => { setEditingPurpose(null); setTestResult(null); }}>
                        Cancelar
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div>
                    {config ? (
                      <div className="space-y-2">
                        <div className="flex items-center gap-2 text-sm">
                          <span className="text-muted-foreground">SMTP:</span>
                          <span className="font-mono text-xs">{config.host}:{config.port}</span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <span className="text-muted-foreground">De:</span>
                          <span className="text-xs">{config.from_name ? `${config.from_name} <${config.from_email || config.user}>` : config.user}</span>
                        </div>
                        <div className="flex items-center gap-2 pt-1">
                          <Button size="sm" variant="outline" className="gap-1" onClick={() => handleEdit(purpose.key)}>
                            <Pencil className="h-3 w-3" /> Editar
                          </Button>
                          <Button size="sm" variant="outline" className="gap-1" onClick={() => handleTest(purpose.key)} disabled={testing === purpose.key}>
                            {testing === purpose.key ? <Loader2 className="h-3 w-3 animate-spin" /> : <TestTube className="h-3 w-3" />}
                            Testar
                          </Button>
                          <Button size="sm" variant="ghost" className="gap-1 text-destructive" onClick={() => handleDelete(purpose.key)}>
                            <Trash2 className="h-3 w-3" /> Eliminar
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div>
                        <Badge variant="outline" className="mb-2 border-amber-300 bg-amber-50 text-amber-700 text-xs">
                          <Info className="h-3 w-3 mr-1" />
                          Se não configurado, o sistema usará o email principal (geral@powerealestate.pt)
                        </Badge>
                        <div className="pt-1">
                          <Button size="sm" variant="outline" className="gap-1" onClick={() => handleEdit(purpose.key)}>
                            <Plus className="h-3 w-3" /> Configurar
                          </Button>
                        </div>
                      </div>
                    )}
                    {testResult?.purpose === purpose.key && (
                      <div className={`mt-2 flex items-center gap-2 text-xs rounded-md p-2 ${testResult.success ? "bg-emerald-50 text-emerald-700 border border-emerald-200" : "bg-red-50 text-red-700 border border-red-200"}`}>
                        {testResult.success ? <CheckCircle className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
                        {testResult.message}
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
};

export default SystemConfigPage;

// Named exports para uso no SystemAdminPanel (tab Comunicações)
export { IntegrationsConfigSection, SystemEmailsSection };
