/**
 * UsersManagementPage — Página de gestão de utilizadores (apenas admin).
 *
 * PORQUÊ: O administrador gere contas, define roles e permissões granulares por páginas e ações.
 *
 * @context {AuthContext} — Consome user, token para autenticação e permissões
 */

import { useState, useEffect, useMemo } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { TableSkeleton } from "../components/ui/skeletons";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Badge } from "../components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Checkbox } from "../components/ui/checkbox";
import { 
  Users, Search, UserPlus, Edit, Trash2, Loader2, UserX, UserCheck, Eye, EyeOff, RefreshCw, Copy, Mail
} from "lucide-react";
import { toast } from "sonner";
import { getUsers, createUser, updateUser, deleteUser } from "../services/api";
import { useAuth } from "../contexts/AuthContext";
import EmailConfigForm from "../components/EmailConfigForm";
import { hasRole, hasAnyRole } from "../utils/roleUtils";

const roleLabels = {
  cliente: "Cliente",
  consultor: "Consultor",
  intermediario: "Intermediário de Crédito",
  consultor_intermediario: "Consultor/Intermediário",
  diretor: "Diretor(a)",
  administrativo: "Administrativo(a)",
  indexacao: "Indexação",
  ceo: "CEO",
  admin: "Administrador",
  parceiro: "Parceiro",
};

const roleColors = {
  cliente: "bg-blue-100 text-blue-800",
  consultor: "bg-emerald-100 text-emerald-800",
  intermediario: "bg-purple-100 text-purple-800",
  consultor_intermediario: "bg-gradient-to-r from-emerald-100 to-purple-100 text-purple-800",
  diretor: "bg-indigo-100 text-indigo-800",
  administrativo: "bg-amber-100 text-amber-800",
  indexacao: "bg-cyan-100 text-cyan-800",
  ceo: "bg-orange-100 text-orange-800",
  admin: "bg-red-100 text-red-800",
  parceiro: "bg-violet-100 text-violet-800",
};

// Roles available as additional (excludes admin, cliente, parceiro)
const additionalRoleOptions = [
  "consultor",
  "intermediario",
  "consultor_intermediario",
  "diretor",
  "administrativo",
  "indexacao",
  "ceo",
];

