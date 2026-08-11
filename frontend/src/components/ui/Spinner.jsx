/**
 * Spinner — global loading indicator (thin Loader2 wrapper).
 */
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const SIZE_CLASS = {
  sm: "h-4 w-4",
  md: "h-6 w-6",
  lg: "h-8 w-8",
};

/**
 * @param {"sm"|"md"|"lg"|number} [size="md"]
 * @param {string} [className]
 */
export function Spinner({ className, size = "md", ...props }) {
  const sizeClass = typeof size === "number"
    ? undefined
    : (SIZE_CLASS[size] || SIZE_CLASS.md);

  return (
    <Loader2
      className={cn("animate-spin", sizeClass, className)}
      style={typeof size === "number" ? { width: size, height: size } : undefined}
      aria-hidden="true"
      {...props}
    />
  );
}

/**
 * Full-area loading placeholder used by dashboards.
 */
export function LoadingSpinner({ className, spinnerClassName }) {
  return (
    <div
      className={cn("flex items-center justify-center h-64", className)}
      role="status"
      aria-label="A carregar"
    >
      <Spinner size="lg" className={cn("text-primary", spinnerClassName)} />
    </div>
  );
}

export default Spinner;
