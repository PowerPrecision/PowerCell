/**
 * ProfilePage — Página de perfil do utilizador autenticado.
 *
 * PACOTE DF — Reestruturação com Shadcn Tabs (Global vs Per-Role):
 *   - Tab "Conta Global" (sempre presente): Informação de Login + Sessões
 *     Ativas. Contém configurações globais: password, sessões, role badge,
 *     "Membro desde".
 *   - Uma tab por UCR (user_company_roles) REAL: gerada dinamicamente a
 *     partir de `user.companies`. Cada tab renderiza o sub-componente
 *     <ProfileRoleTab> com os 3 Cards por-UCR (Dados Profissionais,
 *     Assinatura, Webmail).
 *
 * ANTES (Pacote W/K): pilha flat de 5 Cards. Tabs fantasma apareciam para
 * roles que o utilizador não tinha (effectiveRole hardcoded). AGORA: tabs
 * dinâmicas baseadas em UCRs reais persistidas no backend — sem "conta
 * principal" fantasma, sem roles inventados.
 *
 * @context {AuthContext} — Consome user, logout, refreshUser, effectiveRole
 */

import { useState, useEffect, useMemo } from "react";
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
// PACOTE DF — Shadcn Tabs para reestruturação Global vs Per-Role
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { toast } from "sonner";
import { useAuth } from "../contexts/AuthContext";
import { useNavigate } from "react-router-dom";
import api from "../services/api";
import { formatDateTime } from "../lib/utils";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import DashboardLayout from "../layouts/DashboardLayout";
// PACOTE DF — Role helpers centralizados (substituem getRoleLabel local)
import { ROLE_LABELS, ROLE_ICONS, normalizeRole, isSelectableRole } from "../utils/roleUtils";
// PACOTE DF — Sub-componente para as 3 cards por-UCR
import ProfileRoleTab from "../components/ProfileRoleTab";
import {
  Lock,
  Monitor,
  Trash2,
  Eye,
  EyeOff,
  LogOut,
  Clock,
  MapPin,
  ArrowLeft,
  Building2,
  User,
} from "lucide-react";

// ====================================================================
// PÁGINA DE PERFIL - ÁREA PESSOAL DO UTILIZADOR
// ====================================================================

const ProfilePage = () => {
  const { user, logout, refreshUser, effectiveRole } = useAuth();
  const navigate = useNavigate();

  // ── Tabs dinâmicas baseadas em UCRs reais (user.companies) ──
  // PACOTE DF — Sem hardcode de roles. Só renderiza perfis que o
  // utilizador realmente tem na coleção user_company_roles.
  // Filtro de "default" remove o perfil fantasma "Conta Principal".
  const ucrTabs = useMemo(() => {
    if (!user?.companies || user.companies.length === 0) return [];
    return user.companies
      .filter(c => isSelectableRole(c.role) && c.company_id && c.company_id !== "default")
      .map(c => {
        const role = normalizeRole(c.role);
        return {
          value: `${role}__${c.company_id}`,
          role,
          companyId: c.company_id,
          companyName: c.company_name || c.company_id,
          label: `${ROLE_LABELS[role] || role} @ ${c.company_name || c.company_id}`,
          icon: ROLE_ICONS[role],
        };
      });
  }, [user?.companies]);

  // Tab ativa — default "global" (mais seguro do que pré-seleccionar um UCR)
  const [activeTab, setActiveTab] = useState("global");

  // ── Estados para alteração de password (Conta Global) ──
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

  // ── Estados para sessões (Conta Global) ──
  const [sessions, setSessions] = useState([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [sessionToRevoke, setSessionToRevoke] = useState(null);
  const [revokingSession, setRevokingSession] = useState(false);

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
    } catch {
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
    } catch {
      toast.error("Não foi possível terminar as sessões.");
    } finally {
      setRevokingSession(false);
    }
  };

  // Traduzir força da password (estados legados mantidos)
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

        {/* PACOTE DF — Tabs: Conta Global + uma por UCR real */}
        <Tabs
          value={activeTab}
          onValueChange={setActiveTab}
          className="w-full"
        >
          <TabsList
            className="grid w-full"
            style={{
              gridTemplateColumns: `repeat(${1 + ucrTabs.length}, minmax(0, 1fr))`,
            }}
          >
            <TabsTrigger value="global" className="gap-1.5">
              <User className="h-4 w-4" />
              <span className="hidden sm:inline">Conta Global</span>
            </TabsTrigger>
            {ucrTabs.map((tab) => (
              <TabsTrigger
                key={tab.value}
                value={tab.value}
                className="gap-1.5"
              >
                {/* PACOTE DF — ROLE_ICONS é um emoji (string), não componente */}
                {tab.icon && (
                  <span className="text-base leading-none" aria-hidden>
                    {tab.icon}
                  </span>
                )}
                <span className="hidden sm:inline truncate">{tab.label}</span>
              </TabsTrigger>
            ))}
          </TabsList>

          {/* ── Tab: Conta Global ── */}
          <TabsContent value="global" className="space-y-6 mt-6">
            {/* Card: Informação de Login (comum a todos os perfis) */}
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
                {/* Role + Company badge (PACOTE DF — usa ROLE_LABELS centralizado) */}
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge variant="secondary">
                    {ROLE_LABELS[effectiveRole || user?.role] ||
                      effectiveRole ||
                      user?.role}
                  </Badge>
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

            {/* Card: Sessões Ativas */}
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

            {/* PACOTE DF — Fallback: sem UCRs reais, mostrar mensagem */}
            {ucrTabs.length === 0 && (
              <div className="p-4 rounded-lg border border-dashed border-border bg-muted/30 text-center">
                <p className="text-sm text-muted-foreground">
                  Não tem perfis atribuídos. Contacte um administrador para
                  configurar o seu acesso a uma empresa.
                </p>
              </div>
            )}
          </TabsContent>

          {/* ── Tabs: uma por UCR real (gerada dinamicamente) ── */}
          {ucrTabs.map((tab) => (
            <TabsContent
              key={tab.value}
              value={tab.value}
              className="space-y-6 mt-6"
            >
              <ProfileRoleTab
                companyId={tab.companyId}
                role={tab.role}
                companyName={tab.companyName}
                user={user}
                onUpdate={refreshUser}
              />
            </TabsContent>
          ))}
        </Tabs>

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
