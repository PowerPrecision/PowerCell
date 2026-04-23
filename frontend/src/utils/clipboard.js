/**
 * Clipboard utilities with macOS/Safari fallback.
 *
 * navigator.clipboard.writeText() fails on Safari when called outside
 * a direct user gesture (e.g. after an async API response). This utility
 * provides a fallback that shows the link in a selectable input inside
 * a toast notification.
 */
import { toast } from "sonner";

/**
 * Safely copy text to clipboard with a macOS/Safari fallback.
 * If clipboard API fails, shows a toast with the link in a selectable input.
 *
 * @param {string} text - Text to copy
 * @param {string} successMessage - Message shown on successful copy
 */
export const safeCopyToClipboard = async (text, successMessage = "Link copiado para a área de transferência!") => {
  try {
    await navigator.clipboard.writeText(text);
    toast.success(successMessage);
  } catch {
    // Fallback for macOS Safari: show the link in a selectable input
    toast.custom(
      (t) => (
        <div className="space-y-2">
          <p className="text-sm font-medium">
            ⚠️ Não foi possível copiar automaticamente. Seleione e copie o link:
          </p>
          <input
            type="text"
            readOnly
            value={text}
            onClick={(e) => e.target.select()}
            className="w-full px-3 py-2 text-xs bg-muted border rounded-md font-mono"
            autoFocus
          />
          <p className="text-[11px] text-muted-foreground">
            Cmd+C (Mac) ou Ctrl+C (Windows) para copiar
          </p>
        </div>
      ),
      { duration: 15000, className: "max-w-sm" }
    );
  }
};
