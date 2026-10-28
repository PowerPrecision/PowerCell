/**
 * PedidosDeAtribuicaoCard — os pedidos de alteração de atribuição do Index, para a chefia (Out 2026).
 *
 * Vive na «Supervisão do Index» e só aparece quando há pedidos pendentes (divulgação progressiva).
 * A chefia abre o processo, muda a atribuição pelo «Gerir» e fecha aqui o pedido («Tratado» ou
 * «Recusar»); o indexador é avisado. O servidor só devolve os pedidos da rede de quem pergunta.
 */
import { Link } from "react-router-dom";
import { Check, ExternalLink, UserCog, X } from "lucide-react";
import { pt } from "date-fns/locale";

import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { safeFormat } from "../../lib/utils";
import { usePedidosDeAtribuicao, useResolverPedidoDeAtribuicao } from "../../hooks/usePedidosDeAtribuicao";

export function PedidosDeAtribuicaoCard() {
  const { pedidos } = usePedidosDeAtribuicao();
  const resolver = useResolverPedidoDeAtribuicao();

  if (pedidos.length === 0) return null;

  const emCurso = (id) => resolver.isPending && resolver.variables?.pedidoId === id;

  return (
    <Card data-testid="pedidos-de-atribuicao">
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          <UserCog className="h-4 w-4 text-primary" aria-hidden="true" />
          Pedidos de alteração de atribuição
          <Badge variant="secondary" className="font-normal">{pedidos.length}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <ul className="divide-y divide-border">
          {pedidos.map((p) => (
            <li key={p.id} className="py-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between" data-testid="pedido-de-atribuicao">
              <div className="min-w-0 space-y-1">
                <Link
                  to={`/processo/${p.process_id}`}
                  className="font-medium underline-offset-4 hover:underline hover:text-primary"
                >
                  {p.process_number ? `#${p.process_number}` : "Processo"}
                  {p.client_name ? ` · ${p.client_name}` : ""}
                  <ExternalLink className="ml-1 inline h-3.5 w-3.5 align-baseline opacity-60" aria-hidden="true" />
                </Link>
                <p className="text-xs text-muted-foreground">
                  Pedido por {p.requested_by_name || "um indexador"} em {safeFormat(p.created_at, "dd/MM/yyyy HH:mm", { locale: pt })}
                  {p.indexacao_name ? ` · Indexação actual: ${p.indexacao_name}` : ""}
                </p>
                <p className="text-sm whitespace-pre-line break-words">
                  {p.motivo || <span className="italic text-muted-foreground">Sem motivo indicado</span>}
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={emCurso(p.id)}
                  onClick={() => resolver.mutate({ pedidoId: p.id, decisao: "recusado" })}
                >
                  <X className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                  Recusar
                </Button>
                <Button
                  size="sm"
                  disabled={emCurso(p.id)}
                  title="Use primeiro «Gerir» no processo para mudar a atribuição"
                  onClick={() => resolver.mutate({ pedidoId: p.id, decisao: "concluido" })}
                >
                  <Check className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                  Tratado
                </Button>
              </div>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

export default PedidosDeAtribuicaoCard;
