import { useState, useEffect, useMemo } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Badge } from "../components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { 
  Users, Search, UserPlus, Edit, Trash2, Loader2, UserX, UserCheck, Eye
} from "lucide-react";
import { toast } from "sonner";
import { getUsers, createUser, updateUser, deleteUser } from "../services/api";
import { useAuth } from "../contexts/AuthContext";

const roleLabels = {
  cliente: "Cliente",
  consultor: "Consultor",
  intermediario: "Intermediário de Crédito",
  mediador: "Intermediário de Crédito",
  diretor: "Diretor(a)",
  administrativo: "Administrativo(a)",
  indexacao: "Indexação",
  gestor_documentos: "Gestor de Documentos",
  ceo: "CEO",
  admin: "Administrador",
};

const roleColors = {
  cliente: "bg-blue-100 text-blue-800",
  consultor: "bg-emerald-100 text-emerald-800",
  intermediario: "bg-purple-100 text-purple-800",
  mediador: "bg-purple-100 text-purple-800",
  diretor: "bg-indigo-100 text-indigo-800",
  administrativo: "bg-amber-100 text-amber-800",
  indexacao: "bg-cyan-100 text-cyan-800",
  gestor_documentos: "bg-teal-100 text-teal-800",
  ceo: "bg-orange-100 text-orange-800",
  admin: "bg-red-100 text-red-800",
};

const UsersManagementPage = () => {
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
    onedrive_folder: "",
  });

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
      const matchesRole = roleFilter === "all" || user.role === roleFilter;
      return matchesSearch && matchesRole;
    });
  }, [users, searchTerm, roleFilter]);

  const handleCreateUser = async (e) => {
    e.preventDefault();
    setFormLoading(true);
    try {
      await createUser(formData);
      toast.success("Utilizador criado com sucesso");
      setIsCreateDialogOpen(false);
      setFormData({
        name: "",
        email: "",
        password: "",
        phone: "",
        role: "consultor",
        onedrive_folder: "",
      });
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

  const handleDeleteUser = async (userId) => {
    if (!window.confirm("Tem a certeza que deseja eliminar este utilizador? Esta ação não pode ser revertida.")) {
      return;
    }
    try {
      await deleteUser(userId);
      toast.success("Utilizador eliminado com sucesso");
      fetchUsers();
    } catch (error) {
      console.error("Erro ao eliminar:", error);
      toast.error(error.response?.data?.detail || "Erro ao eliminar utilizador");
    }
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
      onedrive_folder: user.onedrive_folder || "",
    });
    setIsEditDialogOpen(true);
  };

  if (loading) {
    return (
      <DashboardLayout title="Gestão de Utilizadores">
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title="Gestão de Utilizadores">
      <div className="space-y-6 p-6">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Users className="h-5 w-5" />
                  Gestão de Utilizadores
                </CardTitle>
                <CardDescription>Criar, editar e eliminar utilizadores do sistema</CardDescription>
              </div>
              <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
                {/* Esconder botão para roles sem permissão de criar utilizadores */}
                {currentUser?.role !== "indexacao" && currentUser?.role !== "gestor_documentos" && (
                <DialogTrigger asChild>
                  <Button>
                    <UserPlus className="h-4 w-4 mr-2" />
                    Novo Utilizador
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
                    <div className="space-y-2">
                      <Label>Email</Label>
                      <Input 
                        type="email" 
                        value={formData.email} 
                        onChange={(e) => setFormData({ ...formData, email: e.target.value })} 
                        required 
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Password</Label>
                      <Input 
                        type="password" 
                        value={formData.password} 
                        onChange={(e) => setFormData({ ...formData, password: e.target.value })} 
                        required 
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Telefone</Label>
                      <Input 
                        value={formData.phone} 
                        onChange={(e) => setFormData({ ...formData, phone: e.target.value })} 
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Perfil</Label>
                      <Select value={formData.role} onValueChange={(value) => setFormData({ ...formData, role: value })}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="consultor">Consultor</SelectItem>
                          <SelectItem value="intermediario">Intermediário de Crédito</SelectItem>
                          <SelectItem value="diretor">Diretor(a)</SelectItem>
                          <SelectItem value="administrativo">Administrativo(a)</SelectItem>
                          <SelectItem value="indexacao">Indexação</SelectItem>
                          <SelectItem value="ceo">CEO</SelectItem>
                          <SelectItem value="admin">Administrador</SelectItem>
                        </SelectContent>
                      </Select>
                      <p className="text-xs text-muted-foreground">Nota: Clientes são processos, não utilizadores do sistema.</p>
                    </div>
                    <div className="space-y-2">
                      <Label>Pasta Drive</Label>
                      <Input 
                        value={formData.onedrive_folder} 
                        onChange={(e) => setFormData({ ...formData, onedrive_folder: e.target.value })} 
                        placeholder="Nome/caminho da pasta" 
                      />
                    </div>
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
                  <SelectItem value="ceo">CEO</SelectItem>
                  <SelectItem value="admin">Administrador</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="rounded-md border">
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
                  {filteredUsers.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                        Nenhum utilizador encontrado
                      </TableCell>
                    </TableRow>
                  ) : (
                    filteredUsers.map((user) => (
                      <TableRow key={user.id}>
                        <TableCell className="font-medium">{user.name}</TableCell>
                        <TableCell>{user.email}</TableCell>
                        <TableCell>
                          <Badge className={`${roleColors[user.role]} border`}>
                            {roleLabels[user.role]}
                          </Badge>
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
                          {/* Botão Impersonate - só para admins e não para si próprio */}
                          {currentUser?.role === "admin" && user.id !== currentUser?.id && user.role !== "admin" && (
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
                          {currentUser?.role !== "indexacao" && currentUser?.role !== "gestor_documentos" && (
                          <>
                          <Button variant="ghost" size="icon" onClick={() => openEditDialog(user)}>
                            <Edit className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="icon" onClick={() => handleDeleteUser(user.id)}>
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                          </>
                          )}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
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
            <div className="space-y-2">
              <Label>Telefone</Label>
              <Input 
                value={formData.phone} 
                onChange={(e) => setFormData({ ...formData, phone: e.target.value })} 
              />
            </div>
            <div className="space-y-2">
              <Label>Perfil</Label>
              <Select value={formData.role} onValueChange={(value) => setFormData({ ...formData, role: value })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="consultor">Consultor</SelectItem>
                  <SelectItem value="intermediario">Intermediário de Crédito</SelectItem>
                  <SelectItem value="diretor">Diretor(a)</SelectItem>
                  <SelectItem value="administrativo">Administrativo(a)</SelectItem>
                  <SelectItem value="indexacao">Indexação</SelectItem>
                  <SelectItem value="ceo">CEO</SelectItem>
                  <SelectItem value="admin">Administrador</SelectItem>
                </SelectContent>
              </Select>
            </div>
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
              <Input 
                type="password" 
                value={formData.password} 
                onChange={(e) => setFormData({ ...formData, password: e.target.value })} 
                placeholder="Digite apenas se quiser alterar"
              />
            </div>
            <DialogFooter>
              <Button type="submit" disabled={formLoading}>
                {formLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Salvar"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  );
};

export default UsersManagementPage;
