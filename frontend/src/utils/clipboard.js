/**
 * Clipboard utilities with macOS/Safari fallback.
 *
 * navigator.clipboard.writeText() fails on Safari when called outside
 * a direct user gesture (e.g. after an async API response). This utility
 * provides a fallback that shows the link in a selectable input inside
 * a toast notification.
 *
 * The fallback uses a dedicated React component with useRef + useEffect
 * for reliable auto-focus inside the toast portal (autoFocus attribute
 * does not work reliably in portal-based toasts).
 */
import { useRef, useEffect } from "react";
import { toast } from "sonner";

/**
 * Fallback content rendered inside the toast when clipboard API fails.
 * Uses useRef + useEffect for reliable auto-focus/select in toast portals.
 */
const ClipboardFallbackContent = ({ text }) => {
  const inputRef = useRef(null);

  useEffect(() => {
    // Small delay to ensure the toast portal DOM is fully mounted
    const timer = setTimeout(() => {
      if (inputRef.current) {
        inputRef.current.focus();
        inputRef.current.select();
      }
    }, 80);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">
        ⚠️ Não foi possível copiar automaticamente. Selecione e copie o link:
      </p>
      <input
        ref={inputRef}
        type="text"
        readOnly
        value={text}
        onClick={(e) => e.target.select()}
        onFocus={(e) => e.target.select()}
        className="w-full px-3 py-2 text-xs bg-muted border rounded-md font-mono"
      />
      <p className="text-[11px] text-muted-foreground">
        Cmd+C (Mac) ou Ctrl+C (Windows) para copiar
      </p>
    </div>
  );
};

/**
 * Safely copy text to clipboard with a macOS/Safari fallback.
 * If clipboard API fails (common after async operations on Safari),
 * shows a toast with the link in a selectable input so the user can
 * manually copy with Cmd+C / Ctrl+C.
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
      () => <ClipboardFallbackContent text={text} />,
      { duration: 15000, className: "max-w-sm" }
    );
  }
};
