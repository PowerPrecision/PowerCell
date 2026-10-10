/**
 * O botão de vista noturna do Portal do Parceiro.
 *
 * O Portal do Parceiro é feito de tokens semânticos (`bg-background`,
 * `text-muted-foreground`…), por isso acompanha o tema global da aplicação
 * (`ThemeContext`, classe `dark` no `<html>`) sem restyle: o botão só liga a
 * escolha explícita do parceiro a esse tema (guardada no navegador).
 */
import TemaToggle from "@/components/shared/TemaToggle";
import { useTheme } from "@/contexts/ThemeContext";

export default function PartnerTemaToggle({ className }) {
  const { isDark, toggleTheme } = useTheme();
  return <TemaToggle escuro={isDark} onAlternar={toggleTheme} className={className} />;
}
