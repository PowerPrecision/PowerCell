/**
 * ProfilePage — Página de perfil do utilizador autenticado.
 *
 * PORQUÊ: Permite ao utilizador consultar e editar dados pessoais e alterar a password.
 *
 * @context {AuthContext} — Consome user, token para autenticação e permissões
 */

import React, { useState, useEffect } from "react";
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
import { toast } from "../hooks/use-toast";
import { useAuth } from "../contexts/AuthContext";
import { useNavigate } from "react-router-dom";
import api from "../services/api";
import DashboardLayout from "../layouts/DashboardLayout";
import EmailConfigForm from "../components/EmailConfigForm";
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
} from "lucide-react";

// ====================================================================
// PÁGINA DE PERFIL - ÁREA PESSOAL DO UTILIZADOR
// ====================================================================

const ProfilePage = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  // Estados para dados do perfil
  const [profileData, setProfileData] = useState({
    name: "",
    phone: "",
    email: "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

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

  // Carregar dados do utilizador
  useEffect(() => {
    if (user) {
      setProfileData({
        name: user.name || "",
        phone: user.phone || "",
        email: user.email || "",
      });
      setLoading(false);
    }
  }, [user]);

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
  const loadEmailConfigInfo = async () => {
    setLoadingEmailConfig(true);
    try {
      const response = await api.get("/users/me/email-config");
      setEmailConfigInfo(response.data);
    } catch (error) {
      setEmailConfigInfo(null);
    } finally {
      setLoadingEmailConfig(false);
    }
  };

  useEffect(() => {
    loadEmailConfigInfo();
  }, []);

  // Guardar alterações do perfil
  const handleSaveProfile = async () => {
    setSaving(true);
    try {
      const response = await api.put("/auth/profile", {
        name: profileData.name,
        phone: profileData.phone,
      });
      toast({
        title: "Perfil atualizado",
        description: "Os seus dados foram atualizados com sucesso.",
      });
      // Actualizar o estado local
      if (response.data.user) {
        setProfileData({
          ...profileData,
          name: response.data.user.name || profileData.name,
          phone: response.data.user.phone || profileData.phone,
        });
      }
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Erro ao atualizar",
        description: error.response?.data?.detail || "Não foi possível atualizar o perfil.",
      });
    } finally {
      setSaving(false);
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
      toast({
        variant: "destructive",
        title: "Erro",
        description: "As passwords não coincidem.",
      });
      return;
    }

    setChangingPassword(true);
    try {
      await api.post("/auth/change-password", {
        current_password: passwordData.current_password,
        new_password: passwordData.new_password,
      });
      toast({
        title: "Password alterada",
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
      toast({
        variant: "destructive",
        title: "Erro ao alterar password",
        description: error.response?.data?.detail || "Não foi possível alterar a password.",
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
      toast({
        title: "Sessão terminada",
        description: "A sessão foi terminada com sucesso.",
      });
      loadSessions();
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Erro",
        description: "Não foi possível terminar a sessão.",
      });
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
      toast({
        title: "Sessões terminadas",
        description: "Todas as outras sessões foram terminadas.",
      });
      loadSessions();
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Erro",
        description: "Não foi possível terminar as sessões.",
      });
    } finally {
      setRevokingSession(false);
    }
  };

  // Formatar data
  const formatDate = (dateString) => {
    if (!dateString) return "-";
    return new Date(dateString).toLocaleString("pt-PT", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

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
      mediador: "Mediador",
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

        {/* Informação do Perfil */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <User className="h-5 w-5" />
              Informação do Perfil
            </CardTitle>
            <CardDescription>
              Atualize os seus dados pessoais
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="name">Nome</Label>
                <Input
                  id="name"
                  value={profileData.name}
                  onChange={(e) =>
                    setProfileData({ ...profileData, name: e.target.value })
                  }
                  placeholder="O seu nome"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="phone">Telefone</Label>
                <Input
                  id="phone"
                  value={profileData.phone}
                  onChange={(e) =>
                    setProfileData({ ...profileData, phone: e.target.value })
                  }
                  placeholder="O seu telefone"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                value={profileData.email}
                disabled
                className="bg-muted"
              />
              <p className="text-xs text-muted-foreground">
                O email não pode ser alterado. Contacte o administrador se precisar de mudar.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="secondary">{getRoleLabel(user?.role)}</Badge>
              <span className="text-sm text-muted-foreground">
                Membro desde {formatDate(user?.created_at)}
              </span>
            </div>
            <Button onClick={handleSaveProfile} disabled={saving} className="gap-2">
              <Save className="h-4 w-4" />
              {saving ? "A guardar..." : "Guardar Alterações"}
            </Button>
          </CardContent>
        </Card>

        {/* Segurança */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Lock className="h-5 w-5" />
              Segurança
            </CardTitle>
            <CardDescription>
              Altere a sua password e gerir sessões ativas
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between p-4 border rounded-lg">
              <div>
                <h3 className="font-medium">Password</h3>
                <p className="text-sm text-muted-foreground">
                  Altere a sua password de acesso
                </p>
              </div>
              <Button variant="outline" onClick={() => setPasswordDialog(true)}>
                Alterar Password
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Sessões Ativas */}
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
                            {formatDate(session.created_at)}
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

        {/* Configuração de Webmail */}
        {user?.role === "indexacao" ? (
          /* ── BLOQUEIO: Indexação — config gerida centralmente ── */
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
              <EmailConfigForm mode="self" />
            </CardContent>
          </Card>
        )}

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

