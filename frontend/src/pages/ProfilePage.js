/**
 * ProfilePage — Página de perfil do utilizador autenticado.
 *
 * PORQUÊ: Permite ao utilizador consultar e editar dados pessoais e alterar a password.
 *
 * @context {AuthContext} — Consome user, token para autenticação e permissões
 */

import { useState, useEffect } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Separator } from "../components/ui/separator";
import { Badge } from "../components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../components/ui/alert-dialog";
import { toast } from "sonner";
import { useAuth } from "../contexts/AuthContext";
import { useNavigate } from "react-router-dom";
import api from "../services/api";
import { formatDateTime } from "../lib/utils";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import DashboardLayout from "../layouts/DashboardLayout";
import EmailConfigForm from "../components/EmailConfigForm";
import RichTextEditor from "../components/ui/RichTextEditor";
import {
  User,
  Lock,
  Monitor,
  Trash2,
  Shield,
  Save,
  Eye,
  EyeOff,
  LogOut,
  Clock,
  MapPin,
  ArrowLeft,
  Mail,
  RefreshCw,
  Loader2,
  AlertTriangle,
  Info,
  PenLine,
  Building2,
  CheckCircle2,
} from "lucide-react";

// ====================================================================
// PÁGINA DE PERFIL - ÁREA PESSOAL DO UTILIZADOR
// ====================================================================

