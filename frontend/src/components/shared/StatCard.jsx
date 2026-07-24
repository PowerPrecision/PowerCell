/**
 * StatCard — canonical KPI / metric card (promoted from DashboardShared).
 *
 * Supports both dashboard API (`label`, `iconColor`, `bgColor`, `onClick`)
 * and admin API (`title`, `color`) for a single shared implementation.
 */
import { Card, CardContent } from "../ui/card";
import { cn } from "@/lib/utils";
import { safeString } from "../../utils/safeString";

/**
 * @param {React.ComponentType} [icon]
 * @param {string|number} value
 * @param {string} [label]
 * @param {string} [title] — alias for label (admin pages)
 * @param {string} [iconColor]
 * @param {string} [bgColor]
 * @param {string} [color] — value/icon text color (admin pages)
 * @param {string} [subtitle]
 * @param {Function} [onClick]
 * @param {string} [className]
 * @param {"default"|"inline"} [variant="default"]
 */
export function StatCard({
  icon: Icon,
  value,
  label,
  title,
  iconColor = "text-primary",
  bgColor = "bg-secondary",
  color,
  subtitle,
  onClick,
  className,
  variant = "default",
}) {
  const displayLabel = label ?? title ?? "";
  const displayValue = typeof value === "number" ? value : safeString(value);
  const valueColor = color || "";
  const resolvedIconColor = color || iconColor;
  const isClickable = typeof onClick === "function";

  if (variant === "inline") {
    return (
      <Card
        className={cn(
          "border-border",
          isClickable && "cursor-pointer hover:shadow-md transition-shadow",
          className
        )}
        onClick={onClick}
      >
        <CardContent className="p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm text-muted-foreground truncate">{displayLabel}</p>
              <p className={cn("text-2xl font-bold", valueColor)}>{displayValue}</p>
              {subtitle && (
                <p className="text-xs text-muted-foreground mt-1 truncate">{subtitle}</p>
              )}
            </div>
            {Icon && (
              <Icon className={cn("h-8 w-8 shrink-0 opacity-50", resolvedIconColor)} aria-hidden="true" />
            )}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card
      className={cn(
        "border-border",
        isClickable && "cursor-pointer hover:shadow-md transition-shadow",
        className
      )}
      onClick={onClick}
    >
      <CardContent className="pt-6">
        <div className="flex items-center gap-4">
          {Icon && (
            <div className={cn("p-3 rounded-lg", bgColor)}>
              <Icon className={cn("h-6 w-6", resolvedIconColor)} aria-hidden="true" />
            </div>
          )}
          <div className="min-w-0">
            <p className={cn("text-2xl font-bold", valueColor)}>{displayValue}</p>
            <p className="text-sm text-muted-foreground truncate">{displayLabel}</p>
            {subtitle && (
              <p className="text-xs text-muted-foreground mt-0.5 truncate">{subtitle}</p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default StatCard;
