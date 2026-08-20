/**
 * Tab Utilizadores — contas + acessos UCR (Pacotes DW/DY).
 *
 * Tabela de utilizadores com DropdownMenu de acções básicas
 * (Editar Dados, Gerir Acessos UCR, Redefinir Password, Desativar)
 * e Sheet para adicionar Empresa + Cargo.
 */
import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  KeyRound,
  Lock,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Trash2,
  UserCheck,
  UserPlus,
  UserX,
  Users,
} from "lucide-react";
import { toast } from "sonner";
import {
  assignUserRole,
  createUser,
  deleteUser,
  deleteUserCompanyRole,
  getCompanies,
  getUserCompanyRoles,
  getUsers,
  updateUser,
} from "../../services/api";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import {
  groupRolesByUserId,
  isCompanyActive,
  isUserActive,
  normalizeCompaniesPayload,
  normalizeRolesPayload,
} from "../../utils/organizationAdmin";
import {
  ROLE_SHORT_LABELS,
  UCR_ASSIGNABLE_ROLES,
} from "../../utils/roleUtils";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { ScrollArea } from "../ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "../ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../ui/table";
import EmptyState from "../ui/EmptyState";
import { TableSkeleton } from "../ui/skeletons";
import {
  UserCreateDialog,
  UserEditDialog,
  UserPasswordDialog,
} from "./UserAccountDialogs";

const USERS_QUERY_KEY = ["org-admin-users"];
const UCR_QUERY_KEY = ["org-admin-ucrs"];
const UNDO_WINDOW_MS = 8000;

