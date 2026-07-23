/**
 * IntegrationsConfigSection — SMTP transacional, storage e webmail sistema.
 *
 * Extraído de SystemConfigPage.js (tab "integrations").
 */
import { useState, useEffect } from "react";
import { useAuth } from "../../contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Badge } from "../../components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../components/ui/select";
import RichTextEditor from "../../components/ui/RichTextEditor";
import { toast } from "sonner";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import {
  Mail,
  Save,
  Loader2,
  CheckCircle,
  XCircle,
  ShieldCheck,
  HardDrive,
  Globe,
  Zap,
  Pencil,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function IntegrationsConfigSection() {
  const { token } = useAuth();
  const [systemSmtp, setSystemSmtp] = useState({
    resend_api_key: "",
    smtp_from_email: "",
    smtp_from_name: "",
    email_signature: "",
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
  // PACOTE BU — SMTP Transacional: inputs disabled por defeito, desbloqueados
  // ao clicar no ícone de Lápis (Pencil) no topo do cartão.
  const [smtpEditMode, setSmtpEditMode] = useState(false);
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
              email_signature: data.system_smtp.email_signature || "",
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
        toast.error(extractErrorMessage(data.detail, "Erro ao guardar configuração"));
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
        setTestResults(prev => ({ ...prev, smtp: { success: false, message: extractErrorMessage(data.detail || data.message, "Falha na conexão") } }));
        toast.error(extractErrorMessage(data.detail || data.message, "Falha na conexão"));
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
            {/* PACOTE BU — Botão Lápis para desbloquear edição (inputs disabled por defeito) */}
            <div className="flex items-center gap-2">
              <Button
                variant={smtpEditMode ? "default" : "ghost"}
                size="icon"
                className="h-7 w-7"
                onClick={() => setSmtpEditMode(!smtpEditMode)}
                title={smtpEditMode ? "Bloquear edição" : "Editar configuração"}
                data-testid="smtp-edit-toggle"
              >
                <Pencil className="h-3.5 w-3.5" />
              </Button>
              {systemSmtp.resend_api_key && (
                <Badge variant="secondary" className="text-xs bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
                  Configurado
                </Badge>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="sys_resend_key">Resend API Key</Label>
              <Input id="sys_resend_key" type="password" placeholder="re_xxxxxxxxxxxx" value={systemSmtp.resend_api_key}
                onChange={(e) => setSystemSmtp((p) => ({ ...p, resend_api_key: e.target.value }))}
                disabled={!smtpEditMode} />
              <p className="text-xs text-muted-foreground">Chave de API do Resend (obter em <a href="https://resend.com/api-keys" target="_blank" rel="noopener noreferrer" className="text-teal-600 hover:underline">resend.com/api-keys</a>)</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="sys_smtp_from">Email do Remetente (From)</Label>
              <Input id="sys_smtp_from" placeholder="no-reply@powerealestate.pt" value={systemSmtp.smtp_from_email}
                onChange={(e) => setSystemSmtp((p) => ({ ...p, smtp_from_email: e.target.value }))}
                disabled={!smtpEditMode} />
              <p className="text-xs text-muted-foreground">Endereço que aparecerá como remetente nos emails do sistema. O domínio deve estar verificado no Resend.</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="sys_smtp_from_name">Nome do Remetente</Label>
              <Input id="sys_smtp_from_name" placeholder="Power Real Estate" value={systemSmtp.smtp_from_name}
                onChange={(e) => setSystemSmtp((p) => ({ ...p, smtp_from_name: e.target.value }))}
                disabled={!smtpEditMode} />
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
            <Button onClick={() => handleSave("system_smtp")} disabled={saving === "system_smtp" || !smtpEditMode}>
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

      {/* Bloco C: Conta Global de Indexação — PACOTE BU: padding/descrições reduzidos */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Globe className="h-5 w-5 text-amber-700 dark:text-amber-400" />
              <CardTitle className="text-base">Webmail Partilhado (Indexação)</CardTitle>
            </div>
            {systemWebmail.imap_host && (
              <Badge variant="secondary" className="text-xs bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
                Configurado
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="wm_imap_host">IMAP Host</Label>
              <Input id="wm_imap_host" placeholder="imap.gmail.com" value={systemWebmail.imap_host}
                onChange={(e) => setSystemWebmail((p) => ({ ...p, imap_host: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="wm_imap_port">IMAP Port</Label>
              <Input id="wm_imap_port" type="number" placeholder="993" value={systemWebmail.imap_port}
                onChange={(e) => setSystemWebmail((p) => ({ ...p, imap_port: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="wm_email">Email / User</Label>
              <Input id="wm_email" placeholder="indexacao@empresa.pt" value={systemWebmail.email_user}
                onChange={(e) => setSystemWebmail((p) => ({ ...p, email_user: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="wm_pass">App Password</Label>
              <Input id="wm_pass" type="password" placeholder="••••••••" value={systemWebmail.app_password}
                onChange={(e) => setSystemWebmail((p) => ({ ...p, app_password: e.target.value }))} />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button onClick={() => handleSave("system_webmail")} disabled={saving === "system_webmail"}>
              {saving === "system_webmail" ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
              Guardar
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

