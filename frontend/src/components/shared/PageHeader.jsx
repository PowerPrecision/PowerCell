/**
 * PageHeader — canonical page title block.
 *
 * Policy: content title lives here (once). Prefer not duplicating the same
 * string as DashboardLayout `title` unless the fixed header needs a short label.
 */
import { Button } from "../ui/button";
import { RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * @param {React.ComponentType} [icon]
 * @param {string} title
 * @param {React.ReactNode} [titleBadge] — rendered inline right after the title (e.g. a StatusBadge)
 * @param {string|React.ReactNode} [description]
 * @param {Function} [onRefresh]
 * @param {React.ReactNode} [actions] — right-side actions (alternative to onRefresh)
 * @param {string} [className]
 * @param {"h1"|"h2"} [as="h1"]
 */
export function PageHeader({
  icon: Icon,
  title,
  titleBadge,
  description,
  onRefresh,
  actions,
  className,
  as: Heading = "h1",
}) {
  return (
    <div className={cn("flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3", className)}>
      <div className="min-w-0">
        <Heading className="text-2xl font-bold flex items-center gap-2 flex-wrap text-foreground">
          {Icon && <Icon className="h-6 w-6 shrink-0 text-primary" aria-hidden="true" />}
          <span className="truncate">{title}</span>
          {titleBadge}
        </Heading>
        {description ? (
          typeof description === "string" ? (
            <p className="text-muted-foreground mt-0.5">{description}</p>
          ) : (
            <div className="text-muted-foreground mt-0.5">{description}</div>
          )
        ) : null}
      </div>
      {(actions || onRefresh) && (
        <div className="flex items-center gap-2 shrink-0 self-start">
          {actions}
          {onRefresh && (
            <Button variant="outline" onClick={onRefresh}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Atualizar
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

export default PageHeader;
