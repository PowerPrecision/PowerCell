/**
 * SystemSmtpCard — Card 1: Email do Sistema (Transacional) — system_smtp
 * Extraído de EmailAccountsPage.js (Refactor UX — Fev 2026).
 * Mantém exatamente a mesma lógica e gestão de estado (React Query/hooks).
 */
import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../../contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../ui/card";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Badge } from "../ui/badge";
import RichTextEditor from "../ui/RichTextEditor";
import { toast } from "sonner";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import { Mail, Save, Loader2, Zap, CheckCircle, XCircle, ShieldCheck } from "lucide-react";
import { API_URL, fetchSystemConfig } from "./emailAccountsApi";

export const SystemSmtpCard = () => {
  const { token } = useAuth();
  const [systemSmtp, setSystemSmtp] = useState({
    resend_api_key: "",
    smtp_from_email: "",
    smtp_from_name: "",
    email_signature: "",
  });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(null);
  // Resultado do teste isolado por secção (evita bleed para outros sub-menus)
  const [testResult, setTestResult] = useState(null);
  const hydratedRef = useRef(false);

  const { data: systemConfig, isLoading: loading } = useQuery({
    queryKey: ["system-config"],
    enabled: Boolean(token),
    queryFn: () => fetchSystemConfig(token),
  });

  useEffect(() => {
    if (!systemConfig?.system_smtp || hydratedRef.current) return;
    hydratedRef.current = true;
    setSystemSmtp({
      resend_api_key: systemConfig.system_smtp.resend_api_key || "",
      smtp_from_email: systemConfig.system_smtp.smtp_from_email || "",
      smtp_from_name: systemConfig.system_smtp.smtp_from_name || "",
      email_signature: systemConfig.system_smtp.email_signature || "",
    });
  }, [systemConfig]);

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
        toast.error(extractErrorMessage(data.detail, "Erro ao guardar configuração"));
      }
    } catch {
      toast.error("Erro ao guardar configuração");
    } finally {
      setSaving(false);
    }
  };

  const handleTestSmtp = async () => {
    setTesting("smtp");
    setTestResult(null);
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
          setTestResult({ success: true, message: data.message || "Conexão bem sucedida" });
          toast.success("✅ Resend API conectado com sucesso!");
        } else {
          setTestResult({ success: false, message: data.message || "Falha na conexão" });
          toast.error(data.message || "Falha na conexão");
        }
      } else {
        const data = await res.json();
        setTestResult({ success: false, message: extractErrorMessage(data.detail || data.message, "Falha na conexão") });
        toast.error(extractErrorMessage(data.detail || data.message, "Falha na conexão"));
      }
    } catch (err) {
      const msg = err.name === "AbortError" ? "Timeout: o teste demorou demasiado tempo (30s)" : "Erro no teste de conexão";
      setTestResult({ success: false, message: msg });
      toast.error(msg);
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
    <Card data-testid="system-smtp-card">
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
              onChange={(e) => setSystemSmtp((p) => ({ ...p, resend_api_key: e.target.value }))} data-testid="system-smtp-resend-key-input" />
            <p className="text-xs text-muted-foreground">Chave de API do Resend (obter em <a href="https://resend.com/api-keys" target="_blank" rel="noopener noreferrer" className="text-teal-600 hover:underline">resend.com/api-keys</a>)</p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="sys_smtp_from">Email do Remetente (From)</Label>
            <Input id="sys_smtp_from" placeholder="no-reply@powerealestate.pt" value={systemSmtp.smtp_from_email}
              onChange={(e) => setSystemSmtp((p) => ({ ...p, smtp_from_email: e.target.value }))} data-testid="system-smtp-from-email-input" />
            <p className="text-xs text-muted-foreground">Endereço que aparecerá como remetente. O domínio deve estar verificado no Resend.</p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="sys_smtp_from_name">Nome do Remetente</Label>
            <Input id="sys_smtp_from_name" placeholder="Power Real Estate" value={systemSmtp.smtp_from_name}
              onChange={(e) => setSystemSmtp((p) => ({ ...p, smtp_from_name: e.target.value }))} data-testid="system-smtp-from-name-input" />
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
          <Button onClick={handleSave} disabled={saving} data-testid="system-smtp-save-btn">
            {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
            Guardar
          </Button>
          <Button variant="outline" onClick={handleTestSmtp} disabled={testing === "smtp"} data-testid="system-smtp-test-btn">
            {testing === "smtp" ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Zap className="h-4 w-4 mr-2" />}
            Testar Conexão
          </Button>
          {testResult && (
            <div className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded ${
              testResult.success
                ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"
                : "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300"
            }`} data-testid="system-smtp-test-result">
              {testResult.success ? <CheckCircle className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
              {testResult.message}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default SystemSmtpCard;