const ProfilePage = () => {
  const { user, logout, refreshUser, effectiveCompanyId, effectiveRole } = useAuth();
  const navigate = useNavigate();

  // Lista de empresas do utilizador (do GET /auth/me, sempre presente)
  const userCompanies = user?.companies || [];

  // ── Campos por empresa (multi-tenant) ──
  const [displayName, setDisplayName] = useState("");           // per-company display name
  const [professionalPhone, setProfessionalPhone] = useState(""); // per-company phone
  const [jobTitle, setJobTitle] = useState("");                   // per-company job title
  const [emailSignature, setEmailSignature] = useState("");
  const [savingSignature, setSavingSignature] = useState(false);
  const [savingCompanyFields, setSavingCompanyFields] = useState(false);
  const [savedCompanyFields, setSavedCompanyFields] = useState(false);
  const [loading, setLoading] = useState(true);

  // Estados para alteração de password
  const [passwordDialog, setPasswordDialog] = useState(false);
  const [passwordData, setPasswordData] = useState({
    current_password: "",
    new_password: "",
    confirm_password: "",
  });
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const [passwordStrength, setPasswordStrength] = useState(null);

  // Estados para sessões
  const [sessions, setSessions] = useState([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [sessionToRevoke, setSessionToRevoke] = useState(null);
  const [revokingSession, setRevokingSession] = useState(false);

  // Estados para config de email (herança)
  const [emailConfigInfo, setEmailConfigInfo] = useState(null);
  const [loadingEmailConfig, setLoadingEmailConfig] = useState(false);

  // MULTI-EMPRESA: seletor de empresa para config de email pessoal
  // Sincronizado com o ContextSwitcher — quando o utilizador troca de
  // empresa no navbar, o ecrã de webmail reflete a nova empresa.
  //
  // NOTA: Inicializamos com effectiveCompanyId (não "default") porque o
  // backend espera o ID real da empresa no header X-Company-Id. Se
  // inicializássemos com "default", o GET /users/me/email-config não
  // encontraria a config correcta na colecção user_email_configs.
  const [emailCompanyId, setEmailCompanyId] = useState(effectiveCompanyId || "default");
  const [emailCompanies, setEmailCompanies] = useState([]);

  // Sincronizar emailCompanyId com effectiveCompanyId do AuthContext
  // Isto garante que quando o ContextSwitcher troca de empresa, o
  // formulário de webmail recarrega com a config da nova empresa.
  useEffect(() => {
    const newId = effectiveCompanyId || "default";
    if (newId !== emailCompanyId) {
      setEmailCompanyId(newId);
    }
  }, [effectiveCompanyId]);

  // ── REATIVIDADE: Recarregar dados do perfil quando a empresa ativa muda ──
  // Quando o utilizador troca de empresa no ContextSwitcher, os campos
  // específicos da empresa (assinatura, telefone profissional, cargo)
  // devem atualizar automaticamente.
  //
  // NOTA: O backend GET /auth/me faz MERGE dos dados da empresa ativa
  // sobre os campos globais (user.phone ← professional_phone da empresa,
  // user.email_signature ← signature da empresa). Por isso, ao ler
  // user.phone e user.email_signature já obtemos os valores correctos
  // para o contexto actual, sem necessidade de fallback manual.
  //
  // FIX: useState(user?.phone) só corre no PRIMEIRO mount. Quando o
  // ContextSwitcher faz switchActiveCompany(), o AuthContext atualiza o
  // user object mas os estados locais NÃO são automaticamente repostos.
  // Este useEffect é ESSENCIAL para forçar a reidratação do formulário.
  //
  // PACOTE W — Fix Stale State (QA Bug):
  // Problema: switchActiveCompany() faz setActiveCompanyId() ANTES do
  // await api.get("/auth/me"), provocando um render intermédio onde
  // effectiveCompanyId=já mudou mas user=ainda tem dados da empresa anterior.
  // Sem guarda, o useEffect rehidrata os campos com dados STALE (flash visual).
  // Solução: verificar se user.active_company_id está em sincronia com
  // effectiveCompanyId antes de rehidratar. Se não estão sincronizados,
  // o user ainda não foi atualizado — saltamos este ciclo e esperamos
  // pelo próximo render (quando setUser() completar).
  //
  // NOTA: loadEmailConfigInfo() foi REMOVIDO deste useEffect. A carga
  // da config de email é feita EXCLUSIVAMENTE pelo useEffect dedicado
  // (linha ~252) que depende de [emailCompanyId, effectiveCompanyId, effectiveRole],
  // evitando chamadas duplicadas e closures stale de emailCompanyId.
  useEffect(() => {
    if (user) {
      // ── Guarda de sincronia: prevenir reidratação com dados stale ──
      // Quando switchActiveCompany() é chamado, há um render intermédio onde
      // effectiveCompanyId já mudou mas user.active_company_id ainda reflete
      // a empresa anterior. Esta guarda evita o flash de dados errados.
      const userCompanyContext = user.active_company_id || user.company;
      if (effectiveCompanyId && userCompanyContext && userCompanyContext !== effectiveCompanyId) {
        return; // User data é stale para esta empresa — aguardar refreshUser
      }

      // Display name: active_company_display_name > global name
      setDisplayName(user.active_company_display_name ?? user.name ?? "");
      // Phone: active_company_professional_phone > global phone
      setProfessionalPhone(user.active_company_professional_phone ?? user.phone ?? "");
      // Cargo: active_company_job_title
      setJobTitle(user.active_company_job_title ?? "");
      // Email signature
      setEmailSignature(user.active_company_signature ?? user.email_signature ?? "");
      setLoading(false);
    }
  }, [user, effectiveCompanyId, effectiveRole]);

  // Carregar dados do utilizador (inicial — complementado pelo useEffect acima)
  // NOTA: A lógica de carregamento foi movida para o useEffect com [user, effectiveCompanyId]
  // para garantir reatividade à mudança de empresa.

  // Carregar sessões
  const loadSessions = async () => {
    setLoadingSessions(true);
    try {
      const response = await api.get("/auth/sessions");
      setSessions(response.data.sessions || []);
    } catch (error) {
      console.error("Erro ao carregar sessões:", error);
    } finally {
      setLoadingSessions(false);
    }
  };

  useEffect(() => {
    loadSessions();
  }, []);

  // Carregar info de config de email (para mostrar herança)
  // FIX: Passar company_id como query param EXPLÍCITO para garantir que o
  // backend resolve a config da empresa correcta, mesmo se o header
  // X-Company-Id estiver dessincronizado com o sessionStorage.
  // O header continua a ser injectado pelo interceptor api.js, mas o
  // query param serve como fallback de redundância.
  const loadEmailConfigInfo = async () => {
    setLoadingEmailConfig(true);
    try {
      const companyIdParam = emailCompanyId || effectiveCompanyId || "default";
      const response = await api.get(`/users/me/email-config?company_id=${encodeURIComponent(companyIdParam)}`);
      setEmailConfigInfo(response.data);
      // MULTI-EMPRESA: popular lista de empresas disponíveis
      if (response.data.available_companies) {
        setEmailCompanies(response.data.available_companies);
      }
    } catch (error) {
      setEmailConfigInfo(null);
    } finally {
      setLoadingEmailConfig(false);
    }
  };

  // Carregar empresas do sistema para o dropdown (além das do user)
  // NOTA: As empresas do user já vêm em userCompanies (via GET /auth/me).
  // Este useEffect complementa com as empresas do sistema (para admin).
  useEffect(() => {
    const fetchSystemCompanies = async () => {
      try {
        // Primeiro: incluir empresas do utilizador (do AuthContext)
        const userCompanyIds = userCompanies.map(c => c.company_id);

        const res = await api.get("/system-config/companies");
        const systemCompanies = (res.data?.companies || []).map(c => c.company_id);

        // Merge sem duplicados
        setEmailCompanies(prev => {
          const merged = new Set([...prev, ...userCompanyIds, ...systemCompanies]);
          return [...merged];
        });
      } catch (err) {
        // Fallback: usar apenas as empresas do utilizador
        setEmailCompanies(prev => {
          const merged = new Set([...prev, ...userCompanies.map(c => c.company_id)]);
          return [...merged];
        });
      }
    };
    if (user && effectiveRole !== "indexacao" && effectiveRole !== "suporte") {
      fetchSystemCompanies();
    }
  }, [user, userCompanies, effectiveRole]);

  useEffect(() => {
    loadEmailConfigInfo();
  }, [emailCompanyId, effectiveCompanyId, effectiveRole]); // Recarregar quando troca de empresa ou perfil

  // Guardar campos profissionais da empresa (nome, telefone, cargo — consolidado)
  const handleSaveCompanyFields = async () => {
    setSavingCompanyFields(true);
    try {
      const response = await api.put("/auth/profile", {
        display_name: displayName,           // Per-company name → UCR
        name: displayName,                   // Also save globally for backward compat
        professional_phone: professionalPhone, // Per-company phone → UCR
        phone: professionalPhone,            // Also save globally for backward compat
        job_title: jobTitle,                 // Per-company cargo → UCR
      });

      // Verificar avisos do backend
      if (response.data.warnings?.length > 0) {
        toast.warning(response.data.warnings.join("; "));
      } else {
        toast.success("Dados profissionais guardados", {
          description: user?.active_company_name
            ? `Dados profissionais guardados para ${user.active_company_name}`
            : "Os seus dados profissionais foram atualizados com sucesso.",
        });
      }

      // ── REATIVIDADE: Recarregar dados via GET /auth/me ──
      // O await garante que o user no AuthContext é atualizado ANTES de
      // o componente tentar usar os dados. Sem await, o useEffect pode
      // ler dados antigos do user antes do refreshUser completar.
      if (refreshUser) await refreshUser();

      // Feedback visual: mostrar checkmark temporário
      setSavedCompanyFields(true);
      setTimeout(() => setSavedCompanyFields(false), 2000);
    } catch (error) {
      toast.error("Erro ao guardar", {
        description: extractErrorMessage(error.response?.data?.detail, "Não foi possível guardar os dados profissionais."),
      });
    } finally {
      setSavingCompanyFields(false);
    }
  };

  // Guardar assinatura de email (específica da empresa ativa)
  const handleSaveSignature = async () => {
    setSavingSignature(true);
    try {
      const response = await api.put("/auth/profile", {
        signature: emailSignature,  // Campo específico da empresa → user_company_roles
        email_signature: emailSignature,  // Backward compat global
      });

      // Verificar avisos do backend
      if (response.data.warnings?.length > 0) {
        toast.warning(response.data.warnings.join("; "));
      } else {
        // FIX (Pacote K): toast.success explicito (QA pediu esta mensagem exata)
        toast.success("Assinatura guardada com sucesso", {
          description: "A sua assinatura de email foi atualizada para esta empresa.",
        });
      }

      // ── REATIVIDADE: Recarregar dados via GET /auth/me ──
      // O await garante que o user no AuthContext é atualizado ANTES de
      // o componente tentar usar os dados. Sem await, o useEffect pode
      // ler dados antigos do user antes do refreshUser completar.
      if (refreshUser) await refreshUser();
    } catch (error) {
      toast.error("Erro ao guardar", {
        description: extractErrorMessage(error.response?.data?.detail, "Não foi possível guardar a assinatura."),
      });
    } finally {
      setSavingSignature(false);
    }
  };

  // Validar força da password
  const validatePasswordStrength = async (password) => {
    if (!password) {
      setPasswordStrength(null);
      return;
    }
    try {
      const response = await api.post("/auth/validate-password", { password });
      setPasswordStrength(response.data);
    } catch (error) {
      console.error("Erro ao validar password:", error);
    }
  };

  // Alterar password
  const handleChangePassword = async () => {
    if (passwordData.new_password !== passwordData.confirm_password) {
      toast.error("As passwords não coincidem.");
      return;
    }

    setChangingPassword(true);
    try {
      await api.post("/auth/change-password", {
        current_password: passwordData.current_password,
        new_password: passwordData.new_password,
      });
      toast.success("Password alterada", {
        description: "A sua password foi alterada com sucesso.",
      });
      setPasswordDialog(false);
      setPasswordData({
        current_password: "",
        new_password: "",
        confirm_password: "",
      });
      setPasswordStrength(null);
    } catch (error) {
      toast.error("Erro ao alterar password", {
        description: extractErrorMessage(error.response?.data?.detail, "Não foi possível alterar a password."),
      });
    } finally {
      setChangingPassword(false);
    }
  };

  // Revogar sessão
  const handleRevokeSession = async () => {
    if (!sessionToRevoke) return;

    setRevokingSession(true);
    try {
      await api.delete(`/auth/sessions/${sessionToRevoke.id}`);
      toast.success("Sessão terminada", {
        description: "A sessão foi terminada com sucesso.",
      });
      loadSessions();
    } catch (error) {
      toast.error("Não foi possível terminar a sessão.");
    } finally {
      setRevokingSession(false);
      setSessionToRevoke(null);
    }
  };

  // Terminar todas as outras sessões
  const handleRevokeAllOtherSessions = async () => {
    setRevokingSession(true);
    try {
      await api.post("/auth/logout", {});
      toast.success("Sessões terminadas", {
        description: "Todas as outras sessões foram terminadas.",
      });
      loadSessions();
    } catch (error) {
      toast.error("Não foi possível terminar as sessões.");
    } finally {
      setRevokingSession(false);
    }
  };

  // (formatDateTime imported from lib/utils)

  // Traduzir força da password
  const getStrengthLabel = (strength) => {
    const labels = {
      muito_fraca: { label: "Muito fraca", color: "bg-red-500" },
      fraca: { label: "Fraca", color: "bg-orange-500" },
      media: { label: "Média", color: "bg-yellow-500" },
      forte: { label: "Forte", color: "bg-green-500" },
      muito_forte: { label: "Muito forte", color: "bg-emerald-500" },
    };
    return labels[strength] || { label: strength, color: "bg-gray-500" };
  };

  // Traduzir role
  const getRoleLabel = (role) => {
    const roles = {
      admin: "Administrador",
      ceo: "CEO",
      diretor: "Diretor(a)",
      consultor: "Consultor(a)",
      intermediario: "Intermediário de Crédito",
      administrativo: "Administrativo(a)",
      indexacao: "Indexação",
      cliente: "Cliente",
    };
    return roles[role] || role;
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="max-w-4xl mx-auto space-y-6">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 bg-muted animate-pulse rounded" />
            <div className="space-y-1.5">
              <div className="h-8 w-40 bg-muted animate-pulse rounded" />
              <div className="h-4 w-64 bg-muted animate-pulse rounded" />
            </div>
          </div>
          <div className="grid gap-6 md:grid-cols-2">
            {[1,2,3,4].map(i => <div key={i} className="h-36 bg-muted animate-pulse rounded-lg" />)}
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="icon"
              onClick={() => navigate(-1)}
              className="shrink-0"
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <div>
              <h1 className="text-2xl md:text-3xl font-bold">Área Pessoal</h1>
              <p className="text-muted-foreground mt-1">
                Gerir os seus dados e preferências de conta
              </p>
            </div>
          </div>
          <Button variant="outline" onClick={logout} className="gap-2">
            <LogOut className="h-4 w-4" />
            <span className="hidden sm:inline">Terminar Sessão</span>
          </Button>
        </div>

        {/* ── Card 1: Informação de Login (comum a todos os perfis) ── */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Lock className="h-5 w-5" />
              Informação de Login
            </CardTitle>
            <CardDescription>
              Dados de acesso à sua conta — comuns a todos os perfis
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Email (read-only) */}
            <div className="space-y-2">
              <Label>Email</Label>
              <Input value={user?.email || ""} disabled className="bg-muted" />
              <p className="text-xs text-muted-foreground">
                O email não pode ser alterado. Contacte o administrador se precisar de mudar.
              </p>
            </div>
            {/* Password */}
            <div className="flex items-center justify-between p-4 border rounded-lg">
              <div>
                <h3 className="font-medium">Password</h3>
                <p className="text-sm text-muted-foreground">Altere a sua password de acesso</p>
              </div>
              <Button variant="outline" onClick={() => setPasswordDialog(true)}>
                Alterar Password
              </Button>
            </div>
            {/* Role + Company badge */}
            <div className="flex items-center gap-2">
              <Badge variant="secondary">{getRoleLabel(effectiveRole || user?.role)}</Badge>
              {user?.active_company_name && (
                <Badge variant="outline" className="text-xs font-normal">
                  <Building2 className="h-3 w-3 mr-1" />
                  {user.active_company_name}
                </Badge>
              )}
              <span className="text-sm text-muted-foreground">
                Membro desde {formatDateTime(user?.created_at)}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* ── Card 2: Dados Profissionais (por empresa) ── */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Building2 className="h-5 w-5" />
              Dados Profissionais
              {user?.active_company_name && (
                <Badge variant="outline" className="ml-2 text-xs font-normal">
                  {user.active_company_name}
                </Badge>
              )}
            </CardTitle>
            <CardDescription>
              Nome, telefone e cargo específicos para a empresa ativa no Modo de Operação.
              Estes dados são utilizados na assinatura de email e nos templates.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label htmlFor="display_name">Nome</Label>
                <Input
                  id="display_name"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="O seu nome profissional"
                />
                <p className="text-xs text-muted-foreground">
                  Nome apresentado nesta empresa.
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="professional_phone">Telefone</Label>
                <Input
                  id="professional_phone"
                  value={professionalPhone}
                  onChange={(e) => setProfessionalPhone(e.target.value)}
                  placeholder="Ex: +351 912 345 678"
                />
                <p className="text-xs text-muted-foreground">
                  Contacto profissional para esta empresa.
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="job_title">Cargo / Função</Label>
                <Input
                  id="job_title"
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
                  <><Loader2 className="h-4 w-4 animate-spin" /> A guardar...</>
                ) : savedCompanyFields ? (
                  <><CheckCircle2 className="h-4 w-4 text-green-500" /> Guardado!</>
                ) : (
                  <><Save className="h-4 w-4" /> Guardar Dados Profissionais</>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* ── Card 3: Assinatura de Email — Específica da Empresa Ativa ── */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <PenLine className="h-5 w-5" />
              Assinatura de Email
              {user?.active_company_name && (
                <Badge variant="outline" className="ml-2 text-xs font-normal">
                  {user.active_company_name}
                </Badge>
              )}
            </CardTitle>
            <CardDescription>
              Assinatura de email específica para a empresa ativa. Será adicionada automaticamente no final de todos os emails que enviar.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <RichTextEditor
              key={`sig-${effectiveCompanyId || "default"}`}
              value={emailSignature}
              onChange={setEmailSignature}
              placeholder="Escreva ou cole a sua assinatura de email aqui..."
              advanced
              minHeight="120px"
            />
            <div className="flex items-center justify-between">
              <p className="text-xs text-muted-foreground">
                Suporta formatação de texto, cores, links e imagens. Esta assinatura é específica para a empresa ativa.
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

        {/* ── Card 4: Sessões Ativas ── */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <Monitor className="h-5 w-5" />
                  Sessões Ativas
                </CardTitle>
                <CardDescription>
                  Dispositivos onde tem sessão iniciada
                </CardDescription>
              </div>
              {sessions.length > 1 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleRevokeAllOtherSessions}
                  disabled={revokingSession}
                  className="text-destructive"
                >
                  Terminar Outras Sessões
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {loadingSessions ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
              </div>
            ) : sessions.length === 0 ? (
              <p className="text-center text-muted-foreground py-4">
                Nenhuma sessão ativa encontrada
              </p>
            ) : (
              <div className="space-y-3">
                {sessions.map((session) => (
                  <div
                    key={session.id}
                    className="flex items-center justify-between p-4 border rounded-lg hover:bg-muted/50 transition-colors"
                  >
                    <div className="flex items-start gap-3">
                      <Monitor className="h-5 w-5 text-muted-foreground mt-0.5" />
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-sm">
                            {session.device_info || "Dispositivo desconhecido"}
                          </span>
                          {session.current && (
                            <Badge variant="default" className="text-xs">
                              Sessão atual
                            </Badge>
                          )}
                        </div>
                        <div className="flex items-center gap-4 text-xs text-muted-foreground">
                          <span className="flex items-center gap-1">
                            <MapPin className="h-3 w-3" />
                            {session.ip_address || "IP desconhecido"}
                          </span>
                          <span className="flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            {formatDateTime(session.created_at)}
                          </span>
                        </div>
                      </div>
                    </div>
                    {!session.current && (
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setSessionToRevoke(session)}
                        className="text-destructive hover:text-destructive hover:bg-destructive/10"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* ── Card 5: Configuração de Webmail ── */}
        {effectiveRole === "indexacao" || effectiveRole === "suporte" ? (
          /* ── BLOQUEIO: Indexação/Suporte — config gerida centralmente ── */
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
                    Contacte o Administrador para alterações na configuração de email.
                    As definições de IMAP/SMTP são aplicadas uniformemente a todos os membros do departamento.
                  </p>
                  {emailConfigInfo?.display_name && (
                    <p className="text-sm text-amber-700">
                      Caixa partilhada: <strong>{emailConfigInfo.display_name}</strong>
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
          /* ── NORMAL: Config individual com info de herança ── */
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Mail className="h-5 w-5" />
                Configuração de Webmail
              </CardTitle>
              <CardDescription>
                Configure o seu email para integração IMAP/SMTP
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* MULTI-EMPRESA: Seletor de Empresa para config de email */}
              {emailCompanies.length > 1 && (
                <div className="flex items-center gap-3 p-3 bg-muted/50 border rounded-lg">
                  <Building2 className="h-4 w-4 text-muted-foreground shrink-0" />
                  <div className="flex-1">
                    <Label htmlFor="email-company-select" className="text-sm font-medium">
                      Empresa / Perfil
                    </Label>
                    <p className="text-xs text-muted-foreground">
                      Selecione a empresa para a qual esta config de email se aplica
                    </p>
                  </div>
                  <Select
                    value={emailCompanyId}
                    onValueChange={(newId) => {
                      setEmailCompanyId(newId);
                      // Sincronizar com o sessionStorage para que o interceptor
                      // api.js envie o header X-Company-Id correcto nos pedidos
                      // GET/POST /users/me/email-config subsequentes.
                      sessionStorage.setItem("activeCompanyId", newId);
                    }}
                  >
                    <SelectTrigger id="email-company-select" className="w-48">
                      <SelectValue placeholder="Empresa..." />
                    </SelectTrigger>
                    <SelectContent>
                      {emailCompanies.map((cid) => {
                        // Tentar obter nome legível do AuthContext
                        const companyInfo = userCompanies?.find(c => c.company_id === cid);
                        const displayName = cid === "default"
                          ? "Principal (Padrão)"
                          : companyInfo?.company_name || cid;
                        return (
                          <SelectItem key={cid} value={cid}>
                            {displayName}
                          </SelectItem>
                        );
                      })}
                    </SelectContent>
                  </Select>
                </div>
              )}
              {/* Indicador de herança de config */}
              {emailConfigInfo?.config_source && emailConfigInfo.config_source !== "user" && emailConfigInfo.config_source !== "none" && (
                <div className="flex items-center gap-2 p-3 bg-blue-50 border border-blue-200 rounded-lg text-blue-800 text-sm">
                  <Info className="h-4 w-4 shrink-0" />
                  <span>
                    {emailConfigInfo.config_source === "company" && (
                      <>
                        Servidores IMAP/SMTP herdados da empresa
                        {emailConfigInfo.company_name && (
                          <> <strong>{emailConfigInfo.company_name}</strong></>
                        )}
                        . Apenas o email e a password são individuais.
                      </>
                    )}
                    {emailConfigInfo.config_source === "system" && (
                      <>Servidores IMAP/SMTP herdados da configuração global do sistema.</>
                    )}
                  </span>
                </div>
              )}
              {emailConfigInfo?.config_source === "user" && (
                <div className="flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded-lg text-green-800 text-sm">
                  <Mail className="h-4 w-4 shrink-0" />
                  <span>A utilizar configuração individual. Os servidores foram definidos manualmente.</span>
                </div>
              )}
              <EmailConfigForm mode="self" onSuccess={refreshUser} companyId={emailCompanyId} />
            </CardContent>
          </Card>
        )}

        {/* Dialog Alterar Password */}
        <Dialog open={passwordDialog} onOpenChange={setPasswordDialog}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Alterar Password</DialogTitle>
              <DialogDescription>
                Introduza a sua password atual e a nova password
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="current_password">Password Atual</Label>
                <div className="relative">
                  <Input
                    id="current_password"
                    type={showCurrentPassword ? "text" : "password"}
                    value={passwordData.current_password}
                    onChange={(e) =>
                      setPasswordData({
                        ...passwordData,
                        current_password: e.target.value,
                      })
                    }
                    placeholder="Introduza a password atual"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="absolute right-0 top-0 h-full"
                    onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                  >
                    {showCurrentPassword ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              </div>
              <Separator />
              <div className="space-y-2">
                <Label htmlFor="new_password">Nova Password</Label>
                <div className="relative">
                  <Input
                    id="new_password"
                    type={showNewPassword ? "text" : "password"}
                    value={passwordData.new_password}
                    onChange={(e) => {
                      const newPassword = e.target.value;
                      setPasswordData({
                        ...passwordData,
                        new_password: newPassword,
                      });
                      validatePasswordStrength(newPassword);
                    }}
                    placeholder="Introduza a nova password"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="absolute right-0 top-0 h-full"
                    onClick={() => setShowNewPassword(!showNewPassword)}
                  >
                    {showNewPassword ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </Button>
                </div>
                {passwordStrength && (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-sm">
                      <span>Força da password:</span>
                      <span
                        className={`font-medium ${
                          passwordStrength.valid ? "text-green-600" : "text-orange-600"
                        }`}
                      >
                        {getStrengthLabel(passwordStrength.strength).label}
                      </span>
                    </div>
                    <div className="h-2 bg-muted rounded-full overflow-hidden">
                      <div
                        className={`h-full transition-all ${
                          getStrengthLabel(passwordStrength.strength).color
                        }`}
                        style={{ width: `${passwordStrength.score}%` }}
                      />
                    </div>
                    {passwordStrength.feedback.length > 0 && (
                      <ul className="text-xs text-muted-foreground space-y-1">
                        {passwordStrength.feedback.map((item, index) => (
                          <li key={index}>• {item}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="confirm_password">Confirmar Nova Password</Label>
                <div className="relative">
                  <Input
                    id="confirm_password"
                    type={showConfirmPassword ? "text" : "password"}
                    value={passwordData.confirm_password}
                    onChange={(e) =>
                      setPasswordData({
                        ...passwordData,
                        confirm_password: e.target.value,
                      })
                    }
                    placeholder="Confirme a nova password"
                    className="pr-9"
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                {passwordData.confirm_password &&
                  passwordData.new_password !== passwordData.confirm_password && (
                    <p className="text-xs text-destructive">
                      As passwords não coincidem
                    </p>
                  )}
              </div>
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setPasswordDialog(false);
                  setPasswordData({
                    current_password: "",
                    new_password: "",
                    confirm_password: "",
                  });
                  setPasswordStrength(null);
                }}
              >
                Cancelar
              </Button>
              <Button
                onClick={handleChangePassword}
                disabled={
                  changingPassword ||
                  !passwordData.current_password ||
                  !passwordData.new_password ||
                  passwordData.new_password !== passwordData.confirm_password ||
                  !passwordStrength?.valid
                }
              >
                {changingPassword ? "A alterar..." : "Alterar Password"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Dialog Confirmar Revogação de Sessão */}
        <AlertDialog
          open={!!sessionToRevoke}
          onOpenChange={() => setSessionToRevoke(null)}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Terminar Sessão</AlertDialogTitle>
              <AlertDialogDescription>
                Tem a certeza que deseja terminar esta sessão? O dispositivo terá
                de voltar a iniciar sessão.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancelar</AlertDialogCancel>
              <AlertDialogAction
                onClick={handleRevokeSession}
                disabled={revokingSession}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                {revokingSession ? "A terminar..." : "Terminar Sessão"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </DashboardLayout>
  );
};

export default ProfilePage;
