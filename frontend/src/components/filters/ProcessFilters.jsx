/**
 * PACOTE FK / FL — Painel de filtros da listagem de Processos.
 * Independente dos filtros de Clientes. Inclui Estado, Tipo e Atribuído a
 * (multi-select + lógica E/OU).
 */
import { Button } from "../ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { Checkbox } from "../ui/checkbox";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { ToggleGroup, ToggleGroupItem } from "../ui/toggle-group";
import { ScrollArea } from "../ui/scroll-area";
import { Filter, RotateCcw, UserCheck, ChevronDown } from "lucide-react";
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

function toIdList(value) {
  if (Array.isArray(value)) {
    return value.filter(Boolean);
  }
  if (!value || value === "all") return [];
  return String(value)
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export default function ProcessFilters({
  status = "all",
  onStatusChange,
  processType = "all",
  onProcessTypeChange,
  assignedUserId = "all",
  assignedUserIds,
  onAssignedUserIdChange,
  onAssignedUserIdsChange,
  assignedLogic = "OR",
  onAssignedLogicChange,
  onReset,
}) {
  const { users, isLoading: usersLoading } = useAssignmentUsersQuery();
  const { statuses } = useWorkflowStatusesQuery();

  const selectedIds = toIdList(
    assignedUserIds !== undefined ? assignedUserIds : assignedUserId,
  );
  const logic = (assignedLogic || "OR").toUpperCase() === "AND" ? "AND" : "OR";

  const emitIds = (ids) => {
    if (onAssignedUserIdsChange) {
      onAssignedUserIdsChange(ids);
      return;
    }
    onAssignedUserIdChange?.(ids.length ? ids.join(",") : "");
  };

  const toggleUser = (id) => {
    const next = selectedIds.includes(id)
      ? selectedIds.filter((x) => x !== id)
      : [...selectedIds, id];
    emitIds(next);
  };

  const assignedLabel = (() => {
    if (selectedIds.length === 0) return "Todos os utilizadores";
    if (selectedIds.length === 1) {
      const match = users.find((u) => u.id === selectedIds[0]);
      return match ? userLabel(match) : "1 seleccionado";
    }
    return `${selectedIds.length} seleccionados`;
  })();

  const hasActive =
    (status && status !== "all") ||
    (processType && processType !== "all") ||
    selectedIds.length > 0;

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

      <Popover>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            disabled={usersLoading}
            className="w-full sm:w-[220px] justify-between font-normal"
            data-testid="process-assigned-user-filter"
          >
            <span className="flex items-center min-w-0">
              <UserCheck className="h-4 w-4 mr-2 shrink-0 text-muted-foreground" />
              <span className="truncate">{assignedLabel}</span>
            </span>
            <ChevronDown className="h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[280px] p-2" align="start">
          <ScrollArea className="h-[240px] pr-2">
            <label className="flex items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-accent cursor-pointer">
              <Checkbox
                checked={selectedIds.length === 0}
                onCheckedChange={() => emitIds([])}
              />
              Todos os utilizadores
            </label>
            {users.map((u) => (
              <label
                key={u.id}
                className="flex items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-accent cursor-pointer"
              >
                <Checkbox
                  checked={selectedIds.includes(u.id)}
                  onCheckedChange={() => toggleUser(u.id)}
                />
                <span className="truncate">{userLabel(u)}</span>
              </label>
            ))}
          </ScrollArea>
        </PopoverContent>
      </Popover>

      {selectedIds.length > 1 && (
        <ToggleGroup
          type="single"
          value={logic}
          onValueChange={(v) => {
            if (v) onAssignedLogicChange?.(v);
          }}
          variant="outline"
          size="sm"
          className="border border-input rounded-md"
          data-testid="process-assigned-logic"
        >
          <ToggleGroupItem value="AND" aria-label="Todos (E)" className="px-3 text-xs">
            E
          </ToggleGroupItem>
          <ToggleGroupItem value="OR" aria-label="Qualquer (OU)" className="px-3 text-xs">
            OU
          </ToggleGroupItem>
        </ToggleGroup>
      )}

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