export default function UsersAccessAdminTab() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [selectedUser, setSelectedUser] = useState(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [newCompanyId, setNewCompanyId] = useState("");
  const [newRole, setNewRole] = useState("");
  const [saving, setSaving] = useState(false);

  const {
    data: users = [],
    isLoading: usersLoading,
    isError: usersError,
  } = useQuery({
    queryKey: USERS_QUERY_KEY,
    queryFn: async () => {
      const res = await getUsers();
      return Array.isArray(res.data) ? res.data : res.data?.users || [];
    },
  });

  const {
    data: roles = [],
    isError: rolesError,
  } = useQuery({
    queryKey: UCR_QUERY_KEY,
    queryFn: async () => {
      const res = await getUserCompanyRoles();
      return normalizeRolesPayload(res.data);
    },
  });

  const { data: companies = [] } = useQuery({
    queryKey: ["org-admin-companies", ""],
    queryFn: async () => {
      const res = await getCompanies();
      return normalizeCompaniesPayload(res.data);
    },
  });

  useEffect(() => {
    if (usersError) toast.error("Erro ao carregar utilizadores.");
  }, [usersError]);

  useEffect(() => {
    if (rolesError) toast.error("Erro ao carregar acessos UCR.");
  }, [rolesError]);

  const rolesByUser = useMemo(() => groupRolesByUserId(roles), [roles]);

  const filteredUsers = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return users;
    return users.filter((u) => {
      const hay = `${u.name || ""} ${u.email || ""}`.toLowerCase();
      return hay.includes(term);
    });
  }, [users, search]);

  const selectedRoles = selectedUser
    ? rolesByUser[selectedUser.id] || []
    : [];

  const assignedCompanyIds = new Set(
    selectedRoles.map((r) => r.company_id).filter(Boolean),
  );

  const availableCompanies = companies.filter(
    (c) => isCompanyActive(c) && !assignedCompanyIds.has(c.id),
  );

  const invalidateUsers = () => {
    queryClient.invalidateQueries({ queryKey: USERS_QUERY_KEY });
    queryClient.invalidateQueries({ queryKey: ["users"] });
  };

  const setUsersCache = (updater) =>
    queryClient.setQueryData(USERS_QUERY_KEY, (prev = []) =>
      typeof updater === "function" ? updater(prev) : updater,
    );

  const openAccessSheet = (user) => {
    setSelectedUser(user);
    setNewCompanyId("");
    setNewRole("");
    setSheetOpen(true);
  };

  const openEdit = (user) => {
    setSelectedUser(user);
    setEditOpen(true);
  };

  const openPassword = (user) => {
    setSelectedUser(user);
    setPasswordOpen(true);
  };

  const handleCreateUser = async (payload) => {
    setSaving(true);
    try {
      await createUser(payload);
      toast.success("Utilizador criado com sucesso");
      if (payload.password) {
        toast.success(
          `Password: ${payload.password}. Copie e envie ao utilizador por um canal seguro.`,
          { duration: 10000 },
        );
      }
      invalidateUsers();
      return true;
    } catch (err) {
      toast.error(
        extractErrorMessage(
          err.response?.data?.detail || err.response?.data?.error,
          "Erro ao criar utilizador",
        ),
      );
      return false;
    } finally {
      setSaving(false);
    }
  };

  const handleEditUser = async (payload) => {
    if (!selectedUser?.id) return false;
    setSaving(true);
    try {
      await updateUser(selectedUser.id, payload);
      toast.success("Utilizador actualizado com sucesso");
      invalidateUsers();
      return true;
    } catch (err) {
      toast.error(
        extractErrorMessage(
          err.response?.data?.detail || err.response?.data?.error,
          "Erro ao actualizar utilizador",
        ),
      );
      return false;
    } finally {
      setSaving(false);
    }
  };

  const handleResetPassword = async (password) => {
    if (!selectedUser?.id) return false;
    setSaving(true);
    try {
      await updateUser(selectedUser.id, { password });
      toast.success(`Password redefinida para ${selectedUser.name}`);
      return true;
    } catch (err) {
      toast.error(
        extractErrorMessage(
          err.response?.data?.detail || err.response?.data?.error,
          "Erro ao redefinir password",
        ),
      );
      return false;
    } finally {
      setSaving(false);
    }
  };

  const handleToggleUserStatus = async (user) => {
    const currentlyActive = isUserActive(user);
    if (currentlyActive && user.role === "admin") {
      toast.error("Não é possível desactivar o utilizador administrador.");
      return;
    }
    try {
      await updateUser(user.id, { is_active: !currentlyActive });
      toast.success(
        `Utilizador ${currentlyActive ? "desactivado" : "activado"} com sucesso`,
      );
      invalidateUsers();
    } catch (err) {
      toast.error(
        extractErrorMessage(
          err.response?.data?.detail || err.response?.data?.error,
          "Erro ao actualizar utilizador",
        ),
      );
    }
  };

  const handleDeleteUser = (user) => {
    if (!user?.id) return;
    const restoreUser = () =>
      setUsersCache((prev) =>
        [...prev, user].sort((a, b) => (a.name || "").localeCompare(b.name || "")),
      );

    setUsersCache((prev) => prev.filter((u) => u.id !== user.id));

    const commitTimer = setTimeout(async () => {
      try {
        await deleteUser(user.id);
        invalidateUsers();
      } catch (err) {
        restoreUser();
        toast.error(
          extractErrorMessage(
            err.response?.data?.detail || err.response?.data?.error,
            "Erro ao eliminar utilizador",
          ),
        );
      }
    }, UNDO_WINDOW_MS);

    toast.success(`Utilizador "${user.name}" eliminado`, {
      action: {
        label: "Desfazer",
        onClick: () => {
          clearTimeout(commitTimer);
          restoreUser();
          toast.success("Acção desfeita");
        },
      },
      duration: UNDO_WINDOW_MS,
    });
  };

  const handleAddAccess = async (e) => {
    e.preventDefault();
    if (!selectedUser?.id) return;
    if (!newCompanyId || !newRole) {
      toast.error("Escolha a empresa e o cargo.");
      return;
    }
    const company = companies.find((c) => c.id === newCompanyId);
    if (!company) {
      toast.error("Empresa inválida.");
      return;
    }

    setSaving(true);
    try {
      await assignUserRole(selectedUser.id, {
        company_id: company.id,
        company_name: company.name,
        role: newRole,
      });
      toast.success(
        `Acesso adicionado: ${ROLE_SHORT_LABELS[newRole] || newRole} em ${company.name}.`,
      );
      setNewCompanyId("");
      setNewRole("");
      queryClient.invalidateQueries({ queryKey: UCR_QUERY_KEY });
    } catch (err) {
      toast.error(
        extractErrorMessage(
          err.response?.data?.detail || err.response?.data?.error,
          "Erro ao adicionar o acesso.",
        ),
      );
    } finally {
      setSaving(false);
    }
  };

  const handleRemoveAccess = async (roleId) => {
    try {
      await deleteUserCompanyRole(roleId);
      toast.success("Acesso removido.");
      queryClient.invalidateQueries({ queryKey: UCR_QUERY_KEY });
    } catch (err) {
      toast.error(
        extractErrorMessage(
          err.response?.data?.detail || err.response?.data?.error,
          "Erro ao remover o acesso.",
        ),
      );
    }
  };

  return (
    <div className="space-y-4" data-testid="org-admin-users-tab">
      <div className="flex flex-col sm:flex-row gap-3 sm:items-center sm:justify-between">
        <div className="relative max-w-sm w-full">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Pesquisar utilizador..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
            data-testid="org-admin-users-search"
          />
        </div>
        <Button
          size="sm"
          className="gap-1.5 shrink-0"
          onClick={() => setCreateOpen(true)}
          data-testid="btn-new-user"
        >
          <UserPlus className="h-4 w-4" />
          Novo Utilizador
        </Button>
      </div>

      {usersLoading && users.length === 0 ? (
        <TableSkeleton rows={6} />
      ) : filteredUsers.length === 0 ? (
        <EmptyState
          icon={Users}
          title="Nenhum utilizador"
          message="Não foram encontrados utilizadores com os filtros actuais."
        />
      ) : (
        <ScrollArea className="h-fit max-h-[560px] rounded-md border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Utilizador</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead>Acessos</TableHead>
                <TableHead className="text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredUsers.map((user) => {
                const ucrs = rolesByUser[user.id] || [];
                const active = isUserActive(user);
                return (
                  <TableRow key={user.id} data-testid={`user-row-${user.id}`}>
                    <TableCell className="font-medium">{user.name}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {user.email}
                    </TableCell>
                    <TableCell>
                      <Badge variant={active ? "secondary" : "destructive"}>
                        {active ? "Ativo" : "Inativo"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {ucrs.length === 0 ? (
                        <span className="text-muted-foreground text-sm">
                          Sem acessos UCR
                        </span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {ucrs.map((ucr) => (
                            <Badge key={ucr.id} variant="secondary">
                              {ucr.company_name} · {ROLE_SHORT_LABELS[ucr.role] || ucr.role}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Ações de ${user.name}`}
                            data-testid={`btn-user-actions-${user.id}`}
                          >
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => openEdit(user)}>
                            <Pencil className="h-4 w-4" />
                            Editar Dados
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => openAccessSheet(user)}>
                            <KeyRound className="h-4 w-4" />
                            Gerir Acessos UCR
                          </DropdownMenuItem>
                          {user.role !== "parceiro" ? (
                            <DropdownMenuItem onClick={() => openPassword(user)}>
                              <Lock className="h-4 w-4" />
                              Redefinir Password
                            </DropdownMenuItem>
                          ) : null}
                          <DropdownMenuItem
                            disabled={active && user.role === "admin"}
                            onClick={() => handleToggleUserStatus(user)}
                          >
                            {active ? (
                              <UserX className="h-4 w-4" />
                            ) : (
                              <UserCheck className="h-4 w-4" />
                            )}
                            {active ? "Desativar" : "Ativar"}
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            className="text-destructive focus:text-destructive"
                            onClick={() => handleDeleteUser(user)}
                            data-testid={`btn-delete-user-${user.id}`}
                          >
                            <Trash2 className="h-4 w-4" />
                            Eliminar
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </ScrollArea>
      )}

      <UserCreateDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onSubmit={handleCreateUser}
        saving={saving}
      />
      <UserEditDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        user={selectedUser}
        onSubmit={handleEditUser}
        saving={saving}
      />
      <UserPasswordDialog
        open={passwordOpen}
        onOpenChange={setPasswordOpen}
        user={selectedUser}
        onSubmit={handleResetPassword}
        saving={saving}
      />

      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent
          side="right"
          className="w-full sm:max-w-lg overflow-y-auto"
          data-testid="user-access-sheet"
        >
          <SheetHeader>
            <SheetTitle>Acessos de {selectedUser?.name || "utilizador"}</SheetTitle>
            <SheetDescription>
              Defina em que empresa este utilizador opera e com que cargo
              (ex.: Diretor na Empresa A, Consultor na Empresa B).
            </SheetDescription>
          </SheetHeader>

          <div className="mt-6 space-y-6">
            <div>
              <p className="text-sm font-medium mb-2">Acessos actuais</p>
              {selectedRoles.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Ainda não tem nenhum acesso UCR.
                </p>
              ) : (
                <ScrollArea className="h-fit max-h-[240px] rounded-md border border-border">
                  <ul className="divide-y divide-border">
                    {selectedRoles.map((ucr) => (
                      <li
                        key={ucr.id}
                        className="flex items-center justify-between gap-2 p-3"
                        data-testid={`ucr-row-${ucr.id}`}
                      >
                        <div className="min-w-0">
                          <p className="text-sm font-medium truncate">
                            {ucr.company_name}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {ROLE_SHORT_LABELS[ucr.role] || ucr.role}
                            {ucr.is_default ? " · predefinido" : ""}
                          </p>
                        </div>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label="Remover acesso"
                          onClick={() => handleRemoveAccess(ucr.id)}
                          data-testid={`btn-remove-ucr-${ucr.id}`}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </li>
                    ))}
                  </ul>
                </ScrollArea>
              )}
            </div>

            <form onSubmit={handleAddAccess} className="space-y-3 rounded-md border border-border p-4">
              <p className="text-sm font-medium flex items-center gap-1.5">
                <Plus className="h-4 w-4" />
                Novo acesso
              </p>
              <div className="space-y-2">
                <Label>Empresa</Label>
                <Select
                  value={newCompanyId}
                  onValueChange={setNewCompanyId}
                  disabled={availableCompanies.length === 0}
                >
                  <SelectTrigger data-testid="ucr-company-select">
                    <SelectValue
                      placeholder={
                        availableCompanies.length === 0
                          ? "Sem empresas disponíveis"
                          : "Seleccionar empresa"
                      }
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {availableCompanies.map((company) => (
                      <SelectItem key={company.id} value={company.id}>
                        {company.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Cargo</Label>
                <Select value={newRole} onValueChange={setNewRole}>
                  <SelectTrigger data-testid="ucr-role-select">
                    <SelectValue placeholder="Seleccionar cargo" />
                  </SelectTrigger>
                  <SelectContent>
                    {UCR_ASSIGNABLE_ROLES.map((role) => (
                      <SelectItem key={role} value={role}>
                        {ROLE_SHORT_LABELS[role] || role}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button
                type="submit"
                className="w-full"
                disabled={saving || !newCompanyId || !newRole}
                data-testid="btn-add-ucr"
              >
                {saving ? "A guardar..." : "Adicionar acesso"}
              </Button>
            </form>
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
