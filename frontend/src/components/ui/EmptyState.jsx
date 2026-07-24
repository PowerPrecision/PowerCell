/**
 * EmptyState — reusable empty list / empty panel placeholder.
 */
import { cn } from "@/lib/utils";

/**
 * @param {React.ComponentType} [icon]
 * @param {string} [message]
 * @param {string} [title]
 * @param {React.ReactNode} [action]
 * @param {string} [className]
 */
export function EmptyState({
  icon: Icon,
  message,
  title,
  action,
  className,
}) {
  return (
    <div className={cn("text-center py-12 text-muted-foreground", className)}>
      {Icon && <Icon className="h-12 w-12 mx-auto mb-4 opacity-50" aria-hidden="true" />}
      {title && <p className="text-base font-medium text-foreground mb-1">{title}</p>}
      {message && <p>{message}</p>}
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}

export default EmptyState;
