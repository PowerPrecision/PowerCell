import { Hourglass } from "lucide-react";
import { textoEmIndexacao } from "../../utils/desvioInteligente";

/**
 * «N ficheiros aguardam a Indexação» — para quem NÃO vê a pasta `Index`.
 *
 * Apresentação pura: recebe o número, não decide quem o vê (o servidor só o
 * devolve a quem a pasta está escondida). Sem ficheiros em espera não se
 * desenha nada — uma moldura vazia diria que algo falta.
 */
export default function AvisoEmIndexacao({ total }) {
  const texto = textoEmIndexacao(total);
  if (!texto) return null;
  return (
    <div
      role="status"
      data-testid="aviso-em-indexacao"
      className="flex items-start gap-2 border-b bg-muted/40 px-4 py-2 text-sm text-muted-foreground"
    >
      <Hourglass className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <span>{texto}</span>
    </div>
  );
}
