/**
 * ProfileSettingsPage - Configurações de Perfis e Permissões
 * 
 * ACESSO: Admin e CEO apenas
 * 
 * Funcionalidades:
 * - Listar todos os utilizadores
 * - Alterar role do utilizador
 * - Gerir permissões de acesso por utilizador
 * - Ativar/desativar utilizador
 * - Sincronização automática de permissões com role
 */
import React, { useState, useEffect, useCallback } from "react";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Badge } from "../components/ui/badge";
import { Switch } from "../components/ui/switch";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "../components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../components/ui/select";
import { toast } from "sonner";
import {
  Settings, Users, Shield, Search, Loader2, Save, ChevronRight, UserCog, Lock, Eye, EyeOff, RefreshCw, AlertCircle
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

const ROLES = [
  { value: "admin", label: "Administrador", color: "bg-red-100 text-red-800" },
  { value: "ceo", label: "CEO", color: "bg-purple-100 text-purple-800" },
  { value: "diretor", label: "Diretor", color: "bg-blue-100 text-blue-800" },
  { value: "consultor", label: "Consultor", color: "bg-green-100 text-green-800" },
  { value: "intermediario", label: "Intermediário", color: "bg-cyan-100 text-cyan-800" },
  { value: "administrativo", label: "Administrativo", color: "bg-amber-100 text-amber-800" },
  { value: "indexacao", label: "Indexação", color: "bg-gray-100 text-gray-800" },
];

const AVAILABLE_PAGES = [
  { key: "dashboard", label: "Dashboard" },
  { key: "kanban", label: "Quadro Kanban" },
  { key: "processes", label: "Processos" },
  { key: "clients", label: "Clientes" },
  { key: "registrations", label: "Registos de Clientes" },
  { key: "documents", label: "Documentos" },
  { key: "calendar", label: "Calendário" },
  { key: "notifications", label: "Notificações" },
  { key: "stats", label: "Estatísticas" },
  { key: "users", label: "Gestão Utilizadores" },
  { key: "workflow", label: "Workflow / Estados" },
  { key: "automation", label: "Automação" },
  { key: "email_search", label: "Pesquisa Emails" },
  { key: "ai_insights", label: "IA / Insights" },
  { key: "system_config", label: "Configurações Sistema" },
  // Páginas adicionais em falta
  { key: "properties", label: "Imóveis" },
  { key: "minutas", label: "Minutas" },
  { key: "validades", label: "Validades Docs" },
  { key: "rgpd", label: "RGPD" },
  { key: "backups", label: "Backups" },
  { key: "logs", label: "Logs do Sistema" },
  { key: "diagnostics", label: "Diagnósticos" },
  { key: "background_jobs", label: "Processos Background" },
  { key: "leads", label: "Gestor de Visitas" },
  { key: "permissions", label: "Perfis e Permissões" },
  { key: "form_manager", label: "Gestão do Formulário" },
];

const AVAILABLE_ACTIONS = [
  { key: "create_process", label: "Criar Processos" },
  { key: "edit_process", label: "Editar Processos" },
  { key: "delete_process", label: "Eliminar Processos" },
  { key: "create_client", label: "Criar Clientes" },
  { key: "edit_client", label: "Editar Clientes" },
  { key: "delete_client", label: "Eliminar Clientes" },
  { key: "upload_docs", label: "Upload Documentos" },
  { key: "delete_docs", label: "Eliminar Documentos" },
  { key: "manage_users", label: "Gerir Utilizadores" },
  { key: "view_financials", label: "Ver Dados Financeiros" },
  { key: "export_data", label: "Exportar Dados" },
  { key: "assign_clients", label: "Atribuir Clientes" },
  // Ações adicionais em falta
  { key: "manage_backups", label: "Gerir Backups" },
  { key: "view_logs", label: "Ver Logs do Sistema" },
  { key: "manage_properties", label: "Gerir Imóveis" },
  { key: "manage_minutas", label: "Gerir Minutas" },
  { key: "manage_leads", label: "Gerir Leads" },
  { key: "manage_rgpd", label: "Gerir RGPD" },
  { key: "manage_workflow", label: "Gerir Estados Workflow" },
  { key: "manage_automation", label: "Gerir Automações" },
  { key: "view_reports", label: "Ver Relatórios" },
  { key: "manage_ai", label: "Gerir Configurações IA" },
];

const ProfileSettingsPage = ({ embedded = false }) => {
  const { token } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [editDialog, setEditDialog] = useState({ open: false, user: null });
  const [editForm, setEditForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [defaultPermissions, setDefaultPermissions] = useState({});
  const [permissionsModified, setPermissionsModified] = useState(false);

  // Carregar permissões padrão do backend
  const fetchDefaultPermissions = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/admin/permissions/defaults`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setDefaultPermissions(data.defaults || {});
      }
    } catch (err) {
      console.error("Erro ao carregar permissões padrão:", err);
    }
  }, [token]);

  const fetchUsers = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/admin/users`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setUsers(data);
      }
    } catch (err) {
      console.error(err);
      toast.error("Erro ao carregar utilizadores");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { 
    fetchUsers(); 
    fetchDefaultPermissions();
  }, [fetchUsers, fetchDefaultPermissions]);

  const openEditDialog = (user) => {
    const perms = user.permissions || {};
    setEditForm({
      role: user.role,
      originalRole: user.role, // Guardar o role original para detectar mudanças
      is_active: user.is_active !== false,
      pages: perms.pages || AVAILABLE_PAGES.map(p => p.key),
      actions: perms.actions || AVAILABLE_ACTIONS.map(a => a.key),
      originalPages: perms.pages || AVAILABLE_PAGES.map(p => p.key),
      originalActions: perms.actions || AVAILABLE_ACTIONS.map(a => a.key),
    });
    setPermissionsModified(false);
    setEditDialog({ open: true, user });
  };

  // Aplicar permissões padrão do role selecionado
  const applyDefaultPermissions = (role) => {
    if (defaultPermissions[role]) {
      setEditForm(prev => ({
        ...prev,
        pages: defaultPermissions[role].pages || [],
        actions: defaultPermissions[role].actions || [],
      }));
      setPermissionsModified(true);
      toast.info(`Permissões aplicadas para o perfil ${ROLES.find(r => r.value === role)?.label || role}`);
    }
  };

  // Handle role change - sincronizar permissões automaticamente
  const handleRoleChange = (newRole) => {
    const roleChanged = newRole !== editForm.originalRole;
    
    setEditForm(prev => ({
      ...prev,
      role: newRole,
    }));

    // Se o role mudou, perguntar se quer aplicar as permissões padrão
    if (roleChanged && defaultPermissions[newRole]) {
      // Aplicar automaticamente as permissões padrão do novo role
      applyDefaultPermissions(newRole);
    }
  };

  // Redefinir permissões para o padrão do role atual
  const resetToDefault = () => {
    applyDefaultPermissions(editForm.role);
  };

  const handleSave = async () => {
    if (!editDialog.user) return;
    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/users/${editDialog.user.id}`, {
        method: "PUT",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          role: editForm.role,
          is_active: editForm.is_active,
          permissions: {
            pages: editForm.pages,
            actions: editForm.actions,
          },
        }),
      });
      if (res.ok) {
        toast.success("Permissões atualizadas com sucesso");
        setEditDialog({ open: false, user: null });
        fetchUsers();
      } else {
        const err = await res.json();
        toast.error(err.detail || "Erro ao atualizar");
      }
    } catch {
      toast.error("Erro de rede");
    } finally {
      setSaving(false);
    }
  };

  const togglePage = (key) => {
    setEditForm(prev => ({
      ...prev,
      pages: prev.pages.includes(key)
        ? prev.pages.filter(p => p !== key)
        : [...prev.pages, key]
    }));
    setPermissionsModified(true);
  };

  const toggleAction = (key) => {
    setEditForm(prev => ({
      ...prev,
      actions: prev.actions.includes(key)
        ? prev.actions.filter(a => a !== key)
        : [...prev.actions, key]
    }));
    setPermissionsModified(true);
  };

  const getRoleInfo = (role) => ROLES.find(r => r.value === role) || { label: role, color: "bg-gray-100 text-gray-800" };

  // Verificar se as permissões são personalizadas (diferentes do padrão do role)
  const hasCustomPermissions = (user) => {
    if (!user.permissions) return false;
    const roleDefaults = defaultPermissions[user.role];
    if (!roleDefaults) return !!user.permissions;
    
    const userPages = (user.permissions.pages || []).sort().join(',');
    const userActions = (user.permissions.actions || []).sort().join(',');
    const defaultPages = (roleDefaults.pages || []).sort().join(',');
    const defaultActions = (roleDefaults.actions || []).sort().join(',');
    
    return userPages !== defaultPages || userActions !== defaultActions;
  };

  const filtered = users.filter(u =>
    u.name?.toLowerCase().includes(search.toLowerCase()) ||
    u.email?.toLowerCase().includes(search.toLowerCase()) ||
    u.role?.toLowerCase().includes(search.toLowerCase())
  );

  const wrapLayout = (children) => embedded ? children : <DashboardLayout>{children}</DashboardLayout>;
  return wrapLayout(
    <div className="space-y-6" data-testid="profile-settings-page">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Shield className="h-6 w-6" />
              Configurações de Perfis
            </h1>
            <p className="text-muted-foreground mt-1">Gerir permissões de acesso dos utilizadores</p>
          </div>
        </div>

        <div className="relative max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Pesquisar utilizador..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
            data-testid="search-users"
          />
        </div>

        {loading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="grid gap-3">
            {filtered.map((u) => {
              const roleInfo = getRoleInfo(u.role);
              const customPerms = hasCustomPermissions(u);
              return (
                <Card
                  key={u.id}
                  className={`cursor-pointer transition-all hover:shadow-md ${u.is_active === false ? "opacity-50" : ""}`}
                  onClick={() => openEditDialog(u)}
                  data-testid={`user-card-${u.email}`}
                >
                  <CardContent className="flex items-center justify-between py-4 px-5">
                    <div className="flex items-center gap-4">
                      <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                        <span className="text-sm font-bold text-primary">
                          {u.name?.charAt(0)?.toUpperCase() || "?"}
                        </span>
                      </div>
                      <div>
                        <p className="font-medium">{u.name}</p>
                        <p className="text-sm text-muted-foreground">{u.email}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <Badge className={`${roleInfo.color} text-xs`}>{roleInfo.label}</Badge>
                      {customPerms && (
                        <Badge variant="outline" className="text-xs">
                          <Lock className="h-3 w-3 mr-1" />
                          Personalizado
                        </Badge>
                      )}
                      {u.is_active === false && (
                        <Badge variant="destructive" className="text-xs">Inativo</Badge>
                      )}
                      <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    </div>
                  </CardContent>
                </Card>
              );
            })}
            {filtered.length === 0 && (
              <p className="text-center text-muted-foreground py-8">Nenhum utilizador encontrado</p>
            )}
          </div>
        )}

        {/* Edit Permissions Dialog */}
        <Dialog open={editDialog.open} onOpenChange={(open) => setEditDialog({ open, user: editDialog.user })}>
          <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <UserCog className="h-5 w-5" />
                Editar Permissões - {editDialog.user?.name}
              </DialogTitle>
              <DialogDescription>
                Configurar role e permissões de acesso para este utilizador
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-6 py-4">
              {/* Info sobre sincronização */}
              {editForm.role !== editForm.originalRole && (
                <div className="flex items-start gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg text-amber-800 text-sm">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                  <div>
                    <strong>Role alterado!</strong> As permissões foram atualizadas automaticamente para o padrão do novo perfil.
                  </div>
                </div>
              )}

              {/* Role & Status */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Role</Label>
                  <Select value={editForm.role} onValueChange={handleRoleChange}>
                    <SelectTrigger data-testid="edit-role">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ROLES.map(r => (
                        <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Estado</Label>
                  <div className="flex items-center gap-3 h-10">
                    <Switch
                      checked={editForm.is_active}
                      onCheckedChange={(v) => setEditForm(prev => ({ ...prev, is_active: v }))}
                      data-testid="edit-active"
                    />
                    <span className="text-sm">{editForm.is_active ? "Ativo" : "Inativo"}</span>
                  </div>
                </div>
              </div>

              {/* Pages Access */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label className="text-base font-semibold flex items-center gap-2">
                    <Eye className="h-4 w-4" />
                    Páginas Visíveis
                  </Label>
                  <div className="flex gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setEditForm(prev => ({ ...prev, pages: AVAILABLE_PAGES.map(p => p.key) }))}
                    >
                      Todas
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setEditForm(prev => ({ ...prev, pages: [] }))}
                    >
                      Nenhuma
                    </Button>
                  </div>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {AVAILABLE_PAGES.map(page => {
                    const isDefaultForRole = (defaultPermissions[editForm.role]?.pages || []).includes(page.key);
                    return (
                      <label
                        key={page.key}
                        className={`flex items-center gap-2 p-2.5 rounded-lg border cursor-pointer transition-all text-sm ${
                          (editForm.pages || []).includes(page.key)
                            ? "bg-primary/5 border-primary/30"
                            : "bg-muted/30 border-transparent opacity-60"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={(editForm.pages || []).includes(page.key)}
                          onChange={() => togglePage(page.key)}
                          className="rounded border-gray-300"
                        />
                        <span className="flex-1">{page.label}</span>
                        {isDefaultForRole && (
                          <span className="text-[10px] text-primary font-medium">PADRÃO</span>
                        )}
                      </label>
                    );
                  })}
                </div>
              </div>

              {/* Actions */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label className="text-base font-semibold flex items-center gap-2">
                    <Shield className="h-4 w-4" />
                    Ações Permitidas
                  </Label>
                  <div className="flex gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setEditForm(prev => ({ ...prev, actions: AVAILABLE_ACTIONS.map(a => a.key) }))}
                    >
                      Todas
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setEditForm(prev => ({ ...prev, actions: [] }))}
                    >
                      Nenhuma
                    </Button>
                  </div>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {AVAILABLE_ACTIONS.map(action => {
                    const isDefaultForRole = (defaultPermissions[editForm.role]?.actions || []).includes(action.key);
                    return (
                      <label
                        key={action.key}
                        className={`flex items-center gap-2 p-2.5 rounded-lg border cursor-pointer transition-all text-sm ${
                          (editForm.actions || []).includes(action.key)
                            ? "bg-primary/5 border-primary/30"
                            : "bg-muted/30 border-transparent opacity-60"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={(editForm.actions || []).includes(action.key)}
                          onChange={() => toggleAction(action.key)}
                          className="rounded border-gray-300"
                        />
                        <span className="flex-1">{action.label}</span>
                        {isDefaultForRole && (
                          <span className="text-[10px] text-primary font-medium">PADRÃO</span>
                        )}
                      </label>
                    );
                  })}
                </div>
              </div>

              {/* Botão para redefinir permissões */}
              <div className="flex items-center justify-between pt-2 border-t">
                <p className="text-sm text-muted-foreground">
                  {permissionsModified ? 
                    "Permissões personalizadas manualmente" : 
                    "Permissões sincronizadas com o perfil"}
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={resetToDefault}
                  className="flex items-center gap-2"
                >
                  <RefreshCw className="h-4 w-4" />
                  Redefinir para Padrão
                </Button>
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setEditDialog({ open: false, user: null })}>
                Cancelar
              </Button>
              <Button onClick={handleSave} disabled={saving} data-testid="save-permissions">
                {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
                Guardar
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
  );
};

export default ProfileSettingsPage;
