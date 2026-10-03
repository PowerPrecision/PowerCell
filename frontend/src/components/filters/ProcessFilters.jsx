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
import { Filter, RotateCcw, Sparkles, UserCheck, ChevronDown } from "lucide-react";
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
  sub35 = false,
  onSub35Change,
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
    // O Sub35 ENTRA aqui: um filtro activo com o "Limpar Filtros"
    // desactivado deixa o utilizador preso numa lista reduzida sem ver
    // porquê — e sem forma de sair sem mexer no URL.
    Boolean(sub35) ||
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

      {/* Ponto 1 — Sub35. Um interruptor e não um `Select` de três
          valores: "não é Sub35" juntaria quem tem mais de 35 anos com
          quem não tem data de nascimento na ficha, e o servidor recusa
          essa pergunta de propósito (ver `services/sub35.py`). */}
      <Button
        type="button"
        variant={sub35 ? "default" : "outline"}
        size="sm"
        aria-pressed={Boolean(sub35)}
        onClick={() => onSub35Change?.(!sub35)}
        className="gap-2"
        data-testid="process-sub35-filter"
        title={sub35 ? "A mostrar só processos Sub35" : "Mostrar só processos Sub35"}
      >
        <Sparkles className="h-4 w-4" />
        Sub35
      </Button>

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
