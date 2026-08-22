/**
 * PACOTE FK — Painel de filtros da listagem de Clientes.
 * Só campos da entidade Cliente (origem, tipo, estado). Sem filtros de processo.
 */
import { Button } from "../ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { Filter, RotateCcw } from "lucide-react";

export const CLIENT_FONTE_OPTIONS = [
  { value: "staff_created", label: "Criado pela equipa" },
  { value: "Website", label: "Website" },
  { value: "Manual", label: "Manual" },
  { value: "Indicação", label: "Indicação" },
  { value: "Telefone", label: "Telefone" },
  { value: "Email", label: "Email" },
  { value: "Feira", label: "Feira" },
  { value: "trello", label: "Trello" },
  { value: "auto_created", label: "Automático" },
];

export const CLIENT_TIPO_OPTIONS = [
  { value: "particular", label: "Particular" },
  { value: "dois_titulares", label: "Dois titulares" },
  { value: "empresa", label: "Empresa" },
];

export const CLIENT_STATUS_OPTIONS = [
  { value: "active", label: "Ativos" },
  { value: "inactive", label: "Inativos" },
  { value: "deleted", label: "Eliminados" },
];

export default function ClientFilters({
  fonte = "all",
  onFonteChange,
  tipo = "all",
  onTipoChange,
  status = "all",
  onStatusChange,
  onReset,
}) {
  const hasActive =
    (fonte && fonte !== "all") ||
    (tipo && tipo !== "all") ||
    (status && status !== "all");

  return (
    <div
      className="flex flex-wrap items-center gap-2"
      data-testid="client-filters"
    >
      <Select
        value={fonte || "all"}
        onValueChange={(v) => onFonteChange?.(v === "all" ? "" : v)}
      >
        <SelectTrigger
          className="w-full sm:w-[160px]"
          data-testid="client-fonte-filter"
        >
          <Filter className="h-4 w-4 mr-2 text-muted-foreground" />
          <SelectValue placeholder="Origem" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">Todas as origens</SelectItem>
          {CLIENT_FONTE_OPTIONS.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={tipo || "all"}
        onValueChange={(v) => onTipoChange?.(v === "all" ? "" : v)}
      >
        <SelectTrigger
          className="w-full sm:w-[160px]"
          data-testid="client-tipo-filter"
        >
          <SelectValue placeholder="Tipo de Cliente" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">Todos os tipos</SelectItem>
          {CLIENT_TIPO_OPTIONS.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={status || "all"}
        onValueChange={(v) => onStatusChange?.(v === "all" ? "" : v)}
      >
        <SelectTrigger
          className="w-full sm:w-[150px]"
          data-testid="client-status-filter"
        >
          <SelectValue placeholder="Estado" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">Todos os estados</SelectItem>
          {CLIENT_STATUS_OPTIONS.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
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
        data-testid="client-filters-reset"
      >
        <RotateCcw className="h-4 w-4" />
        Limpar Filtros
      </Button>
    </div>
  );
}
