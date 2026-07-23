/**
 * SystemEmailsSection — emails de sistema por purpose (SystemConfig).
 *
 * Extraído de SystemConfigPage.js (tab "system_emails").
 */
import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Badge } from "../../components/ui/badge";
import { toast } from "sonner";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import { safeString } from "../../utils/safeString";
import {
  Save,
  Loader2,
  Plus,
  Trash2,
  MailCheck,
  ShieldCheck,
  FolderOpen,
  AlertTriangle,
  Zap,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;


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

export default function SystemEmailsSection({ token }) {
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
    } catch {
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
        toast.error(extractErrorMessage(err.detail, "Erro ao guardar"));
      }
    } catch {
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
    } catch {
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
    } catch {
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
}

