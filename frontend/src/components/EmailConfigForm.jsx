/**
 * EmailConfigForm — Componente partilhado para configuração IMAP/SMTP
 *
 * UTILIZAÇÃO:
 * - ProfilePage.js (mode="self"): Utilizador configura o próprio email
 * - UsersManagementPage.js (mode="admin"): Admin configura email de outro utilizador
 *
 * PROPS:
 * - mode: "self" | "admin"
 * - userId: ID do utilizador alvo (apenas em mode="admin")
 * - targetUserName: Nome do utilizador alvo (para título em modo admin)
 * - onSuccess: Callback após guardar com sucesso
 * - onCancel: Callback para cancelar/fechar
 *
 * COMPORTAMENTO DE EDIÇÃO:
 * - Quando o email já está configurado, os campos ficam disabled (readOnly)
 * - Um botão com ícone de lápis permite ativar o modo de edição
 * - O modo de edição pode ser cancelado, revertendo as alterações não guardadas
 * - Isto evita alterações acidentais numa configuração que funciona
 *
 * GOOGLE OAUTH:
 * O botão "Ligar Google OAuth" usa um fluxo de dois passos para evitar
 * o bug de redirecionamento 401:
 * 1. fetch() com Authorization header → obtém authorization_url do backend
 * 2. window.open(authorization_url) no popup do Google
 * Isto é necessário porque o browser NÃO envia o header Authorization
 * durante window.location.href, causando 401 → redirect para login.
 */

import { useState, useEffect } from "react";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Badge } from "../components/ui/badge";
import { toast } from "sonner";
import api from "../services/api";
import { useAuth } from "../contexts/AuthContext";
import { Mail, Save, RefreshCw, Loader2, Eye, EyeOff, Shield, AlertCircle, Unlink, Pencil, X } from "lucide-react";

const roleLabels = {
  consultor: "Consultor",
  intermediario: "Intermediário",
  indexacao: "Indexação",
  administrativo: "Administrativo",
  diretor: "Diretor",
  ceo: "CEO",
  admin: "Administrador",
};

const API_URL = process.env.REACT_APP_BACKEND_URL;

