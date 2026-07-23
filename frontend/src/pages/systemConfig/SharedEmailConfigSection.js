/**
 * SharedEmailConfigSection — Google OAuth/IMAP por role.
 */
import { useState, useEffect } from "react";
import { useAuth } from "../../contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Badge } from "../../components/ui/badge";
import { Switch } from "../../components/ui/switch";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import { formatDate } from "../../lib/utils";
import { toast } from "sonner";
import {
  Loader2,
  CheckCircle,
  XCircle,
  RefreshCw,
  Info,
  RotateCcw,
  MailCheck,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

const SHARED_EMAIL_ROLES = [
  { role: "indexacao", label: "Indexação", description: "Email partilhado do departamento de indexação" },
  { role: "suporte", label: "Suporte", description: "Email partilhado do departamento de suporte" },
  { role: "comercial", label: "Comercial", description: "Email partilhado do departamento comercial" },
  { role: "admin", label: "Administração", description: "Email partilhado da administração" },
];

export default function SharedEmailConfigSection() {
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
}

