import { Building2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { etiquetaDaEmpresaDona } from "@/utils/empresaDona";

/**
 * Etiqueta (só leitura) com a empresa dona do processo, no cabeçalho do
 * detalhe. Um processo partilhado por outra rede ganha o destaque «Partilhado».
 *
 * @param {{empresaDona?: object|null}} props `empresa_dona` tal como vem do servidor.
 */
export default function EmpresaDonaTag({ empresaDona }) {
  const etiqueta = etiquetaDaEmpresaDona(empresaDona);
  if (!etiqueta) return null;
  return (
    <Badge
      variant={etiqueta.partilhado ? "secondary" : "outline"}
      className="gap-1 font-medium"
      title={etiqueta.titulo}
      data-testid="empresa-dona-tag"
    >
      <Building2 className="h-3 w-3 shrink-0" aria-hidden="true" />
      <span>{etiqueta.nome}</span>
      {etiqueta.partilhado ? <span className="text-muted-foreground">· Partilhado</span> : null}
    </Badge>
  );
}
