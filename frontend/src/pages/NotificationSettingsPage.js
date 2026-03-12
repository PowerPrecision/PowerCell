/**
 * ====================================================================
 * PÁGINA DE CONFIGURAÇÃO DE NOTIFICAÇÕES - CREDITOIMO
 * ====================================================================
 * Permite ao admin configurar notificações e emails:
 * - Suas próprias preferências
 * - Preferências de outros utilizadores
 * - Marcar utilizadores como "teste" para não receberem emails
 * ====================================================================
 */

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Label } from "../components/ui/label";
import { Switch } from "../components/ui/switch";
import { Separator } from "../components/ui/separator";
import { Input } from "../components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import { Checkbox } from "../components/ui/checkbox";
import { toast } from "sonner";
import {
  Bell,
  Mail,
  Loader2,
  Save,
  Search,
  User,
  Users,
  Settings,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Filter,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Descrições das preferências
const PREFERENCE_LABELS = {
  email_new_process: { label: "Novo processo criado", category: "email" },
  email_status_change: { label: "Mudança de status", category: "email" },
  email_document_upload: { label: "Documento carregado", category: "email" },
  email_task_assigned: { label: "Tarefa atribuída", category: "email" },
  email_deadline_reminder: { label: "Lembrete de prazo", category: "email", important: true },
  email_urgent_only: { label: "Apenas notificações urgentes", category: "email", important: true },
  email_daily_summary: { label: "Resumo diário", category: "email", important: true },
  email_weekly_report: { label: "Relatório semanal", category: "email", important: true },
  inapp_new_process: { label: "Novo processo criado", category: "inapp" },
  inapp_status_change: { label: "Mudança de status", category: "inapp" },
  inapp_document_upload: { label: "Documento carregado", category: "inapp" },
  inapp_task_assigned: { label: "Tarefa atribuída", category: "inapp" },
  inapp_comments: { label: "Comentários", category: "inapp" },
  is_test_user: { label: "Utilizador de Teste (não recebe emails)", category: "special" },
};

export default function NotificationSettingsPage() {
  const { token, user } = useAuth();
  
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [users, setUsers] = useState([]);
  const [filteredUsers, setFilteredUsers] = useState([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedUser, setSelectedUser] = useState(null);
  const [preferences, setPreferences] = useState({});
  const [showDialog, setShowDialog] = useState(false);
  const [selectedForBulk, setSelectedForBulk] = useState([]);
  const [showBulkDialog, setShowBulkDialog] = useState(false);

  // Carregar lista de utilizadores com preferências
  const loadUsers = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/admin/notification-preferences`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      
      if (response.ok) {
        const data = await response.json();
        setUsers(data);
        setFilteredUsers(data);
      } else {
        toast.error("Erro ao carregar utilizadores");
      }
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro de conexão");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  // Filtrar utilizadores
  useEffect(() => {
    if (!searchTerm) {
      setFilteredUsers(users);
    } else {
      const term = searchTerm.toLowerCase();
      setFilteredUsers(users.filter(u => 
        u.email?.toLowerCase().includes(term) ||
        u.name?.toLowerCase().includes(term) ||
        u.role?.toLowerCase().includes(term)
      ));
    }
  }, [searchTerm, users]);

  // Carregar preferências de um utilizador
  const loadUserPreferences = async (userId) => {
    try {
      const response = await fetch(`${API_URL}/api/admin/notification-preferences/${userId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      
      if (response.ok) {
        const data = await response.json();
        setPreferences(data.preferences || {});
        setSelectedUser(data);
        setShowDialog(true);
      }
    } catch (error) {
      toast.error("Erro ao carregar preferências");
    }
  };

  // Guardar preferências
  const savePreferences = async () => {
    if (!selectedUser) return;
    
    setSaving(true);
    try {
      const response = await fetch(`${API_URL}/api/admin/notification-preferences/${selectedUser.user_id}`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(preferences),
      });
      
      if (response.ok) {
        toast.success("Preferências guardadas");
        setShowDialog(false);
        loadUsers();
      } else {
        toast.error("Erro ao guardar preferências");
      }
    } catch (error) {
      toast.error("Erro de conexão");
    } finally {
      setSaving(false);
    }
  };

  // Marcar como teste (bulk)
  const markAsTest = async (isTest) => {
    if (selectedForBulk.length === 0) return;
    
    setSaving(true);
    try {
      const response = await fetch(`${API_URL}/api/admin/notification-preferences/bulk-update`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          user_ids: selectedForBulk,
          preferences: { is_test_user: isTest }
        }),
      });
      
      if (response.ok) {
        const data = await response.json();
        toast.success(`${data.updated_count} utilizadores actualizados`);
        setSelectedForBulk([]);
        setShowBulkDialog(false);
        loadUsers();
      } else {
        toast.error("Erro ao actualizar utilizadores");
      }
    } catch (error) {
      toast.error("Erro de conexão");
    } finally {
      setSaving(false);
    }
  };

  // Toggle preferência
  const togglePreference = (key) => {
    setPreferences(prev => ({
      ...prev,
      [key]: !prev[key]
    }));
  };

  // Toggle selecção para bulk
  const toggleBulkSelection = (userId) => {
    setSelectedForBulk(prev => 
      prev.includes(userId) 
        ? prev.filter(id => id !== userId)
        : [...prev, userId]
    );
  };

  // Seleccionar todos filtrados
  const selectAllFiltered = () => {
    const allIds = filteredUsers.map(u => u.user_id);
    setSelectedForBulk(allIds);
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-96">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-6" data-testid="notification-settings-page">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Bell className="h-6 w-6 text-primary" />
              Configuração de Notificações
            </h1>
            <p className="text-muted-foreground mt-1">
              Controle quem recebe emails e notificações
            </p>
          </div>
          
          {selectedForBulk.length > 0 && (
            <div className="flex items-center gap-2">
              <Badge variant="secondary">{selectedForBulk.length} seleccionados</Badge>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowBulkDialog(true)}
              >
                <Settings className="h-4 w-4 mr-2" />
                Acções em Massa
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSelectedForBulk([])}
              >
                <XCircle className="h-4 w-4" />
              </Button>
            </div>
          )}
        </div>

        {/* Info Card */}
        <Card className="bg-blue-50 dark:bg-blue-950 border-blue-200 dark:border-blue-800">
          <CardContent className="pt-4">
            <div className="flex items-start gap-3">
              <Mail className="h-5 w-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
              <div className="text-sm">
                <p className="font-medium text-blue-800 dark:text-blue-200 mb-1">
                  Sobre Emails e Notificações
                </p>
                <ul className="list-disc list-inside space-y-1 text-blue-700 dark:text-blue-300">
                  <li><strong>Emails</strong> - Enviados para o email do utilizador (pode ser desactivado)</li>
                  <li><strong>Notificações In-App</strong> - Aparecem dentro da aplicação</li>
                  <li><strong>Utilizadores de Teste</strong> - Não recebem nenhum email</li>
                </ul>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Search and Filter */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Users className="h-4 w-4" />
              Utilizadores ({filteredUsers.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2 mb-4">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Pesquisar por nome, email ou role..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-10"
                />
              </div>
              <Button variant="outline" size="sm" onClick={selectAllFiltered}>
                Seleccionar Todos
              </Button>
            </div>

            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12"></TableHead>
                  <TableHead>Utilizador</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead className="text-center">Recebe Emails</TableHead>
                  <TableHead className="text-center">Teste</TableHead>
                  <TableHead className="text-right">Acções</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredUsers.map((u) => (
                  <TableRow key={u.user_id}>
                    <TableCell>
                      <Checkbox
                        checked={selectedForBulk.includes(u.user_id)}
                        onCheckedChange={() => toggleBulkSelection(u.user_id)}
                      />
                    </TableCell>
                    <TableCell>
                      <div>
                        <p className="font-medium">{u.name || "Sem nome"}</p>
                        <p className="text-sm text-muted-foreground">{u.email}</p>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{u.role}</Badge>
                    </TableCell>
                    <TableCell className="text-center">
                      {u.receives_email ? (
                        <CheckCircle className="h-5 w-5 text-green-500 mx-auto" />
                      ) : (
                        <XCircle className="h-5 w-5 text-muted-foreground mx-auto" />
                      )}
                    </TableCell>
                    <TableCell className="text-center">
                      {u.is_test_user ? (
                        <Badge variant="secondary" className="bg-amber-100 text-amber-800">
                          <AlertTriangle className="h-3 w-3 mr-1" />
                          Teste
                        </Badge>
                      ) : null}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => loadUserPreferences(u.user_id)}
                      >
                        <Settings className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        {/* Dialog de Preferências */}
        <Dialog open={showDialog} onOpenChange={setShowDialog}>
          <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <User className="h-5 w-5" />
                Preferências de {selectedUser?.user_name || selectedUser?.user_email}
              </DialogTitle>
              <DialogDescription>
                Configure quais notificações e emails este utilizador recebe
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-6 py-4">
              {/* Utilizador de Teste */}
              <div className="p-4 border rounded-lg bg-amber-50 dark:bg-amber-950">
                <div className="flex items-center justify-between">
                  <div>
                    <Label className="text-base font-medium">Utilizador de Teste</Label>
                    <p className="text-sm text-muted-foreground">
                      Utilizadores de teste não recebem nenhum email
                    </p>
                  </div>
                  <Switch
                    checked={preferences.is_test_user || false}
                    onCheckedChange={() => togglePreference("is_test_user")}
                  />
                </div>
              </div>

              <Separator />

              {/* Emails */}
              <div className="space-y-4">
                <h3 className="font-semibold flex items-center gap-2">
                  <Mail className="h-4 w-4" />
                  Notificações por Email
                </h3>
                
                <div className="grid gap-3">
                  {Object.entries(PREFERENCE_LABELS)
                    .filter(([_, v]) => v.category === "email")
                    .map(([key, info]) => (
                      <div key={key} className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-muted/50">
                        <div className="flex items-center gap-2">
                          <Label className="cursor-pointer">
                            {info.label}
                          </Label>
                          {info.important && (
                            <Badge variant="outline" className="text-xs">Importante</Badge>
                          )}
                        </div>
                        <Switch
                          checked={preferences[key] || false}
                          onCheckedChange={() => togglePreference(key)}
                          disabled={preferences.is_test_user}
                        />
                      </div>
                    ))
                  }
                </div>
              </div>

              <Separator />

              {/* In-App */}
              <div className="space-y-4">
                <h3 className="font-semibold flex items-center gap-2">
                  <Bell className="h-4 w-4" />
                  Notificações In-App
                </h3>
                
                <div className="grid gap-3">
                  {Object.entries(PREFERENCE_LABELS)
                    .filter(([_, v]) => v.category === "inapp")
                    .map(([key, info]) => (
                      <div key={key} className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-muted/50">
                        <Label className="cursor-pointer">{info.label}</Label>
                        <Switch
                          checked={preferences[key] || false}
                          onCheckedChange={() => togglePreference(key)}
                        />
                      </div>
                    ))
                  }
                </div>
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setShowDialog(false)}>
                Cancelar
              </Button>
              <Button onClick={savePreferences} disabled={saving}>
                {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
                Guardar
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Dialog de Acções em Massa */}
        <Dialog open={showBulkDialog} onOpenChange={setShowBulkDialog}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Acções em Massa</DialogTitle>
              <DialogDescription>
                Aplicar alterações a {selectedForBulk.length} utilizadores seleccionados
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-4">
              <Button
                variant="outline"
                className="w-full justify-start"
                onClick={() => markAsTest(true)}
                disabled={saving}
              >
                <AlertTriangle className="h-4 w-4 mr-2 text-amber-500" />
                Marcar como Utilizadores de Teste
                <span className="text-xs text-muted-foreground ml-auto">
                  (não recebem emails)
                </span>
              </Button>
              
              <Button
                variant="outline"
                className="w-full justify-start"
                onClick={() => markAsTest(false)}
                disabled={saving}
              >
                <CheckCircle className="h-4 w-4 mr-2 text-green-500" />
                Remover Marca de Teste
                <span className="text-xs text-muted-foreground ml-auto">
                  (voltam a receber emails)
                </span>
              </Button>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setShowBulkDialog(false)}>
                Cancelar
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </DashboardLayout>
  );
}
