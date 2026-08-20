/**
 * ProfileRoleTab — Sub-componente de ProfilePage (Pacote DF).
 *
 * PORQUÊ: No Pacote DF, ProfilePage foi reestruturada em Tabs. Cada UCR
 * (user_company_roles) real ganha uma tab que renderiza este componente.
 * Esta sub-rotina encapsula os 3 Cards por-UCR:
 *   1. Dados Profissionais (display_name, professional_phone, job_title)
 *   2. Assinatura de Email (RichTextEditor)
 *   3. Configuração de Webmail (EmailConfigForm / bloqueio para indexação)
 *
 * SCOPE POR UCR: Todos os pedidos PUT /auth/profile incluem o header
 * `X-Company-Id: <companyId>` (override por-request) para que o backend
 * persista os campos no UCR correcto, mesmo que o utilizador tenha outra
 * empresa activa globalmente. O GET /auth/me para carregar os dados
 * iniciais também inclui o mesmo header para receber os campos
 * `active_company_*` correspondentes a este UCR.
 *
 * @prop {string} companyId   — ID da empresa do UCR (ex: "comp-123")
 * @prop {string} role        — Role do UCR (ex: "consultor")
 * @prop {string} companyName — Nome da empresa (ex: "Power Real Estate")
 * @prop {Object} user        — User object do AuthContext (apenas para referência)
 * @prop {Function} onUpdate  — Callback opcional após save (ex: refreshUser)
 */

import { useState, useEffect } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "./ui/card";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Badge } from "./ui/badge";
import { toast } from "sonner";
import api from "../services/api";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import { htmlToText } from "../utils/sanitize";
// PACOTE DF — role helpers centralizados (substituem getRoleLabel local)
import { ROLE_LABELS, ROLE_COLORS } from "../utils/roleUtils";
import EmailAccountsCard from "./EmailAccountsCard";
import RichTextEditor, { RichTextViewer } from "./ui/RichTextEditor";
import {
  Building2,
  PenLine,
  Save,
  Loader2,
  CheckCircle2,
  Mail,
  Shield,
  AlertTriangle,
  Info,
} from "lucide-react";

