/**
 * ====================================================================
 * PÁGINA DE DEFINIÇÕES - CREDITOIMO
 * ====================================================================
 * Página de configurações do sistema e perfil do utilizador.
 * 
 * Funcionalidades:
 * - Editar dados do perfil
 * - Alterar password
 * - Preferências de notificações
 * - Configurações de visualização (apenas Admin)
 * - Gestão de workflow (apenas Admin)
 * ====================================================================
 */

import { useState, useEffect } from "react";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Switch } from "../components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Separator } from "../components/ui/separator";
import { toast } from "sonner";
import {
  User,
  Lock,
  Bell,
  Palette,
  Settings,
  Save,
  Eye,
  EyeOff,
  Mail,
  Phone,
  Building2,
  Shield,
  Workflow,
  Loader2,
} from "lucide-react";
import WorkflowEditor from "../components/WorkflowEditor";
import NotificationSettings from "../components/NotificationSettings";
import TrelloIntegration from "../components/TrelloIntegration";
import BulkDocumentUpload from "../components/BulkDocumentUpload";

const API_URL = process.env.REACT_APP_BACKEND_URL || "";

const SettingsPage = () => {
  const { user, token } = useAuth();
  
  // Estado do perfil
  const [profileData, setProfileData] = useState({
    name: "",
    email: "",
    phone: "",
  });
  
  // Estado da password
  const [passwordData, setPasswordData] = useState({
    current_password: "",
    new_password: "",
    confirm_password: "",
  });
  const [showPasswords, setShowPasswords] = useState({
    current: false,
    new: false,
    confirm: false,
  });
  
  // Estado das notificações
  const [notifications, setNotifications] = useState({
    email_new_process: true,
    email_status_change: true,
    email_document_expiry: true,
    email_deadline_reminder: true,
  });
  const [loadingPreferences, setLoadingPreferences] = useState(true);
  
  // Estado de loading
  const [loading, setLoading] = useState(false);
  
  // Carregar dados do utilizador
  useEffect(() => {
    if (user) {
      setProfileData({
        name: user.name || "",
        email: user.email || "",
        phone: user.phone || "",
      });
    }
  }, [user]);
  
  // Carregar preferências de notificação
  useEffect(() => {
    const loadPreferences = async () => {
      if (!token) return;
      try {
        const response = await fetch(`${API_URL}/api/auth/preferences`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (response.ok) {
          const data = await response.json();
          if (data.notifications) {
            setNotifications(prev => ({
              ...prev,
              ...data.notifications
            }));
          }
        }
      } catch (error) {
        console.error("Erro ao carregar preferências:", error);
      } finally {
        setLoadingPreferences(false);
      }
    };
    loadPreferences();
  }, [token]);
  
  // Guardar perfil
  const handleSaveProfile = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/auth/profile`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: profileData.name,
          phone: profileData.phone,
        }),
      });
      
      if (response.ok) {
        toast.success("Perfil atualizado com sucesso");
      } else {
        const data = await response.json();
        throw new Error(data.detail || "Erro ao atualizar perfil");
      }
    } catch (error) {
      toast.error(error.message || "Não foi possível atualizar o perfil");
    } finally {
      setLoading(false);
    }
  };
  
  // Alterar password
  const handleChangePassword = async () => {
    if (passwordData.new_password !== passwordData.confirm_password) {
      toast.error("As passwords não coincidem");
      return;
    }
    
    if (passwordData.new_password.length < 6) {
      toast.error("A password deve ter pelo menos 6 caracteres");
      return;
    }
    
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/auth/change-password`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          current_password: passwordData.current_password,
          new_password: passwordData.new_password,
        }),
      });
      
      if (response.ok) {
        toast.success("Password alterada com sucesso");
        setPasswordData({
          current_password: "",
          new_password: "",
          confirm_password: "",
        });
      } else {
        const data = await response.json();
        throw new Error(data.detail || "Erro ao alterar password");
      }
    } catch (error) {
      toast.error(error.message || "Não foi possível alterar a password");
    } finally {
      setLoading(false);
    }
  };
  
  // Guardar notificações
  const handleSaveNotifications = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/auth/preferences`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ notifications }),
      });
      
      if (response.ok) {
        toast.success("Preferências de notificação guardadas!");
      } else {
        throw new Error("Erro ao guardar preferências");
      }
    } catch (error) {
      toast.error("Não foi possível guardar as preferências");
    } finally {
      setLoading(false);
    }
  };
  
  // Obter label do papel
  const getRoleLabel = (role) => {
    const labels = {
      admin: "Administrador",
      ceo: "CEO",
      consultor: "Consultor",
      intermediario: "Intermediário de Crédito",
      mediador: "Mediador",
      consultor_intermediario: "Consultor/Intermediário",
      cliente: "Cliente",
    };
    return labels[role] || role;
  };

  return (
    <DashboardLayout title="Definições">
      <div className="p-6">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-blue-950">Definições</h1>
          <p className="text-muted-foreground">
            Gerir as configurações da sua conta e preferências
          </p>
        </div>

        <Tabs defaultValue="perfil" className="space-y-6">
          <TabsList className="bg-blue-50 border border-blue-200">
            <TabsTrigger value="perfil" className="data-[state=active]:bg-teal-600 data-[state=active]:text-white">
              <User className="h-4 w-4 mr-2" />
              Perfil
            </TabsTrigger>
            <TabsTrigger value="seguranca" className="data-[state=active]:bg-teal-600 data-[state=active]:text-white">
              <Lock className="h-4 w-4 mr-2" />
              Segurança
            </TabsTrigger>
            <TabsTrigger value="notificacoes" className="data-[state=active]:bg-teal-600 data-[state=active]:text-white">
              <Bell className="h-4 w-4 mr-2" />
              Notificações
            </TabsTrigger>
            {user?.role === "admin" && (
              <TabsTrigger value="sistema" className="data-[state=active]:bg-teal-600 data-[state=active]:text-white">
                <Settings className="h-4 w-4 mr-2" />
                Sistema
              </TabsTrigger>
            )}
          </TabsList>

          {/* Tab Perfil */}
          <TabsContent value="perfil">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <User className="h-5 w-5 text-blue-900" />
                  Informações do Perfil
                </CardTitle>
                <CardDescription>
                  Atualize os seus dados pessoais
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* Informação do papel */}
                <div className="flex items-center gap-4 p-4 bg-blue-50 rounded-lg border border-blue-200">
                  <div className="h-12 w-12 rounded-full bg-teal-600 flex items-center justify-center">
                    <Shield className="h-6 w-6 text-white" />
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">O seu papel no sistema</p>
                    <p className="font-semibold text-blue-900">{getRoleLabel(user?.role)}</p>
                  </div>
                </div>

                <Separator />

                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="name">Nome Completo</Label>
                    <div className="relative">
                      <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                      <Input
                        id="name"
                        value={profileData.name}
                        onChange={(e) => setProfileData({ ...profileData, name: e.target.value })}
                        className="pl-10"
                        placeholder="O seu nome"
                      />
                    </div>
                  </div>
                  
                  <div className="space-y-2">
                    <Label htmlFor="email">Email</Label>
                    <div className="relative">
                      <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                      <Input
                        id="email"
                        type="email"
                        value={profileData.email}
                        disabled
                        className="pl-10 bg-muted"
                      />
                    </div>
                    <p className="text-xs text-muted-foreground">O email não pode ser alterado</p>
                  </div>
                  
                  <div className="space-y-2">
                    <Label htmlFor="phone">Telefone</Label>
                    <div className="relative">
                      <Phone className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                      <Input
                        id="phone"
                        value={profileData.phone}
                        onChange={(e) => setProfileData({ ...profileData, phone: e.target.value })}
                        className="pl-10"
                        placeholder="+351 912 345 678"
                      />
                    </div>
                  </div>
                </div>

                <div className="flex justify-end">
                  <Button 
                    onClick={handleSaveProfile} 
                    disabled={loading}
                    className="bg-teal-600 hover:bg-teal-700"
                  >
                    <Save className="h-4 w-4 mr-2" />
                    Guardar Alterações
                  </Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Tab Segurança */}
          <TabsContent value="seguranca">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Lock className="h-5 w-5 text-blue-900" />
                  Alterar Password
                </CardTitle>
                <CardDescription>
                  Mantenha a sua conta segura atualizando a password regularmente
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="space-y-4 max-w-md">
                  <div className="space-y-2">
                    <Label htmlFor="current_password">Password Atual</Label>
                    <div className="relative">
                      <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                      <Input
                        id="current_password"
                        type={showPasswords.current ? "text" : "password"}
                        value={passwordData.current_password}
                        onChange={(e) => setPasswordData({ ...passwordData, current_password: e.target.value })}
                        className="pl-10 pr-10"
                        placeholder="••••••••"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPasswords({ ...showPasswords, current: !showPasswords.current })}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      >
                        {showPasswords.current ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>
                  
                  <div className="space-y-2">
                    <Label htmlFor="new_password">Nova Password</Label>
                    <div className="relative">
                      <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                      <Input
                        id="new_password"
                        type={showPasswords.new ? "text" : "password"}
                        value={passwordData.new_password}
                        onChange={(e) => setPasswordData({ ...passwordData, new_password: e.target.value })}
                        className="pl-10 pr-10"
                        placeholder="••••••••"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPasswords({ ...showPasswords, new: !showPasswords.new })}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      >
                        {showPasswords.new ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>
                  
                  <div className="space-y-2">
                    <Label htmlFor="confirm_password">Confirmar Nova Password</Label>
                    <div className="relative">
                      <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                      <Input
                        id="confirm_password"
                        type={showPasswords.confirm ? "text" : "password"}
                        value={passwordData.confirm_password}
                        onChange={(e) => setPasswordData({ ...passwordData, confirm_password: e.target.value })}
                        className="pl-10 pr-10"
                        placeholder="••••••••"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPasswords({ ...showPasswords, confirm: !showPasswords.confirm })}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      >
                        {showPasswords.confirm ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>
                </div>

                <div className="flex justify-end">
                  <Button 
                    onClick={handleChangePassword} 
                    disabled={loading || !passwordData.current_password || !passwordData.new_password}
                    className="bg-teal-600 hover:bg-teal-700"
                  >
                    <Lock className="h-4 w-4 mr-2" />
                    Alterar Password
                  </Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Tab Notificações */}
          <TabsContent value="notificacoes">
            <div className="space-y-6">
              {/* Push Notifications */}
              <NotificationSettings />
              
              {/* Email Notifications */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Mail className="h-5 w-5 text-blue-900" />
                    Notificações por Email
                  </CardTitle>
                  <CardDescription>
                    Escolha quando deseja receber emails
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="space-y-4">
                    <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
                      <div className="space-y-0.5">
                        <p className="font-medium">Novo Processo</p>
                        <p className="text-sm text-muted-foreground">
                          Receber email quando um novo processo for criado
                        </p>
                      </div>
                      <Switch
                        checked={notifications.email_new_process}
                        onCheckedChange={(checked) => 
                          setNotifications({ ...notifications, email_new_process: checked })
                        }
                      />
                    </div>
                    
                    <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
                      <div className="space-y-0.5">
                        <p className="font-medium">Mudança de Estado</p>
                        <p className="text-sm text-muted-foreground">
                          Receber email quando o estado de um processo mudar
                        </p>
                      </div>
                      <Switch
                        checked={notifications.email_status_change}
                        onCheckedChange={(checked) => 
                          setNotifications({ ...notifications, email_status_change: checked })
                        }
                      />
                    </div>
                    
                    <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
                      <div className="space-y-0.5">
                        <p className="font-medium">Documentos a Expirar</p>
                        <p className="text-sm text-muted-foreground">
                          Receber alerta quando documentos estiverem próximos de expirar (60 dias)
                        </p>
                      </div>
                      <Switch
                        checked={notifications.email_document_expiry}
                        onCheckedChange={(checked) => 
                          setNotifications({ ...notifications, email_document_expiry: checked })
                        }
                      />
                    </div>
                    
                    <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
                      <div className="space-y-0.5">
                        <p className="font-medium">Lembretes de Prazos</p>
                        <p className="text-sm text-muted-foreground">
                          Receber lembretes de eventos e prazos agendados
                        </p>
                      </div>
                      <Switch
                        checked={notifications.email_deadline_reminder}
                        onCheckedChange={(checked) => 
                          setNotifications({ ...notifications, email_deadline_reminder: checked })
                        }
                      />
                    </div>
                  </div>

                  <div className="flex justify-end">
                    <Button 
                      onClick={handleSaveNotifications}
                      disabled={loading}
                      className="bg-teal-600 hover:bg-teal-700"
                    >
                      {loading ? (
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      ) : (
                        <Save className="h-4 w-4 mr-2" />
                      )}
                      Guardar Preferências
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Tab Sistema (apenas Admin) */}
          {user?.role === "admin" && (
            <TabsContent value="sistema">
              <div className="space-y-6">
                {/* Análise de Documentos com IA */}
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Settings className="h-5 w-5 text-purple-500" />
                      Análise de Documentos com IA
                    </CardTitle>
                    <CardDescription>
                      Upload massivo de documentos para preenchimento automático das fichas de clientes
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-center justify-between p-4 bg-purple-50 rounded-lg border border-purple-100">
                      <div>
                        <p className="font-medium">Upload Massivo</p>
                        <p className="text-sm text-muted-foreground">
                          Selecione uma pasta com subpastas de clientes. A IA analisa CC, recibos, IRS e outros documentos.
                        </p>
                      </div>
                      <BulkDocumentUpload />
                    </div>
                  </CardContent>
                </Card>

                {/* Integração Trello */}
                <TrelloIntegration />
                
                {/* Editor de Workflow */}
                <WorkflowEditor />
                
                {/* Informação do Sistema */}
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Building2 className="h-5 w-5 text-blue-900" />
                      Informação do Sistema
                    </CardTitle>
                    <CardDescription>
                      Detalhes técnicos
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                      <div className="p-4 bg-muted/30 rounded-lg">
                        <p className="text-sm text-muted-foreground">Versão</p>
                        <p className="font-semibold text-lg">2.1.0</p>
                      </div>
                      <div className="p-4 bg-muted/30 rounded-lg">
                        <p className="text-sm text-muted-foreground">Ambiente</p>
                        <p className="font-semibold text-lg">Produção</p>
                      </div>
                      <div className="p-4 bg-muted/30 rounded-lg">
                        <p className="text-sm text-muted-foreground">Base de Dados</p>
                        <p className="font-semibold text-lg">MongoDB</p>
                      </div>
                      <div className="p-4 bg-muted/30 rounded-lg">
                        <p className="text-sm text-muted-foreground">Última Atualização</p>
                        <p className="font-semibold text-lg">Janeiro 2026</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </TabsContent>
          )}
        </Tabs>
      </div>
    </DashboardLayout>
  );
};

export default SettingsPage;
