/**
 * TemaToggle — o botão explícito de vista noturna (claro/escuro).
 *
 * COMPONENTE DE APRESENTAÇÃO: não sabe onde a preferência é guardada. O
 * Portal do Parceiro liga-o ao tema global (`useTheme`); o Portal do Cliente a
 * `usePortalTheme` (preferência própria, com o aspecto claro por omissão).
 */
import { Moon, Sun } from "lucide-react";

import { Button } from "../ui/button";
import { cn } from "../../lib/utils";

/**
 * @param {Object} props
 * @param {boolean} props.escuro — a vista noturna está activa?
 * @param {() => void} props.onAlternar
 * @param {string} [props.className]
 * @param {"icon"|"sm"} [props.size]
 */
export default function TemaToggle({ escuro, onAlternar, className, size = "icon" }) {
  const rotulo = escuro ? "Desativar vista noturna" : "Ativar vista noturna";
  return (
    <Button
      type="button"
      variant="outline"
      size={size}
      onClick={onAlternar}
      aria-label={rotulo}
      aria-pressed={escuro}
      title={rotulo}
      data-testid="alternar-tema"
      className={cn(className)}
    >
      {escuro ? <Sun className="h-4 w-4" aria-hidden="true" /> : <Moon className="h-4 w-4" aria-hidden="true" />}
    </Button>
  );
}
