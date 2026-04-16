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
 */

import React, { useState, useEffect } from "react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Badge } from "../components/ui/badge";
import { toast } from "sonner";
import api from "../services/api";
import { Mail, Save, RefreshCw, Loader2, Eye, EyeOff, Shield, AlertCircle } from "lucide-react";

const EmailConfigForm = ({ mode = "self", userId, targetUserName, onSuccess, onCancel }) => {
  const isSelf = mode === "self";

  // Build API URLs based on mode
  const getConfigUrl = () => {
    if (isSelf) return "/users/me/email-config";
    return `/admin/users/${userId}/email-config`;
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
  const [webmailConfigured, setWebmailConfigured] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [testResult, setTestResult] = useState(null);

  // Load existing config
  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    setLoading(true);
    try {
      const response = await api.get(getConfigUrl());
      const config = response.data;
      if (config && (config.is_configured || config.imap_server)) {
        setEmailConfig({
          email_address: config.email_address || "",
          imap_server: config.imap_server || "",
          imap_port: config.imap_port || 993,
          smtp_server: config.smtp_server || "",
          smtp_port: config.smtp_port || 465,
          password: "",  // Never populate password from server
        });
        setWebmailConfigured(true);
      }
    } catch (error) {
      setWebmailConfigured(false);
    } finally {
      setLoading(false);
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
      });

      // Now test with the just-saved stored credentials
      const response = await api.post(testConfigUrl());
      const result = response.data;
      setTestResult(result);

      if (result.success) {
        toast.success("Ligação IMAP/SMTP bem-sucedida");
        setWebmailConfigured(true);
      } else {
        toast.error(`Erro na ligação: ${result.error || "Desconhecido"}`);
      }
    } catch (error) {
      const msg = error.response?.data?.detail || "Erro ao testar a ligação";
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
      });
      toast.success("Configuração de webmail guardada com sucesso");
      setEmailConfig((prev) => ({ ...prev, password: "" }));
      setTestResult(null);
      loadConfig();
      if (onSuccess) onSuccess();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao guardar a configuração");
    } finally {
      setSaving(false);
    }
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

      {/* Config Status Badge */}
      <div className="flex items-center gap-2">
        {webmailConfigured ? (
          <Badge className="bg-green-600 hover:bg-green-700 text-white">
            Configurado
          </Badge>
        ) : (
          <Badge variant="secondary">Não configurado</Badge>
        )}
        {webmailConfigured && (
          <span className="text-xs text-muted-foreground">
            Deixe a password em branco para manter a atual
          </span>
        )}
      </div>

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
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="ec_password">
            Password
            {webmailConfigured && (
              <span className="text-xs text-muted-foreground ml-1">(nova, opcional)</span>
            )}
          </Label>
          <div className="relative">
            <Input
              id="ec_password"
              type={showPassword ? "text" : "password"}
              value={emailConfig.password}
              onChange={(e) =>
                setEmailConfig({ ...emailConfig, password: e.target.value })
              }
              placeholder={
                webmailConfigured
                  ? "Nova password (deixar em branco para manter)"
                  : "Password do email"
              }
            />
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
          </div>
        </div>
        <div className="space-y-2">
          <Label htmlFor="ec_imap_server">Servidor IMAP</Label>
          <Input
            id="ec_imap_server"
            type="text"
            value={emailConfig.imap_server}
            onChange={(e) =>
              setEmailConfig({ ...emailConfig, imap_server: e.target.value })
            }
            placeholder="imap.exemplo.com"
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
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="ec_smtp_server">Servidor SMTP</Label>
          <Input
            id="ec_smtp_server"
            type="text"
            value={emailConfig.smtp_server}
            onChange={(e) =>
              setEmailConfig({ ...emailConfig, smtp_server: e.target.value })
            }
            placeholder="smtp.exemplo.com"
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
        {onCancel && (
          <Button variant="ghost" onClick={onCancel}>
            Cancelar
          </Button>
        )}
      </div>
    </div>
  );
};

export default EmailConfigForm;
