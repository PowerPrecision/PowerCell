/**
 * PedirAlteracaoDeAtribuicao — botão + diálogo com que o Index pede à chefia a alteração da
 * atribuição de um processo (Out 2026). O motivo é opcional.
 *
 * Com um pedido seu ainda pendente, o botão dá lugar a «Pedido enviado» (o servidor também
 * recusa um segundo, 409). Nada aqui muda a atribuição: quem a muda é a chefia, pelo «Gerir».
 */
import { useState } from "react";
import { Clock, Loader2, UserCog } from "lucide-react";

import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog";
import { Label } from "../ui/label";
import { Textarea } from "../ui/textarea";
import { usePedidosDeAtribuicao, usePedirAlteracaoDeAtribuicao } from "../../hooks/usePedidosDeAtribuicao";

const MAX_MOTIVO = 1000;

export function PedirAlteracaoDeAtribuicao({ processId, variant = "outline", size = "default", className = "" }) {
  const [aberto, setAberto] = useState(false);
  const [motivo, setMotivo] = useState("");
  const { pedidos } = usePedidosDeAtribuicao({ processId, enabled: Boolean(processId) });
  const pedir = usePedirAlteracaoDeAtribuicao(processId);

  if (pedidos.length > 0) {
    return (
      <Badge
        variant="secondary"
        className="gap-1 font-normal"
        title="A chefia foi avisada e vai rever a atribuição deste processo"
        data-testid="pedido-atribuicao-pendente"
      >
        <Clock className="h-3.5 w-3.5" aria-hidden="true" />
        Pedido de alteração enviado
      </Badge>
    );
  }

  const fechar = () => {
    if (pedir.isPending) return;
    setAberto(false);
    setMotivo("");
  };
  const enviar = () => pedir.mutate(motivo.trim(), { onSuccess: fechar });

  return (
    <>
      <Button
        variant={variant}
        size={size}
        className={className}
        onClick={() => setAberto(true)}
        data-testid="botao-pedir-alteracao-atribuicao"
      >
        <UserCog className="mr-1.5 h-4 w-4" aria-hidden="true" />
        Pedir alteração de atribuição
      </Button>
      <Dialog open={aberto} onOpenChange={(v) => !v && fechar()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Pedir alteração de atribuição</DialogTitle>
            <DialogDescription>
              A chefia recebe o pedido e trata a atribuição deste processo. Indicar o motivo é opcional.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="motivo-pedido-atribuicao">Motivo (opcional)</Label>
            <Textarea
              id="motivo-pedido-atribuicao"
              value={motivo}
              maxLength={MAX_MOTIVO}
              rows={4}
              placeholder="Ex.: o processo é de outro balcão; já estou com muitos processos…"
              onChange={(e) => setMotivo(e.target.value)}
              data-testid="motivo-pedido-atribuicao"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={fechar} disabled={pedir.isPending}>
              Cancelar
            </Button>
            <Button onClick={enviar} disabled={pedir.isPending} data-testid="enviar-pedido-atribuicao">
              {pedir.isPending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden="true" />}
              Enviar pedido
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export default PedirAlteracaoDeAtribuicao;
