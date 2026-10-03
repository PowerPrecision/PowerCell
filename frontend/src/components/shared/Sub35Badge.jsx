/**
 * Etiqueta Sub35 (Lote 4, ponto 1).
 *
 * A ETIQUETA JÁ EXISTIA — E NUNCA APARECEU
 * `KanbanCard`, `SearchResultsList` e `FilteredProcessList` tinham, cada
 * um, o seu `{process.under_35 && <Badge>&lt;35 anos</Badge>}`, com as
 * cores escritas à mão em três sítios. **Nenhum ficheiro do backend
 * escreve `under_35`**: o campo está na projecção do Kanban, é lido por
 * três componentes e não é produzido por ninguém. A etiqueta foi
 * construída e nunca foi vista uma única vez — a mesma forma do `doc_id`
 * do Lote 3 e da fila Mongo do Lote 2.
 *
 * Hoje o servidor calcula a elegibilidade ao servir
 * (`services/sub35.py`) e esta é a ÚNICA etiqueta: um componente em vez
 * de três cópias, com tokens semânticos em vez de `bg-green-50`, que no
 * modo escuro fica verde-claro sobre verde-claro.
 *
 * Porque é que diz "Sub35" e não "<35 anos": o rótulo é o nome que a
 * equipa usa para o segmento (e o critério é "menos de 36", até aos 35
 * inclusive — "<35 anos" estava, à letra, errado).
 *
 * LOTE 5 — a regra é ESTRITA: o apoio do Estado exige que TODOS os
 * compradores cumpram o requisito de idade, logo um 2.º titular com mais
 * de 35 anos retira a etiqueta ao processo. Quem decide continua a ser o
 * servidor (`services/sub35.py`); o que muda aqui é só o que a etiqueta
 * PROMETE a quem passa o rato — e prometer "o titular" quando a condição
 * é sobre todos era a diferença entre uma oportunidade e uma isenção de
 * IMT recusada pela AT em cima da escritura.
 */
import { Sparkles } from "lucide-react";

import { Badge } from "../ui/badge";
import { cn } from "../../lib/utils";

/** O texto é único e vive aqui: três cópias é como as três divergiram. */
export const ROTULO_SUB35 = "Sub35";
export const EXPLICACAO_SUB35 =
  "Todos os titulares com 35 anos ou menos — elegível para os apoios à " +
  "habitação jovem";

/**
 * @param {object} props
 * @param {object} [props.processo] — qualquer documento servido pela API
 * @param {boolean} [props.activo] — alternativa a `processo`, já resolvida
 * @param {"sm"|"md"} [props.tamanho]
 * @param {string} [props.className]
 */
export default function Sub35Badge({
  processo,
  activo,
  tamanho = "md",
  className,
}) {
  const mostrar = activo !== undefined ? Boolean(activo) : eSub35(processo);
  if (!mostrar) return null;

  return (
    <Badge
      variant="secondary"
      title={EXPLICACAO_SUB35}
      className={cn(
        "gap-1 font-medium whitespace-nowrap",
        tamanho === "sm" ? "text-[9px] px-1.5 py-0 h-4" : "text-[10px] px-2 py-0 h-5",
        className,
      )}
      data-testid="etiqueta-sub35"
    >
      <Sparkles className={tamanho === "sm" ? "h-2.5 w-2.5" : "h-3 w-3"} />
      {ROTULO_SUB35}
    </Badge>
  );
}

/**
 * O documento vem etiquetado pelo servidor?
 *
 * `is_sub35` é o campo novo; `under_35` é o nome legado que os três
 * ecrãs leem e que o servidor passou a enviar com o mesmo valor. Ler os
 * dois aqui é o que permite que um ecrã ainda não migrado não fique sem
 * etiqueta — e é SÓ aqui que a cascata existe.
 *
 * Nunca se calcula a idade no cliente: a listagem não recebe (nem deve
 * receber) a ficha pessoal inteira, e duas contas da mesma regra em dois
 * sítios é o defeito que o ponto único do backend acabou de fechar.
 */
export function eSub35(processo) {
  if (!processo || typeof processo !== "object") return false;
  return processo.is_sub35 === true || processo.under_35 === true;
}
