/**
 * StatusBadge — canonical status pill (promoted from DashboardShared).
 *
 * Modes:
 * 1) Workflow: pass `workflowStatuses` (array of { name, label, color, order })
 * 2) Map: pass `statusMap` ({ [status]: { label, className?, color?, icon? } })
 * 3) Fallback: outline Badge with raw status string
 *
 * Prefer Shadcn semantic tokens over raw Tailwind color utilities.
 */
import { Badge } from "../ui/badge";
import { cn } from "@/lib/utils";

/** Workflow color keys → Shadcn token classes */
export const WORKFLOW_COLOR_CLASSES = {
  yellow: "bg-accent/15 text-accent-foreground border-accent/30",
  blue: "bg-primary/10 text-primary border-primary/20",
  orange: "bg-accent/20 text-foreground border-accent/40",
  green: "bg-secondary text-secondary-foreground border-border",
  red: "bg-destructive/10 text-destructive border-destructive/20",
  purple: "bg-primary/15 text-primary border-primary/25",
  indigo: "bg-primary/10 text-primary border-primary/20",
  gray: "bg-muted text-muted-foreground border-border",
};

function resolveLabel(raw, fallback) {
  if (raw == null) return fallback;
  if (typeof raw === "string") return raw;
  if (typeof raw === "object") return raw.label || raw.value || String(raw);
  return String(raw);
}

/**
 * @param {string} status
 * @param {Array} [workflowStatuses]
 * @param {Record<string, {label?: string, className?: string, color?: string, icon?: React.ComponentType}>} [statusMap]
 * @param {boolean} [showOrder=true]
 * @param {string} [className]
 */
export function StatusBadge({
  status,
  workflowStatuses,
  statusMap,
  showOrder = true,
  className,
}) {
  if (Array.isArray(workflowStatuses) && workflowStatuses.length > 0) {
    const statusInfo = workflowStatuses.find((s) => s.name === status);
    if (!statusInfo) {
      return <Badge variant="outline" className={className}>{status}</Badge>;
    }

    const label = resolveLabel(statusInfo.label, status);
    const tokenClass =
      WORKFLOW_COLOR_CLASSES[statusInfo.color] || WORKFLOW_COLOR_CLASSES.gray;
    const orderPrefix = showOrder && statusInfo.order != null
      ? `${statusInfo.order} - `
      : "";

    return (
      <Badge className={cn(tokenClass, "border", className)}>
        {orderPrefix}{label}
      </Badge>
    );
  }

  if (statusMap && status) {
    const entry = statusMap[status] || statusMap.default || Object.values(statusMap)[0];
    if (!entry) {
      return <Badge variant="outline" className={className}>{status}</Badge>;
    }

    const Icon = entry.icon;
    const label = entry.label || status;
    const colorClass = entry.className || entry.color || "";

    return (
      <Badge
        variant="outline"
        className={cn(colorClass, Icon && "flex items-center gap-1", className)}
      >
        {Icon ? <Icon className="h-3 w-3" aria-hidden="true" /> : null}
        {label}
      </Badge>
    );
  }

  return (
    <Badge variant="outline" className={className}>
      {status}
    </Badge>
  );
}

export default StatusBadge;
