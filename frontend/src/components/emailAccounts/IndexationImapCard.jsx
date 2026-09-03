/**
 * IndexationImapCard — Card 2: Conta de Indexação (IMAP Recepção) — system_webmail
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
import { toast } from "sonner";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import { Globe, Save, Loader2, Plug } from "lucide-react";
import { API_URL, fetchSystemConfig } from "./emailAccountsApi";
import { testCompanyEmailConnection } from "../../services/api";

export const IndexationImapCard = () => {
  const { token } = useAuth();
  const [systemWebmail, setSystemWebmail] = useState({
    imap_host: "",
    imap_port: "993",
    email_user: "",
    app_password: "",
  });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const hydratedRef = useRef(false);

  const { data: systemConfig, isLoading: loading } = useQuery({
    queryKey: ["system-config"],
    enabled: Boolean(token),
    queryFn: () => fetchSystemConfig(token),
  });

  useEffect(() => {
    if (!systemConfig?.system_webmail || hydratedRef.current) return;
    hydratedRef.current = true;
    setSystemWebmail({
      imap_host: systemConfig.system_webmail.imap_host || "",
      imap_port: String(systemConfig.system_webmail.imap_port || 993),
      email_user: systemConfig.system_webmail.email_user || "",
      app_password: systemConfig.system_webmail.app_password ? "••••••••" : "",
    });
  }, [systemConfig]);

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
        toast.error(extractErrorMessage(data.detail, "Erro ao guardar configuração IMAP"));
      }
    } catch {
      toast.error("Erro ao guardar configuração IMAP");
    } finally {
      setSaving(false);
    }
  };

  // BUGFIX (Bug 4, Fev 2026): botão "Testar Ligação" — testa a ligação IMAP
  // real com os valores atuais do formulário (sem gravar), via o endpoint
  // genérico de teste SMTP/IMAP já usado em Empresas/Admin.
  const handleTestConnection = async () => {
    if (!systemWebmail.imap_host || !systemWebmail.email_user || !systemWebmail.app_password) {
      toast.error("Preencha o Host, o Email e a App Password para testar a ligação.");
      return;
    }
    if (systemWebmail.app_password === "••••••••") {
      toast.error("Introduza novamente a password para testar a ligação (o campo mostra apenas um indicador).");
      return;
    }
    setTesting(true);
    try {
      const res = await testCompanyEmailConnection({
        imap_host: systemWebmail.imap_host,
        imap_port: parseInt(systemWebmail.imap_port) || 993,
        imap_email: systemWebmail.email_user,
        imap_password: systemWebmail.app_password,
      });
      toast.success(res.data?.results?.imap?.message || "Ligação IMAP validada com sucesso.");
    } catch (err) {
      toast.error(extractErrorMessage(err.response?.data?.detail, "Falha ao testar a ligação IMAP."));
    } finally {
      setTesting(false);
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
    <Card data-testid="indexation-imap-card">
      <CardHeader className="pb-3">
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
      <CardContent className="space-y-3">
        {/* PACOTE: layout em grid 2 colunas (sm:+) para reduzir a altura vertical do cartão */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label htmlFor="wm_imap_host" className="text-xs">IMAP Host</Label>
            <Input id="wm_imap_host" placeholder="imap.gmail.com" value={systemWebmail.imap_host}
              onChange={(e) => setSystemWebmail((p) => ({ ...p, imap_host: e.target.value }))} className="h-9" data-testid="indexation-imap-host-input" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="wm_imap_port" className="text-xs">IMAP Port</Label>
            <Input id="wm_imap_port" type="number" placeholder="993" value={systemWebmail.imap_port}
              onChange={(e) => setSystemWebmail((p) => ({ ...p, imap_port: e.target.value }))} className="h-9" data-testid="indexation-imap-port-input" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="wm_email" className="text-xs">Email / User</Label>
            <Input id="wm_email" placeholder="indexacao@empresa.pt" value={systemWebmail.email_user}
              onChange={(e) => setSystemWebmail((p) => ({ ...p, email_user: e.target.value }))} className="h-9" data-testid="indexation-imap-email-input" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="wm_pass" className="text-xs">App Password</Label>
            <Input id="wm_pass" type="password" placeholder="••••••••" value={systemWebmail.app_password}
              onChange={(e) => setSystemWebmail((p) => ({ ...p, app_password: e.target.value }))} className="h-9" data-testid="indexation-imap-password-input" />
          </div>
        </div>
        <p className="text-xs text-muted-foreground">App Password = password de aplicação (não a password da conta).</p>
        <div className="flex items-center gap-3 pt-1">
          <Button onClick={handleSave} disabled={saving} data-testid="indexation-imap-save-btn">
            {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
            Guardar
          </Button>
          <Button variant="outline" onClick={handleTestConnection} disabled={testing} data-testid="indexation-imap-test-btn">
            {testing ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Plug className="h-4 w-4 mr-2" />}
            Testar Ligação
          </Button>
        </div>
      </CardContent>
    </Card>
  );
};

export default IndexationImapCard;
