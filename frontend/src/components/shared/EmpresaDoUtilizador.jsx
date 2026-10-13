/**
 * Etiqueta com a empresa de uma pessoa, à frente do nome nas listas de atribuição.
 * Não desenha nada quando o servidor não disse a empresa (um rótulo vazio é ruído).
 */
import { Building2 } from "lucide-react";
import { etiquetaDaEmpresa } from "../../utils/empresaDoUtilizador";

export default function EmpresaDoUtilizador({ utilizador, className = "" }) {
  const empresa = etiquetaDaEmpresa(utilizador);
  if (!empresa) return null;
  return (
    <span
      data-testid="empresa-do-utilizador"
      title={`Empresa: ${empresa}`}
      className={`inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground ${className}`}
    >
      <Building2 className="h-3 w-3" aria-hidden="true" />
      {empresa}
    </span>
  );
}