const EmailConfigForm = ({ mode = "self", userId, targetUserName, onSuccess, onCancel, companyId = "default" }) => {
  const isSelf = mode === "self";
  const { user, effectiveRole, effectiveCompanyId } = useAuth();

  // Whether the user has multiple roles (and thus per-role email configs)
  const hasMultipleRoles = isSelf && user?.additional_roles?.length > 0;

  // Build API URLs based on mode
  const resolvedCompanyId = companyId || effectiveCompanyId || "default";

  // PACOTE DM: headers isolados por UCR da tab (não a empresa activa global)
  const companyRequestConfig = () => {
    const headers = {};
    if (resolvedCompanyId && resolvedCompanyId !== "default") {
      headers["X-Company-Id"] = resolvedCompanyId;
    }
    return {
      headers,
      params: { company_id: resolvedCompanyId },
    };
  };

  const getConfigUrl = () => {
    const cid = resolvedCompanyId;
    const base = isSelf ? "/users/me/email-config" : `/admin/users/${userId}/email-config`;
    return `${base}?company_id=${encodeURIComponent(cid)}`;
  };

  const saveConfigUrl = () => {
    if (isSelf) return "/users/me/email-config";
    return `/admin/users/${userId}/email-config`;
  };

  const testConfigUrl = () => {
    if (isSelf) return "/users/me/email-config/test";
    return `/admin/users/${userId}/email-config/test`;
  };

  const [emailConfig, setEmailConfig] = useState({
    email_address: "",
    imap_server: "",
    imap_port: 993,
    smtp_server: "",
    smtp_port: 465,
    password: "",
  });
  const [hasPassword, setHasPassword] = useState(false);
  const [webmailConfigured, setWebmailConfigured] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [googleOAuthConnecting, setGoogleOAuthConnecting] = useState(false);
  const [googleOAuthConnected, setGoogleOAuthConnected] = useState(false);
  // "user" | "company" | "system" | "shared_role" | "none"
  const [configSource, setConfigSource] = useState("none");

  // Whether form fields should be disabled (configured + not editing)
  const isFieldsLocked = webmailConfigured && !isEditing;
  // IMAP/SMTP come from the company/system — user only edits email + password
  const serversFromCompany = configSource === "company" || configSource === "system";
  const isServerFieldsLocked = isFieldsLocked || serversFromCompany;

  // Load existing config — recarregar quando companyId muda (troca de empresa)
  // O effectiveCompanyId garante reatividade quando o ContextSwitcher muda a empresa ativa.
  //
  // PORQUÊ: Quando o utilizador troca de empresa no ContextSwitcher:
  // 1. O AuthContext atualiza `effectiveCompanyId` via switchActiveCompany()
  // 2. Este useEffect deteta a mudança e chama loadConfig()
  // 3. loadConfig() faz GET /users/me/email-config com o header X-Company-Id atualizado
  // 4. O formulário reflete a configuração da nova empresa ativa
  //
  // LIMPEZA VISUAL: Ao trocar de empresa, também limpamos:
  // - Modo de edição (isEditing → false) para não mostrar dados da empresa anterior
  // - Resultado de teste de ligação (testResult → null)
  // - Estado de visibilidade da password (showPassword → false)
  // - Flag de Google OAuth conectado (para reavaliar com base na nova empresa)
  useEffect(() => {
    // Limpar cache visual antes de carregar nova config
    setIsEditing(false);
    setShowPassword(false);
    setTestResult(null);
    setGoogleOAuthConnected(false);
    // Resetar password visual (nunca vem do servidor, mas limpa lixo de input anterior)
    setEmailConfig(prev => ({ ...prev, password: "" }));

    loadConfig();
  }, [companyId, effectiveCompanyId, effectiveRole]); // ← effectiveRole adicionado: troca de perfil recarrega config

  // Listen for Google OAuth popup messages (two-step flow)
  useEffect(() => {
    const handleMessage = (event) => {
      if (event.data?.type === "google_oauth_success") {
        toast.success("Google OAuth conectado com sucesso!");
        setGoogleOAuthConnecting(false);
        setGoogleOAuthConnected(true);
        loadConfig();
        if (onSuccess) onSuccess();
      }
      if (event.data?.type === "google_oauth_error") {
        toast.error(`Autenticação Google cancelada: ${event.data.error}`);
        setGoogleOAuthConnecting(false);
      }
    };
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, []);

  const loadConfig = async () => {
    setLoading(true);
    // ── Limpeza visual ANTES do fetch ──
    // Garante que o formulário não mostra dados da empresa/perfil anterior
    // enquanto carrega os novos. Isto é redundante com o useEffect mas
    // protege contra chamadas diretas a loadConfig() (ex: Google OAuth callback).
    setWebmailConfigured(false);
    setEmailConfig({
      email_address: "",
      imap_server: "",
      imap_port: 993,
      smtp_server: "",
      smtp_port: 465,
      password: "",
    });
    setHasPassword(false);
    setConfigSource("none");
    try {
      const response = await api.get(getConfigUrl(), companyRequestConfig());
      const config = response.data;
      if (config && (config.is_configured || config.imap_server)) {
        setConfigSource(config.config_source || "user");
        setEmailConfig({
          email_address: config.email_address || "",
          imap_server: config.imap_server || "",
          imap_port: config.imap_port || 993,
          smtp_server: config.smtp_server || "",
          smtp_port: config.smtp_port || 465,
          password: "",  // Never populate password from server
        });
        setHasPassword(config.has_password || false);
        setWebmailConfigured(true);
        // Check Google OAuth status
        if (config.auth_method?.includes("google_oauth") || config.has_google_oauth || config.google_refresh_token) {
          setGoogleOAuthConnected(true);
        }
      } else {
        // Sem config para esta empresa — resetar formulário
        setConfigSource(config?.config_source || "none");
        setEmailConfig({
          email_address: "",
          imap_server: config?.imap_server || "",
          imap_port: config?.imap_port || 993,
          smtp_server: config?.smtp_server || "",
          smtp_port: config?.smtp_port || 465,
          password: "",
        });
        setHasPassword(false);
        setWebmailConfigured(false);
      }
    } catch {
      setConfigSource("none");
      setWebmailConfigured(false);
      setEmailConfig({
        email_address: "",
        imap_server: "",
        imap_port: 993,
        smtp_server: "",
        smtp_port: 465,
        password: "",
      });
      setHasPassword(false);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Google OAuth — Two-step flow to prevent 401 redirect loop.
   *
   * Instead of doing window.location.href = '/api/auth/google/login'
   * (which loses the Authorization header), we:
   * 1. Call the endpoint via fetch() with the Bearer token
   * 2. Get back the authorization_url
   * 3. Open it in a popup
   */
  const handleGoogleOAuthConnect = async () => {
    setGoogleOAuthConnecting(true);
    try {
      // Step 1: fetch the authorization URL (with Bearer token)
      const token = localStorage.getItem("token");
      const params = new URLSearchParams();
      if (emailConfig.email_address) {
        params.set("email_address", emailConfig.email_address);
      }

      const response = await fetch(
        `${API_URL}/api/auth/google/login?${params.toString()}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
            ...(effectiveRole ? { "X-Active-Role": effectiveRole } : {}),
            ...(resolvedCompanyId && resolvedCompanyId !== "default"
              ? { "X-Company-Id": resolvedCompanyId }
              : {}),
          },
        }
      );

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        toast.error(extractErrorMessage(data.detail, "Erro ao iniciar autenticação Google"));
        setGoogleOAuthConnecting(false);
        return;
      }

      const data = await response.json();

      // Step 2: Open the Google auth URL in a popup
      const popup = window.open(
        data.authorization_url,
        "google_oauth",
        "width=600,height=700,left=200,top=100"
      );

      if (!popup) {
        toast.error("Popup bloqueado. Permita popups para este site.");
        setGoogleOAuthConnecting(false);
        return;
      }

      // Timeout safety — clear connecting state after 2 minutes
      setTimeout(() => {
        setGoogleOAuthConnecting(false);
      }, 120000);
    } catch {
      toast.error("Erro ao iniciar autenticação Google");
      setGoogleOAuthConnecting(false);
    }
  };

  const handleGoogleOAuthDisconnect = async () => {
    try {
      await api.delete("/auth/google/disconnect", companyRequestConfig());
      setGoogleOAuthConnected(false);
      toast.success("Google OAuth desconectado");
      loadConfig();
    } catch (error) {
      toast.error(extractErrorMessage(error.response?.data?.detail, "Erro ao desconectar Google OAuth"));
    }
  };

  const handleTest = async () => {
    // Always save current form values first, then test.
    // The test endpoint uses stored credentials, so the form must be saved first
    // to ensure we test the values the user sees (not stale DB values).
    if (!emailConfig.email_address) {
      toast.error("Preencha o endereço de email para testar");
      return;
    }

    if (!webmailConfigured && !emailConfig.password) {
      toast.error("Preencha a password do email para a configuração inicial");
      return;
    }

    setTesting(true);
    setTestResult(null);
    try {
      // Always save form values before testing
      await api.post(saveConfigUrl(), {
        email_address: emailConfig.email_address,
        password: emailConfig.password || undefined,  // omit if empty → backend preserves existing
        imap_server: emailConfig.imap_server,
        imap_port: emailConfig.imap_port,
        smtp_server: emailConfig.smtp_server,
        smtp_port: emailConfig.smtp_port,
        company_id: resolvedCompanyId,  // PACOTE DM: UCR da tab, não a empresa activa global
      }, companyRequestConfig());

      // Now test with the just-saved stored credentials
      const response = await api.post(testConfigUrl(), null, companyRequestConfig());
      const result = response.data;
      setTestResult(result);

      if (result.success) {
        toast.success("Ligação IMAP/SMTP bem-sucedida");
        setWebmailConfigured(true);
        setIsEditing(false);
      } else {
        toast.error(`Erro na ligação: ${result.error || "Desconhecido"}`);
      }
    } catch (error) {
      const msg = extractErrorMessage(error.response?.data?.detail, "Erro ao testar a ligação");
      toast.error(msg);
      setTestResult({ success: false, error: msg });
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async () => {
    if (!emailConfig.email_address) {
      toast.error("Preencha o endereço de email");
      return;
    }

    if (!webmailConfigured && !emailConfig.password) {
      toast.error("Preencha a password do email para a configuração inicial");
      return;
    }

    setSaving(true);
    try {
      await api.post(saveConfigUrl(), {
        email_address: emailConfig.email_address,
        password: emailConfig.password || undefined,
        imap_server: emailConfig.imap_server,
        imap_port: emailConfig.imap_port,
        smtp_server: emailConfig.smtp_server,
        smtp_port: emailConfig.smtp_port,
        company_id: resolvedCompanyId,  // PACOTE DM: UCR da tab, não a empresa activa global
      }, companyRequestConfig());
      toast.success("Configuração de webmail guardada com sucesso");
      setEmailConfig((prev) => ({ ...prev, password: "" }));
      setTestResult(null);
      setIsEditing(false);
      setWebmailConfigured(true);
      loadConfig();
      if (onSuccess) onSuccess();
    } catch (error) {
      toast.error(extractErrorMessage(error.response?.data?.detail, "Erro ao guardar a configuração"));
    } finally {
      setSaving(false);
    }
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setEmailConfig((prev) => ({ ...prev, password: "" }));
    setTestResult(null);
    // Reload config to discard any changes
    loadConfig();
  };

  const handleStartEdit = () => {
    setIsEditing(true);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        <span className="ml-2 text-muted-foreground">A carregar configuração...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Company / profile context — mailbox is per company, not per role */}
      {isSelf && ((companyId && companyId !== "default") || effectiveCompanyId || hasMultipleRoles) && (
        <div className="bg-muted/50 rounded-lg p-3 mb-4">
          <p className="text-sm text-muted-foreground">
            {(companyId && companyId !== "default") || effectiveCompanyId
              ? <>Caixa de email da empresa ativa. Defina o <strong className="text-foreground">email e a password</strong>; os servidores IMAP/SMTP vêm da empresa quando disponíveis.</>
              : <>Defina o <strong className="text-foreground">email e a password</strong> desta conta. Os servidores IMAP/SMTP podem ser herdados da empresa.</>
            }
          </p>
          {hasMultipleRoles && (
            <p className="text-xs text-muted-foreground mt-1">
              Perfil ativo: {roleLabels[effectiveRole] || effectiveRole}. Multi-perfil costuma corresponder a empresas (e caixas) diferentes.
            </p>
          )}
        </div>
      )}

      {/* Admin Mode Header */}
      {!isSelf && targetUserName && (
        <div className="flex items-center gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg text-amber-800 text-sm">
          <Shield className="h-4 w-4 shrink-0" />
          <span>
            A configurar o webmail de <strong>{targetUserName}</strong>.
            A password do email será encriptada antes de ser guardada.
          </span>
        </div>
      )}

      {/* Config Status Badge + Edit Button */}
      <div className="flex items-center gap-2 flex-wrap">
        {webmailConfigured ? (
          <Badge className="bg-green-600 hover:bg-green-700 text-white">
            Configurado
          </Badge>
        ) : (
          <Badge variant="secondary">Não configurado</Badge>
        )}
        {googleOAuthConnected && (
          <Badge className="bg-blue-600 hover:bg-blue-700 text-white">
            Google OAuth
          </Badge>
        )}
        {webmailConfigured && !isEditing && (
          <>
            {hasPassword ? (
              <span className="text-xs text-green-600 flex items-center gap-1">
                <Shield className="h-3 w-3" />
                Password configurada
              </span>
            ) : (
              <span className="text-xs text-amber-600">
                Sem password — configure para ativar sincronização
              </span>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={handleStartEdit}
              className="gap-1.5 ml-auto"
            >
              <Pencil className="h-3.5 w-3.5" />
              Editar Configuração
            </Button>
          </>
        )}
        {isEditing && (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleCancelEdit}
            className="gap-1.5 text-muted-foreground ml-auto"
          >
            <X className="h-3.5 w-3.5" />
            Cancelar Edição
          </Button>
        )}
      </div>

      {/* Google OAuth Section */}
      {isSelf && (
        <div className="p-4 border rounded-lg bg-muted/30 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="text-sm font-medium">Google OAuth (Gmail)</h4>
              <p className="text-xs text-muted-foreground mt-0.5">
                Autenticação via Google para sincronização de emails
              </p>
            </div>
            {googleOAuthConnected ? (
              <Button
                variant="outline"
                size="sm"
                onClick={handleGoogleOAuthDisconnect}
                className="gap-2 text-destructive hover:text-destructive"
              >
                <Unlink className="h-4 w-4" />
                Desconectar
              </Button>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={handleGoogleOAuthConnect}
                disabled={googleOAuthConnecting}
                className="gap-2"
              >
                {googleOAuthConnecting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Mail className="h-4 w-4" />
                )}
                {googleOAuthConnecting ? "A aguardar..." : "Ligar Google OAuth"}
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Form Fields */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="ec_email">Endereço de Email</Label>
          <Input
            id="ec_email"
            type="email"
            value={emailConfig.email_address}
            onChange={(e) =>
              setEmailConfig({ ...emailConfig, email_address: e.target.value })
            }
            placeholder="seu@email.com"
            disabled={isFieldsLocked}
            className={isFieldsLocked ? "bg-muted cursor-not-allowed" : ""}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="ec_password">
            Password
            {webmailConfigured && hasPassword && (
              <span className="text-xs text-muted-foreground ml-1">(nova, opcional)</span>
            )}
          </Label>
          <div className="relative">
            <Input
              id="ec_password"
              type={isFieldsLocked ? "password" : (showPassword ? "text" : "password")}
              value={emailConfig.password}
              onChange={(e) =>
                setEmailConfig({ ...emailConfig, password: e.target.value })
              }
              placeholder={
                webmailConfigured && hasPassword
                  ? "********"
                  : webmailConfigured
                  ? "Nova password (deixar em branco para manter)"
                  : "Password do email"
              }
              disabled={isFieldsLocked}
              className={isFieldsLocked ? "bg-muted cursor-not-allowed" : "pr-9"}
            />
            {/* ── UX: Ocultar botão "Olho" quando campos estão trancados ──
                Se o email já está configurado e o utilizador NÃO está em modo
                de edição, o campo mostra "********" (placeholder). O botão do
                olho não faz sentido aqui porque:
                1. A password real nunca é enviada do servidor
                2. O campo está vazio (value=""), só tem placeholder visual
                3. Clicar no olho só mostraria um campo vazio em texto plano
                Só mostramos o botão quando o utilizador pode editar (isEditing
                ou email ainda não configurado). */}
            {!isFieldsLocked && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="absolute right-0 top-0 h-full"
                onClick={() => setShowPassword(!showPassword)}
              >
                {showPassword ? (
                  <EyeOff className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
              </Button>
            )}
          </div>
          {webmailConfigured && hasPassword && !isFieldsLocked && (
            <p className="text-xs text-green-600 flex items-center gap-1">
              <Shield className="h-3 w-3" />
              Password configurada com sucesso. Preencha apenas se quiser alterar.
            </p>
          )}
        </div>
        <div className="space-y-2">
          <Label htmlFor="ec_imap_server">
            Servidor IMAP
            {serversFromCompany && (
              <span className="text-xs text-muted-foreground ml-1">(empresa)</span>
            )}
          </Label>
          <Input
            id="ec_imap_server"
            type="text"
            value={emailConfig.imap_server}
            onChange={(e) =>
              setEmailConfig({ ...emailConfig, imap_server: e.target.value })
            }
            placeholder="imap.exemplo.com"
            disabled={isServerFieldsLocked}
            className={isServerFieldsLocked ? "bg-muted cursor-not-allowed" : ""}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="ec_imap_port">Porta IMAP</Label>
          <Input
            id="ec_imap_port"
            type="number"
            value={emailConfig.imap_port}
            onChange={(e) =>
              setEmailConfig({ ...emailConfig, imap_port: parseInt(e.target.value) || 993 })
            }
            placeholder="993"
            disabled={isServerFieldsLocked}
            className={isServerFieldsLocked ? "bg-muted cursor-not-allowed" : ""}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="ec_smtp_server">
            Servidor SMTP
            {serversFromCompany && (
              <span className="text-xs text-muted-foreground ml-1">(empresa)</span>
            )}
          </Label>
          <Input
            id="ec_smtp_server"
            type="text"
            value={emailConfig.smtp_server}
            onChange={(e) =>
              setEmailConfig({ ...emailConfig, smtp_server: e.target.value })
            }
            placeholder="smtp.exemplo.com"
            disabled={isServerFieldsLocked}
            className={isServerFieldsLocked ? "bg-muted cursor-not-allowed" : ""}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="ec_smtp_port">Porta SMTP</Label>
          <Input
            id="ec_smtp_port"
            type="number"
            value={emailConfig.smtp_port}
            onChange={(e) =>
              setEmailConfig({ ...emailConfig, smtp_port: parseInt(e.target.value) || 465 })
            }
            placeholder="465"
            disabled={isServerFieldsLocked}
            className={isServerFieldsLocked ? "bg-muted cursor-not-allowed" : ""}
          />
        </div>
      </div>

      {/* Test Result */}
      {testResult && (
        <div
          className={`flex items-start gap-2 p-3 rounded-lg text-sm ${
            testResult.success
              ? "bg-green-50 border border-green-200 text-green-800"
              : "bg-red-50 border border-red-200 text-red-800"
          }`}
        >
          {testResult.success ? (
            <Mail className="h-4 w-4 mt-0.5 shrink-0" />
          ) : (
            <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
          )}
          <div>
            {testResult.success ? (
              <span>
                <strong>IMAP:</strong> {testResult.imap_connected ? "Ligado" : "Falhou"} |{" "}
                <strong>SMTP:</strong> {testResult.smtp_connected ? "Ligado" : "Falhou"}
              </span>
            ) : (
              <span>{testResult.error || "Erro desconhecido na ligação"}</span>
            )}
          </div>
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex flex-col sm:flex-row gap-3 pt-2">
        {(isEditing || !webmailConfigured) && (
          <>
            <Button
              variant="outline"
              onClick={handleTest}
              disabled={testing}
              className="gap-2"
            >
              {testing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              {testing ? "A testar..." : "Testar Ligação"}
            </Button>
            <Button
              onClick={handleSave}
              disabled={saving}
              className="gap-2"
            >
              {saving ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              {saving ? "A guardar..." : "Guardar Configuração"}
            </Button>
          </>
        )}
        {onCancel && !isEditing && (
          <Button variant="ghost" onClick={onCancel}>
            Cancelar
          </Button>
        )}
      </div>
    </div>
  );
};

export default EmailConfigForm;