const UsersManagementPage = ({ embedded = false }) => {
  const { user: currentUser, impersonate } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [formLoading, setFormLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    password: "",
    phone: "",
    role: "consultor",
    additional_roles: [],
    onedrive_folder: "",
  });
  const [showPassword, setShowPassword] = useState(false);
  const [generatedPassword, setGeneratedPassword] = useState("");
  const [emailConfigDialog, setEmailConfigDialog] = useState({ open: false, user: null });

  useEffect(() => {
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    try {
      setLoading(true);
      const response = await getUsers();
      setUsers(response.data);
    } catch (error) {
      toast.error("Erro ao carregar utilizadores");
    } finally {
      setLoading(false);
    }
  };

  const filteredUsers = useMemo(() => {
    return users.filter(user => {
      const matchesSearch = user.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                           user.email.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesRole = roleFilter === "all" || hasRole(user, roleFilter);
      return matchesSearch && matchesRole;
    });
  }, [users, searchTerm, roleFilter]);

  // Gerar password aleatória
  const generatePassword = () => {
    const length = 12;
    const charset = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*";
    let password = "";
    // Garantir pelo menos uma de cada tipo
    password += "ABCDEFGHIJKLMNOPQRSTUVWXYZ".charAt(Math.floor(Math.random() * 26));
    password += "abcdefghijklmnopqrstuvwxyz".charAt(Math.floor(Math.random() * 26));
    password += "0123456789".charAt(Math.floor(Math.random() * 10));
    password += "!@#$%^&*".charAt(Math.floor(Math.random() * 8));
    // Preencher o resto
    for (let i = 4; i < length; i++) {
      password += charset.charAt(Math.floor(Math.random() * charset.length));
    }
    // Embaralhar
    password = password.split('').sort(() => Math.random() - 0.5).join('');
    setFormData({ ...formData, password });
    setGeneratedPassword(password);
    setShowPassword(true);
  };

  // Copiar password para clipboard
  const copyPassword = () => {
    navigator.clipboard.writeText(formData.password);
    toast.success("Password copiada para o clipboard");
  };

  const handleCreateUser = async (e) => {
    e.preventDefault();
    // Validação: cargo principal não pode estar nos cargos adicionais
    if (formData.additional_roles.includes(formData.role)) {
      toast.error(`O cargo principal "${roleLabels[formData.role]}" não pode ser também cargo adicional.`);
      return;
    }
    setFormLoading(true);
    try {
      const response = await createUser(formData);
      toast.success("Utilizador criado com sucesso");
      // Mostrar a password após criação
      if (formData.password) {
        toast.success(
          <div>
            <strong>Password do utilizador:</strong>
            <div className="mt-1 p-2 bg-gray-100 rounded font-mono select-all">{formData.password}</div>
            <p className="text-xs mt-1">Copie esta password e envie ao utilizador por email seguro.</p>
          </div>,
          { duration: 10000 }
        );
      }
      setIsCreateDialogOpen(false);
      setFormData({
        name: "",
        email: "",
        password: "",
        phone: "",
        role: "consultor",
        additional_roles: [],
        onedrive_folder: "",
      });
      setGeneratedPassword("");
      setShowPassword(false);
      fetchUsers();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao criar utilizador");
    } finally {
      setFormLoading(false);
    }
  };

  const handleEditUser = async (e) => {
    e.preventDefault();
    if (!selectedUser?.id) {
      toast.error("Nenhum utilizador selecionado");
      return;
    }
    // Validação: cargo principal não pode estar nos cargos adicionais
    if (formData.additional_roles.includes(formData.role)) {
      toast.error(`O cargo principal "${roleLabels[formData.role]}" não pode ser também cargo adicional.`);
      return;
    }
    setFormLoading(true);
    try {
      const updateData = { ...formData };
      // Remove password if empty
      if (!updateData.password) {
        delete updateData.password;
      }
      await updateUser(selectedUser.id, updateData);
      toast.success("Utilizador atualizado com sucesso");
      setIsEditDialogOpen(false);
      fetchUsers();
    } catch (error) {
      console.error("Erro ao atualizar:", error);
      toast.error(error.response?.data?.detail || "Erro ao atualizar utilizador");
    } finally {
      setFormLoading(false);
    }
  };

  const handleDeleteUser = async (userId, userName) => {
    // O8 - Usar undo toast em vez de window.confirm para micro-ações
    const userToDelete = users.find(u => u.id === userId);
    if (!userToDelete) return;

    // Remover otimisticamente da lista
    setUsers(prev => prev.filter(u => u.id !== userId));

    toast.success(`Utilizador "${userName}" eliminado`, {
      action: {
        label: 'Desfazer',
        onClick: () => {
          // Restaurar na lista (undo)
          setUsers(prev => [...prev, userToDelete].sort((a, b) => a.name.localeCompare(b.name)));
          toast.success("Ação desfeita");
        },
      },
      duration: 5000,
      onAutoClose: async () => {
        // Commit: efetuar a eliminação real no backend
        try {
          await deleteUser(userId);
        } catch (error) {
          // Se falhar, restaurar o utilizador
          setUsers(prev => [...prev, userToDelete].sort((a, b) => a.name.localeCompare(b.name)));
          toast.error(error.response?.data?.detail || "Erro ao eliminar utilizador");
        }
      },
    });
  };

  const handleToggleUserStatus = async (userId, currentStatus) => {
    try {
      await updateUser(userId, { is_active: !currentStatus });
      toast.success(`Utilizador ${!currentStatus ? 'ativado' : 'desativado'} com sucesso`);
      fetchUsers();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao atualizar utilizador");
    }
  };

  const openEditDialog = (user) => {
    setSelectedUser(user);
    setFormData({
      name: user.name,
      email: user.email,
      password: "",
      phone: user.phone || "",
      role: user.role,
      additional_roles: user.additional_roles || [],
      onedrive_folder: user.onedrive_folder || "",
    });
    setIsEditDialogOpen(true);
  };

  if (loading) {
    const loadingContent = (
      <div className="space-y-6">
        <div className="flex items-start justify-between gap-3">
          <div className="h-8 w-48 bg-muted animate-pulse rounded" />
          <div className="h-9 w-36 bg-muted animate-pulse rounded" />
        </div>
        <TableSkeleton rows={8} columns={6} />
      </div>
    );
    return embedded ? loadingContent : <DashboardLayout title="Gestão de Utilizadores">{loadingContent}</DashboardLayout>;
  }

  const pageContent = (
    <>
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <CardTitle className="text-lg flex items-center gap-2">
                  <Users className="h-5 w-5 shrink-0" />
                  <span className="truncate">Gestão de Utilizadores</span>
                </CardTitle>
                <CardDescription>Criar, editar e eliminar utilizadores do sistema</CardDescription>
              </div>
              <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
                {/* Esconder botão para roles sem permissão de criar utilizadores */}
                {!hasRole(currentUser, "indexacao") && (
                <DialogTrigger asChild>
                  <Button size="sm" className="shrink-0">
                    <UserPlus className="h-4 w-4 sm:mr-2" />
                    <span className="hidden sm:inline">Novo Utilizador</span>
                  </Button>
                </DialogTrigger>
                )}
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Criar Novo Utilizador</DialogTitle>
                    <DialogDescription>
                      Preencha os dados para criar um novo utilizador.
                    </DialogDescription>
                  </DialogHeader>
                  <form onSubmit={handleCreateUser} className="space-y-4">
                    <div className="space-y-2">
                      <Label>Nome</Label>
                      <Input 
                        value={formData.name} 
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })} 
                        required
                      />
                    </div>
                    {/* Email - obrigatório para não-parceiros, opcional para parceiros */}
                    <div className="space-y-2">
                      <Label>
                        Email
                        {formData.role === "parceiro" && (
                          <span className="text-xs text-muted-foreground ml-1">(opcional)</span>
                        )}
                      </Label>
                      <Input 
                        value={formData.email} 
                        onChange={(e) => setFormData({ ...formData, email: e.target.value })} 
                        required={formData.role !== "parceiro"}
                        type="email"
                      />
                    </div>
                    {/* Telefone - opcional para todos */}
                    <div className="space-y-2">
                      <Label>
                        Telefone
                        <span className="text-xs text-muted-foreground ml-1">(opcional)</span>
                      </Label>
                      <Input 
                        value={formData.phone} 
                        onChange={(e) => setFormData({ ...formData, phone: e.target.value })} 
                        type="tel"
                      />
                    </div>
                    {/* Campos apenas para não-parceiros */}
                    {formData.role !== "parceiro" && (
                      <>
                        <div className="space-y-2">
                          <Label>Password</Label>
                          <div className="flex gap-2">
                            <div className="relative flex-1">
                              <Input 
                                type={showPassword ? "text" : "password"} 
                                value={formData.password} 
                                onChange={(e) => setFormData({ ...formData, password: e.target.value })} 
                                className="pr-20"
                                required
                              />
                              <div className="absolute right-1 top-1/2 -translate-y-1/2 flex gap-1">
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="icon"
                                  className="h-7 w-7"
                                  onClick={() => setShowPassword(!showPassword)}
                                  title={showPassword ? "Ocultar password" : "Mostrar password"}
                                >
                                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                </Button>
                                {formData.password && (
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7"
                                    onClick={copyPassword}
                                    title="Copiar password"
                                  >
                                    <Copy className="h-4 w-4" />
                                  </Button>
                                )}
                              </div>
                            </div>
                            <Button
                              type="button"
                              variant="outline"
                              onClick={generatePassword}
                              title="Gerar password aleatória"
                            >
                              <RefreshCw className="h-4 w-4" />
                            </Button>
                          </div>
                          {generatedPassword && (
                            <p className="text-xs text-green-600 font-medium">
                              Password gerada. Copie e envie ao utilizador.
                            </p>
                          )}
                          {/* O17 - Password strength indicator */}
                          {formData.password && !generatedPassword && (() => {
                            const pw = formData.password;
                            let score = 0;
                            if (pw.length >= 8) score++;
                            if (pw.length >= 12) score++;
                            if (/[A-Z]/.test(pw)) score++;
                            if (/[0-9]/.test(pw)) score++;
                            if (/[^A-Za-z0-9]/.test(pw)) score++;
                            const levels = [
                              { label: "Muito fraca", color: "bg-red-500", width: "w-1/5" },
                              { label: "Fraca", color: "bg-orange-500", width: "w-2/5" },
                              { label: "Razoável", color: "bg-yellow-500", width: "w-3/5" },
                              { label: "Forte", color: "bg-green-500", width: "w-4/5" },
                              { label: "Muito forte", color: "bg-emerald-600", width: "w-full" },
                            ];
                            const level = levels[Math.min(score, 4)];
                            return (
                              <div className="space-y-1">
                                <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                                  <div className={`h-full rounded-full transition-all ${level.color} ${level.width}`} />
                                </div>
                                <p className={`text-xs ${score >= 3 ? "text-green-600" : "text-orange-600"}`}>{level.label}</p>
                              </div>
                            );
                          })()}
                        </div>
                        <div className="space-y-2">
                          <Label>Pasta Drive</Label>
                          <Input 
                            value={formData.onedrive_folder} 
                            onChange={(e) => setFormData({ ...formData, onedrive_folder: e.target.value })} 
                            placeholder="Nome/caminho da pasta" 
                          />
                        </div>
                      </>
                    )}
                    <div className="space-y-2">
                      <Label>Perfil</Label>
                      <Select value={formData.role} onValueChange={(value) => setFormData({ ...formData, role: value, additional_roles: formData.additional_roles.filter((r) => r !== value) })}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="consultor">Consultor</SelectItem>
                          <SelectItem value="intermediario">Intermediário de Crédito</SelectItem>
                          <SelectItem value="diretor">Diretor(a)</SelectItem>
                          <SelectItem value="administrativo">Administrativo(a)</SelectItem>
                          <SelectItem value="indexacao">Indexação</SelectItem>
                          <SelectItem value="parceiro">Parceiro</SelectItem>
                          <SelectItem value="ceo">CEO</SelectItem>
                          <SelectItem value="admin">Administrador</SelectItem>
                        </SelectContent>
                      </Select>
                      <p className="text-xs text-muted-foreground">
                        {formData.role === "parceiro" 
                          ? "Parceiros são utilizadores fantasma sem acesso à plataforma, usados apenas para tracking e atribuição."
                          : "Nota: Clientes são processos, não utilizadores do sistema."}
                      </p>
                    </div>
                    {/* Cargos Adicionais — only for non-parceiro, non-cliente */}
                    {formData.role !== "parceiro" && formData.role !== "cliente" && (
                      <div className="space-y-2">
                        <Label>Cargos Adicionais</Label>
                        <p className="text-xs text-muted-foreground">
                          Permitir que este utilizador alterne entre múltiplos perfis no Context Switcher. O cargo principal não pode ser selecionado como adicional.
                        </p>
                        {formData.additional_roles.includes(formData.role) && (
                          <p className="text-xs text-red-500 font-medium">
                            ⚠ O cargo principal já está selecionado e não pode ser adicionado como cargo adicional.
                          </p>
                        )}
                        <div className="grid grid-cols-2 gap-2 pt-1">
                          {additionalRoleOptions
                            .filter((r) => r !== formData.role)
                            .map((role) => (
                              <label
                                key={role}
                                className="flex items-center gap-2 text-sm cursor-pointer rounded-md border px-3 py-2 hover:bg-muted/50 transition-colors has-[data-state=checked]:bg-primary/10 has-[data-state=checked]:border-primary/30"
                              >
                                <Checkbox
                                  checked={formData.additional_roles.includes(role)}
                                  onCheckedChange={(checked) => {
                                    const updated = checked
                                      ? [...formData.additional_roles, role]
                                      : formData.additional_roles.filter((r) => r !== role);
                                    setFormData({ ...formData, additional_roles: updated });
                                  }}
                                />
                                <span className="text-sm">{roleLabels[role]}</span>
                              </label>
                            ))}
                        </div>
                      </div>
                    )}
                    <DialogFooter>
                      <Button type="submit" disabled={formLoading}>
                        {formLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Criar"}
                      </Button>
                    </DialogFooter>
                  </form>
                </DialogContent>
              </Dialog>
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col sm:flex-row gap-4 mb-4">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input 
                  placeholder="Pesquisar utilizador..." 
                  className="pl-10" 
                  value={searchTerm} 
                  onChange={(e) => setSearchTerm(e.target.value)} 
                />
              </div>
              <Select value={roleFilter} onValueChange={setRoleFilter}>
                <SelectTrigger className="w-full sm:w-48">
                  <SelectValue placeholder="Filtrar por perfil" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos os perfis</SelectItem>
                  <SelectItem value="cliente">Cliente</SelectItem>
                  <SelectItem value="consultor">Consultor</SelectItem>
                  <SelectItem value="intermediario">Intermediário de Crédito</SelectItem>
                  <SelectItem value="diretor">Diretor(a)</SelectItem>
                  <SelectItem value="administrativo">Administrativo(a)</SelectItem>
                  <SelectItem value="indexacao">Indexação</SelectItem>
                  <SelectItem value="parceiro">Parceiro</SelectItem>
                  <SelectItem value="ceo">CEO</SelectItem>
                  <SelectItem value="admin">Administrador</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* O9 - Mobile: Card view */}
            {filteredUsers.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">Nenhum utilizador encontrado</div>
            ) : (
              <>
                <div className="md:hidden space-y-3">
                  {filteredUsers.map((u) => (
                    <div key={u.id} className="border rounded-lg p-4 bg-card space-y-2">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <p className="font-medium truncate">{u.name}</p>
                          <p className="text-sm text-muted-foreground truncate">{u.email}</p>
                        </div>
                        <div className="flex gap-1 shrink-0 flex-wrap justify-end">
                          <Badge className={`${roleColors[u.role]} border text-xs`}>{roleLabels[u.role]}</Badge>
                          {u.additional_roles?.length > 0 && u.additional_roles.map((r) => (
                            <Badge key={r} variant="outline" className="text-xs">{roleLabels[r]}</Badge>
                          ))}
                          <Badge className={u.is_active ? "bg-green-100 text-green-800 text-xs" : "bg-red-100 text-red-800 text-xs"}>
                            {u.is_active ? "Ativo" : "Inativo"}
                          </Badge>
                        </div>
                      </div>
                      <div className="flex gap-1 justify-end">
                        {hasAnyRole(currentUser, ["admin", "ceo"]) && u.id !== currentUser?.id && u.role !== "admin" && u.role !== "ceo" && (
                          <Button variant="ghost" size="icon" onClick={async () => { try { await impersonate(u.id); toast.success(`A ver como ${u.name}`); } catch { toast.error("Erro"); } }}>
                            <Eye className="h-4 w-4 text-blue-600" />
                          </Button>
                        )}
                        <Button variant="ghost" size="icon" onClick={() => handleToggleUserStatus(u.id, u.is_active)}>
                          {u.is_active ? <UserX className="h-4 w-4 text-orange-600" /> : <UserCheck className="h-4 w-4 text-green-600" />}
                        </Button>
                        {hasAnyRole(currentUser, ["admin", "ceo"]) && u.role !== "parceiro" && (
                              <Button variant="ghost" size="icon" onClick={() => setEmailConfigDialog({ open: true, user: u })} title="Configurar Email">
                                <Mail className="h-4 w-4" />
                              </Button>
                            )}
                        {!hasRole(currentUser, "indexacao") && (
                          <>
                            <Button variant="ghost" size="icon" onClick={() => openEditDialog(u)}>
                              <Edit className="h-4 w-4" />
                            </Button>
                            <Button variant="ghost" size="icon" onClick={() => handleDeleteUser(u.id, u.name)}>
                              <Trash2 className="h-4 w-4 text-destructive" />
                            </Button>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>

                {/* O9 - Desktop: Table */}
                <div className="hidden md:block rounded-md border overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Nome</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Perfil</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Pasta Drive</TableHead>
                    <TableHead className="text-right">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredUsers.map((user) => (
                    <TableRow key={user.id}>
                        <TableCell className="font-medium">{user.name}</TableCell>
                        <TableCell>{user.email}</TableCell>
                        <TableCell>
                          <div className="flex flex-wrap gap-1">
                            <Badge className={`${roleColors[user.role]} border`}>
                              {roleLabels[user.role]}
                            </Badge>
                            {user.additional_roles?.length > 0 && user.additional_roles.map((r) => (
                              <Badge key={r} variant="outline">{roleLabels[r]}</Badge>
                            ))}
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge 
                            variant={user.is_active ? "success" : "destructive"} 
                            className={user.is_active ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"}
                          >
                            {user.is_active ? "Ativo" : "Inativo"}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-mono text-sm">{user.onedrive_folder || "-"}</TableCell>
                        <TableCell className="text-right">
                          {/* Botão Impersonate - admin pode ver como qualquer utilizador (exceto outros admins) */}
                          {hasRole(currentUser, "admin") && user.id !== currentUser?.id && user.role !== "admin" && (
                            <Button 
                              variant="ghost" 
                              size="icon" 
                              onClick={async () => {
                                try {
                                  await impersonate(user.id);
                                  toast.success(`A ver como ${user.name}`);
                                } catch (error) {
                                  toast.error("Erro ao iniciar visualização");
                                }
                              }}
                              title="Ver como este utilizador"
                              className="text-blue-600 hover:text-blue-800 hover:bg-blue-50"
                            >
                              <Eye className="h-4 w-4" />
                            </Button>
                          )}
                          <Button 
                            variant="ghost" 
                            size="icon" 
                            onClick={() => handleToggleUserStatus(user.id, user.is_active)}
                            title={user.is_active ? "Desativar utilizador" : "Ativar utilizador"}
                          >
                            {user.is_active ? (
                              <UserX className="h-4 w-4 text-orange-600" />
                            ) : (
                              <UserCheck className="h-4 w-4 text-green-600" />
                            )}
                          </Button>
                          {hasAnyRole(currentUser, ["admin", "ceo"]) && user.role !== "parceiro" && (
                            <Button variant="ghost" size="icon" onClick={() => setEmailConfigDialog({ open: true, user })} title="Configurar Email" className="text-teal-600 hover:text-teal-800 hover:bg-teal-50">
                              <Mail className="h-4 w-4" />
                            </Button>
                          )}
                          {!hasRole(currentUser, "indexacao") && (
                          <>
                          <Button variant="ghost" size="icon" onClick={() => openEditDialog(user)}>
                            <Edit className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="icon" onClick={() => handleDeleteUser(user.id, user.name)}>
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                          </>
                          )}
                        </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Edit Dialog */}
      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Editar Utilizador</DialogTitle>
            <DialogDescription>
              Altere os dados do utilizador.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleEditUser} className="space-y-4">
            <div className="space-y-2">
              <Label>Nome</Label>
              <Input 
                value={formData.name} 
                onChange={(e) => setFormData({ ...formData, name: e.target.value })} 
                required
              />
            </div>
            {/* Email - obrigatório para não-parceiros, opcional para parceiros */}
            <div className="space-y-2">
              <Label>
                Email
                {formData.role === "parceiro" && (
                  <span className="text-xs text-muted-foreground ml-1">(opcional)</span>
                )}
              </Label>
              <Input 
                value={formData.email || ""} 
                onChange={(e) => setFormData({ ...formData, email: e.target.value })} 
                required={formData.role !== "parceiro"}
                type="email"
              />
            </div>
            {/* Telefone - opcional para todos */}
            <div className="space-y-2">
              <Label>
                Telefone
                <span className="text-xs text-muted-foreground ml-1">(opcional)</span>
              </Label>
              <Input 
                value={formData.phone} 
                onChange={(e) => setFormData({ ...formData, phone: e.target.value })} 
                type="tel"
              />
            </div>
            {/* Campos apenas para não-parceiros */}
            {formData.role !== "parceiro" && (
              <>
                <div className="space-y-2">
                  <Label>Pasta Drive</Label>
                  <Input 
                    value={formData.onedrive_folder} 
                    onChange={(e) => setFormData({ ...formData, onedrive_folder: e.target.value })} 
                    placeholder="Nome/caminho da pasta" 
                  />
                </div>
                <div className="space-y-2">
                  <Label>Nova Password (deixar em branco para manter)</Label>
                  <div className="relative">
                    <Input 
                      type={showPassword ? "text" : "password"} 
                      value={formData.password} 
                      onChange={(e) => setFormData({ ...formData, password: e.target.value })} 
                      placeholder="Digite apenas se quiser alterar"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>
              </>
            )}
            <div className="space-y-2">
              <Label>Perfil</Label>
              <Select value={formData.role} onValueChange={(value) => setFormData({ ...formData, role: value, additional_roles: formData.additional_roles.filter((r) => r !== value) })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="consultor">Consultor</SelectItem>
                  <SelectItem value="intermediario">Intermediário de Crédito</SelectItem>
                  <SelectItem value="diretor">Diretor(a)</SelectItem>
                  <SelectItem value="administrativo">Administrativo(a)</SelectItem>
                  <SelectItem value="indexacao">Indexação</SelectItem>
                  <SelectItem value="parceiro">Parceiro</SelectItem>
                  <SelectItem value="ceo">CEO</SelectItem>
                  <SelectItem value="admin">Administrador</SelectItem>
                </SelectContent>
              </Select>
              {formData.role === "parceiro" && (
                <p className="text-xs text-muted-foreground">
                  Parceiros são utilizadores fantasma sem acesso à plataforma, usados apenas para tracking e atribuição.
                </p>
              )}
            </div>
            {/* Cargos Adicionais — only for non-parceiro, non-cliente */}
            {formData.role !== "parceiro" && formData.role !== "cliente" && (
              <div className="space-y-2">
                <Label>Cargos Adicionais</Label>
                <p className="text-xs text-muted-foreground">
                  Permitir que este utilizador alterne entre múltiplos perfis no Context Switcher. O cargo principal não pode ser selecionado como adicional.
                </p>
                {formData.additional_roles.includes(formData.role) && (
                  <p className="text-xs text-red-500 font-medium">
                    ⚠ O cargo principal já está selecionado e não pode ser adicionado como cargo adicional.
                  </p>
                )}
                <div className="grid grid-cols-2 gap-2 pt-1">
                  {additionalRoleOptions
                    .filter((r) => r !== formData.role)
                    .map((role) => (
                      <label
                        key={role}
                        className="flex items-center gap-2 text-sm cursor-pointer rounded-md border px-3 py-2 hover:bg-muted/50 transition-colors has-[data-state=checked]:bg-primary/10 has-[data-state=checked]:border-primary/30"
                      >
                        <Checkbox
                          checked={formData.additional_roles.includes(role)}
                          onCheckedChange={(checked) => {
                            const updated = checked
                              ? [...formData.additional_roles, role]
                              : formData.additional_roles.filter((r) => r !== role);
                            setFormData({ ...formData, additional_roles: updated });
                          }}
                        />
                        <span className="text-sm">{roleLabels[role]}</span>
                      </label>
                    ))}
                </div>
              </div>
            )}
            <DialogFooter>
              <Button type="submit" disabled={formLoading}>
                {formLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Guardar"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      {/* Email Config Dialog (Admin) */}
      <Dialog open={emailConfigDialog.open} onOpenChange={(open) => setEmailConfigDialog({ open, user: emailConfigDialog.user })}>
        <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Mail className="h-5 w-5" />
              Configurar Webmail — {emailConfigDialog.user?.name}
            </DialogTitle>
            <DialogDescription>
              {!hasRole(emailConfigDialog.user, "parceiro")
                ? "Configure as credenciais IMAP/SMTP para este utilizador. A password será encriptada."
                : "Parceiros não podem ter configuração de email."}
            </DialogDescription>
          </DialogHeader>
          {!hasRole(emailConfigDialog.user, "parceiro") ? (
            <EmailConfigForm
              mode="admin"
              userId={emailConfigDialog.user?.id}
              targetUserName={emailConfigDialog.user?.name}
              onSuccess={() => {
                setEmailConfigDialog({ open: false, user: null });
              }}
              onCancel={() => setEmailConfigDialog({ open: false, user: null })}
            />
          ) : (
            <p className="text-muted-foreground py-4">Parceiros não têm acesso ao webmail.</p>
          )}
        </DialogContent>
      </Dialog>
    </>
  );

  return embedded ? pageContent : <DashboardLayout title="Gestão de Utilizadores">{pageContent}</DashboardLayout>;
};

export default UsersManagementPage;

