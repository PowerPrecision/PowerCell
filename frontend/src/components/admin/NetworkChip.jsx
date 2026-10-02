/**
 * Chip da rede (grupo) de uma empresa (Lote 4, ponto 5).
 *
 * Componente de APRESENTAÇÃO: recebe o slug e a etiqueta já resolvida
 * (ver `utils/redesDeEmpresas.js`) e desenha-a. Não sabe de listas nem de
 * ambiguidade — quem decide o texto é o contentor, porque a decisão
 * depende das OUTRAS empresas no ecrã.
 *
 * Duas coisas que não são decoração:
 *
 * 1. **"Sem grupo" tem aparência própria.** Uma empresa sem `network_id`
 *    é uma ILHA: não partilha dados com nenhuma outra. Desenhá-la como as
 *    restantes fazia o estado mais consequente do ecrã passar por um
 *    campo em branco.
 *
 * 2. **O slug cru vai no `title`.** O rótulo bonito é para ler; o slug é
 *    o valor que de facto decide o isolamento, e tem de estar alcançável
 *    sem abrir o diálogo de edição.
 */
import { Network, Unlink } from "lucide-react";

import { Badge } from "../ui/badge";

/**
 * @param {object} props
 * @param {string} props.slug — `network_id` normalizado (`""` = sem rede)
 * @param {string} props.etiqueta — texto a mostrar (já desambiguado)
 * @param {boolean} [props.ambigua] — dois slugs com o mesmo rótulo no ecrã
 */
export default function NetworkChip({ slug, etiqueta, ambigua = false }) {
  if (!slug) {
    return (
      <Badge
        variant="outline"
        className="gap-1 border-dashed text-muted-foreground font-normal"
        title="Sem grupo: esta empresa é uma ilha — não partilha dados com nenhuma outra."
        data-testid="chip-rede-sem-grupo"
      >
        <Unlink className="h-3 w-3" />
        {etiqueta}
      </Badge>
    );
  }

  return (
    <Badge
      variant="secondary"
      className="gap-1 font-normal"
      title={
        ambigua
          ? `Rede: ${slug} — há outra rede com um nome parecido neste ecrã. ` +
            "Confirme se não é uma gralha."
          : `Rede: ${slug}`
      }
      data-testid={`chip-rede-${slug}`}
    >
      <Network className="h-3 w-3" />
      {etiqueta}
    </Badge>
  );
}
