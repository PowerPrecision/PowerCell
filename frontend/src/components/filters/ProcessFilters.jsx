/**
 * PACOTE FK — Painel de filtros da listagem de Processos.
 * Independente dos filtros de Clientes. Inclui Estado, Tipo e Atribuído a.
 */
import { Button } from "../ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { Filter, RotateCcw, UserCheck } from "lucide-react";
import { PROCESS_TYPE_LABELS } from "../SmartClientSearch";
import {
  useAssignmentUsersQuery,
  useWorkflowStatusesQuery,
} from "../../hooks/queries/useUsersQuery";

function userLabel(user) {
  const name = user?.name || user?.email || user?.id || "Utilizador";
  const role = user?.role || user?.effective_role;
  return role ? `${name} (${role})` : name;
}

export default function ProcessFilters({
  status = "all",
  onStatusChange,
  processType = "all",
  onProcessTypeChange,
  assignedUserId = "all",
  onAssignedUserIdChange,
  onReset,
}) {
  const { users, isLoading: usersLoading } = useAssignmentUsersQuery();
  const { statuses } = useWorkflowStatusesQuery();

  const hasActive =
    (status && status !== "all") ||
    (processType && processType !== "all") ||
    (assignedUserId && assignedUserId !== "all");

  return (
    <div
      className="flex flex-wrap items-center gap-2"
      data-testid="process-filters"
    >
      <Select
        value={status || "all"}
        onValueChange={(v) => onStatusChange?.(v === "all" ? "" : v)}
      >
        <SelectTrigger
          className="w-full sm:w-[180px]"
          data-testid="process-status-filter"
        >
          <Filter className="h-4 w-4 mr-2 text-muted-foreground" />
          <SelectValue placeholder="Estado do Processo" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">Todos os estados</SelectItem>
          {statuses.map((s) => (
            <SelectItem key={s.name || s.id} value={s.name}>
              {s.label || s.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={processType || "all"}
        onValueChange={(v) => onProcessTypeChange?.(v === "all" ? "" : v)}
      >
        <SelectTrigger
          className="w-full sm:w-[180px]"
          data-testid="process-type-filter"
        >
          <SelectValue placeholder="Tipo" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">Todos os tipos</SelectItem>
          {Object.entries(PROCESS_TYPE_LABELS).map(([value, label]) => (
            <SelectItem key={value} value={value}>
              {label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={assignedUserId || "all"}
        onValueChange={(v) => onAssignedUserIdChange?.(v === "all" ? "" : v)}
        disabled={usersLoading}
      >
        <SelectTrigger
          className="w-full sm:w-[200px]"
          data-testid="process-assigned-user-filter"
        >
          <UserCheck className="h-4 w-4 mr-2 text-muted-foreground" />
          <SelectValue placeholder="Atribuído a" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">Todos os utilizadores</SelectItem>
          {users.map((u) => (
            <SelectItem key={u.id} value={u.id}>
              {userLabel(u)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={onReset}
        disabled={!hasActive}
        className="gap-2"
        data-testid="process-filters-reset"
      >
        <RotateCcw className="h-4 w-4" />
        Limpar Filtros
      </Button>
    </div>
  );
}