const ProfileRoleTab = ({ companyId, role, companyName, user, onUpdate }) => {
  // ── Campos por UCR (escopo: companyId) ──
  const [displayName, setDisplayName] = useState("");
  const [professionalPhone, setProfessionalPhone] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [emailSignature, setEmailSignature] = useState("");
  const [savingSignature, setSavingSignature] = useState(false);
  const [savingCompanyFields, setSavingCompanyFields] = useState(false);
  const [savedCompanyFields, setSavedCompanyFields] = useState(false);
  const [loading, setLoading] = useState(true);

  // PACOTE DF — Info de herança de config de email para este UCR específico
  const [emailConfigInfo, setEmailConfigInfo] = useState(null);

  // ── Carregar dados do UCR ──
  // O backend retorna os campos `active_company_*` em /auth/me quando o
  // header X-Company-Id corresponde à empresa do UCR. Aqui fazemos um
  // override EXPLÍCITO do header (não dependemos do interceptor global,
  // que envia a empresa activa global — que pode diferir da tab aberta).
  useEffect(() => {
    let cancelled = false;

    const fetchData = async () => {
      setLoading(true);
      try {
        // 1) Carregar dados do utilizador para ESTE UCR
        const meResponse = await api.get("/auth/me", {
          headers: { "X-Company-Id": companyId },
        });
        const u = meResponse.data;
        if (cancelled) return;
        setDisplayName(u.active_company_display_name ?? u.name ?? "");
        setProfessionalPhone(u.active_company_professional_phone ?? u.phone ?? "");
        setJobTitle(u.active_company_job_title ?? "");
        setEmailSignature(u.active_company_signature ?? u.email_signature ?? "");

        // 2) Carregar info de config de email para ESTE UCR
        try {
          const cfgResponse = await api.get(
            `/users/me/email-config?company_id=${encodeURIComponent(companyId)}`,
            { headers: { "X-Company-Id": companyId } }
          );
          if (!cancelled) setEmailConfigInfo(cfgResponse.data);
        } catch {
          if (!cancelled) setEmailConfigInfo(null);
        }
      } catch (error) {
        // PACOTE DF — erro silencioso no log; a UI continua navegável
        console.error(
          `[ProfileRoleTab] Erro ao carregar dados para ${role}@${companyId}:`,
          error
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchData();
    return () => {
      cancelled = true;
    };
  }, [companyId, role]);

  // ── Guardar campos profissionais (display_name, phone, job_title) ──
  // PACOTE DF — override do header X-Company-Id por-request para persistir
  // no UCR correcto, mesmo que a empresa activa global seja outra.
  const handleSaveCompanyFields = async () => {
    setSavingCompanyFields(true);
    try {
      const response = await api.put(
        "/auth/profile",
        {
          display_name: displayName,           // Per-company name → UCR
          name: displayName,                   // Backward compat global
          professional_phone: professionalPhone, // Per-company phone → UCR
          phone: professionalPhone,            // Backward compat global
          job_title: jobTitle,                 // Per-company cargo → UCR
        },
        { headers: { "X-Company-Id": companyId } }
      );

      if (response.data.warnings?.length > 0) {
        toast.warning(response.data.warnings.join("; "));
      } else {
        toast.success("Dados profissionais guardados", {
          description: companyName
            ? `Dados profissionais guardados para ${companyName}.`
            : "Os seus dados profissionais foram atualizados com sucesso.",
        });
      }

      // Notificar parent para refrescar user global (não afecta o estado local)
      if (onUpdate) await onUpdate();

      // Feedback visual: checkmark temporário
      setSavedCompanyFields(true);
      setTimeout(() => setSavedCompanyFields(false), 2000);
    } catch (error) {
      toast.error("Erro ao guardar", {
        description: extractErrorMessage(
          error.response?.data?.detail,
          "Não foi possível guardar os dados profissionais."
        ),
      });
    } finally {
      setSavingCompanyFields(false);
    }
  };

  // ── Guardar assinatura de email (específica deste UCR) ──
  const handleSaveSignature = async () => {
    setSavingSignature(true);
    try {
      const response = await api.put(
        "/auth/profile",
        {
          signature: emailSignature,         // Campo UCR → user_company_roles
          email_signature: emailSignature,   // Backward compat global
        },
        { headers: { "X-Company-Id": companyId } }
      );

      if (response.data.warnings?.length > 0) {
        toast.warning(response.data.warnings.join("; "));
      } else {
        toast.success("Assinatura guardada com sucesso", {
          description: companyName
            ? `Assinatura atualizada para ${companyName}.`
            : "A sua assinatura de email foi atualizada para esta empresa.",
        });
      }

      if (onUpdate) await onUpdate();
    } catch (error) {
      toast.error("Erro ao guardar", {
        description: extractErrorMessage(
          error.response?.data?.detail,
          "Não foi possível guardar a assinatura."
        ),
      });
    } finally {
      setSavingSignature(false);
    }
  };

  // PACOTE DF — Indexação tem config de email gerida centralmente
  // (suporte não aparece como UCR aqui — effectiveRole suporte legacy)
  const isIndexacao = role === "indexacao";
  const roleLabel = ROLE_LABELS[role] || role;
  const roleColorClasses = ROLE_COLORS[role] || "";

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        <span className="ml-2 text-sm text-muted-foreground">
          A carregar dados de {roleLabel}
          {companyName ? ` @ ${companyName}` : ""}…
        </span>
      </div>
    );
  }

  return (
    <>
      {/* ── Cabeçalho do UCR: badge com role + nome da empresa ── */}
      <div className="flex items-center gap-2 flex-wrap">
        <Badge
          variant="secondary"
          className={roleColorClasses || ""}
        >
          {roleLabel}
        </Badge>
        {companyName && (
          <Badge variant="outline" className="text-xs font-normal">
            <Building2 className="h-3 w-3 mr-1" />
            {companyName}
          </Badge>
        )}
      </div>

      {/* ── Card: Dados Profissionais ── */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Building2 className="h-5 w-5" />
            Dados Profissionais
            {companyName && (
              <Badge variant="outline" className="ml-2 text-xs font-normal">
                {companyName}
              </Badge>
            )}
          </CardTitle>
          <CardDescription>
            Nome, telefone e cargo específicos para esta empresa. Estes dados
            são utilizados na assinatura de email e nos templates.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label htmlFor={`display_name-${companyId}`}>Nome</Label>
              <Input
                id={`display_name-${companyId}`}
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="O seu nome profissional"
              />
              <p className="text-xs text-muted-foreground">
                Nome apresentado nesta empresa.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor={`professional_phone-${companyId}`}>Telefone</Label>
              <Input
                id={`professional_phone-${companyId}`}
                value={professionalPhone}
                onChange={(e) => setProfessionalPhone(e.target.value)}
                placeholder="Ex: +351 912 345 678"
              />
              <p className="text-xs text-muted-foreground">
                Contacto profissional para esta empresa.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor={`job_title-${companyId}`}>Cargo / Função</Label>
              <Input
                id={`job_title-${companyId}`}
                value={jobTitle}
                onChange={(e) => setJobTitle(e.target.value)}
                placeholder="Ex: Consultor Imobiliário"
              />
              <p className="text-xs text-muted-foreground">
                Cargo específico para esta empresa.
              </p>
            </div>
          </div>
          <div className="flex justify-end">
            <Button
              onClick={handleSaveCompanyFields}
              disabled={savingCompanyFields}
              className="gap-2"
            >
              {savingCompanyFields ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> A guardar...
                </>
              ) : savedCompanyFields ? (
                <>
                  <CheckCircle2 className="h-4 w-4 text-green-500" /> Guardado!
                </>
              ) : (
                <>
                  <Save className="h-4 w-4" /> Guardar Dados Profissionais
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* ── Card: Assinatura de Email — Específica deste UCR ── */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <PenLine className="h-5 w-5" />
            Assinatura de Email
            {companyName && (
              <Badge variant="outline" className="ml-2 text-xs font-normal">
                {companyName}
              </Badge>
            )}
          </CardTitle>
          <CardDescription>
            Assinatura de email específica para esta empresa. Será adicionada
            automaticamente no final de todos os emails que enviar.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <RichTextEditor
            key={`sig-${companyId}`}
            value={emailSignature}
            onChange={setEmailSignature}
            placeholder="Escreva ou cole a sua assinatura de email aqui..."
            advanced
            minHeight="120px"
          />
          {emailSignature && htmlToText(emailSignature).trim() && (
            <div className="space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground">Pré-visualização</p>
              <RichTextViewer html={emailSignature} />
            </div>
          )}
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground">
              Suporta formatação de texto, cores, links e imagens. Esta
              assinatura é específica para esta empresa.
            </p>
            <Button
              onClick={handleSaveSignature}
              disabled={savingSignature}
              size="sm"
            >
              {savingSignature ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-1" />
                  A guardar...
                </>
              ) : (
                <>
                  <Save className="h-4 w-4 mr-1" />
                  Guardar Assinatura
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* ── Card: Configuração de Webmail ── */}
      {isIndexacao ? (
        // PACOTE DF — Indexação: config gerida centralmente pelo departamento
        <Card className="border-amber-200 bg-amber-50/50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-amber-800">
              <AlertTriangle className="h-5 w-5" />
              Configuração de Webmail
            </CardTitle>
            <CardDescription className="text-amber-700">
              Acesso gerido centralmente pelo departamento
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-start gap-3 p-4 border border-amber-200 rounded-lg bg-amber-50">
              <Shield className="h-5 w-5 text-amber-600 mt-0.5 shrink-0" />
              <div className="space-y-2">
                <p className="text-amber-800 font-medium">
                  O seu acesso ao email é gerido centralmente pelo departamento.
                </p>
                <p className="text-sm text-amber-700">
                  Contacte o Administrador para alterações na configuração de
                  email. As definições de IMAP/SMTP são aplicadas uniformemente
                  a todos os membros do departamento.
                </p>
                {emailConfigInfo?.display_name && (
                  <p className="text-sm text-amber-700">
                    Caixa partilhada:{" "}
                    <strong>{emailConfigInfo.display_name}</strong>
                    {emailConfigInfo.email_address && (
                      <> ({emailConfigInfo.email_address})</>
                    )}
                  </p>
                )}
                {emailConfigInfo?.is_configured ? (
                  <Badge className="bg-green-600 hover:bg-green-700 text-white">
                    Configuração ativa
                  </Badge>
                ) : (
                  <Badge variant="secondary">Pendente de configuração</Badge>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      ) : (
        // PACOTE DF / DN.4 — Webmail: lista de contas + adicionar
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Mail className="h-5 w-5" />
              Configuração de Webmail
            </CardTitle>
            <CardDescription>
              Contas IMAP/SMTP ou OAuth deste perfil. Pode adicionar várias e escolhê-las no Webmail.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Indicador de herança de config (empresa / sistema) */}
            {emailConfigInfo?.config_source &&
              emailConfigInfo.config_source !== "user" &&
              emailConfigInfo.config_source !== "none" && (
                <div className="flex items-center gap-2 p-3 bg-blue-50 border border-blue-200 rounded-lg text-blue-800 text-sm">
                  <Info className="h-4 w-4 shrink-0" />
                  <span>
                    {emailConfigInfo.config_source === "company" && (
                      <>
                        Servidores IMAP/SMTP herdados da empresa
                        {emailConfigInfo.company_name && (
                          <>
                            {" "}
                            <strong>{emailConfigInfo.company_name}</strong>
                          </>
                        )}
                        . Apenas o email e a password são individuais.
                      </>
                    )}
                    {emailConfigInfo.config_source === "system" && (
                      <>
                        Servidores IMAP/SMTP herdados da configuração global do
                        sistema.
                      </>
                    )}
                  </span>
                </div>
              )}
            {emailConfigInfo?.config_source === "user" && (
              <div className="flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded-lg text-green-800 text-sm">
                <Mail className="h-4 w-4 shrink-0" />
                <span>
                  A utilizar configuração individual. Os servidores foram
                  definidos manualmente.
                </span>
              </div>
            )}
            <EmailAccountsCard key={`${companyId}__${role}`} companyId={companyId} onUpdate={onUpdate} />
          </CardContent>
        </Card>
      )}
    </>
  );
};

export default ProfileRoleTab;
