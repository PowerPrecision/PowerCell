/**
 * ReabrirProcesso — botão + diálogo para reabrir um processo JÁ indexado (Nov 2026).
 *
 * O caso: indexado hoje, daqui a dois meses o banco pede os recibos e os extratos desses meses. Quem
 * trabalha como Index reabre-o para si (fica atribuído e «Em tratamento»); a gestão devolve-o à fila.
 * A fase do processo não muda. O motivo é opcional e fica no registo de auditoria.
 * Só aparece num processo indexado por uma pessoa (um dispensado nunca passou pelo Index).
 */
import { useState } from "react";
import { Loader2, RotateCcw } from "lucide-react";

import { Button } from "../ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog";
import { Label } from "../ui/label";
import { Textarea } from "../ui/textarea";

const MAX_MOTIVO = 500;

export function podeReabrir(processo) {
  return processo?.index_status === "indexed" && processo?.index_skipped !== true;
}

export function ReabrirProcesso({ processo, daEquipa, reabrir }) {
  const [aberto, setAberto] = useState(false);
  const [motivo, setMotivo] = useState("");
  if (!podeReabrir(processo)) return null;

  const fechar = () => {
    if (reabrir.isPending) return;
    setAberto(false);
    setMotivo("");
  };
  const enviar = () => reabrir.mutate(motivo.trim(), { onSuccess: fechar });

  return (
    <>
      <Button variant="outline" onClick={() => setAberto(true)} data-testid="botao-reabrir-processo">
        <RotateCcw className="mr-1.5 h-4 w-4" aria-hidden="true" />
        Reabrir
      </Button>
      <Dialog open={aberto} onOpenChange={(v) => !v && fechar()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reabrir este processo?</DialogTitle>
            <DialogDescription>
              {daEquipa
                ? "O processo volta a estar atribuído a si, em tratamento, para analisar os documentos novos. Conta para o seu limite de processos activos."
                : "O processo volta à fila do Index e é atribuído automaticamente a um indexador."}{" "}
              A fase do processo não muda. Quando terminar, marque-o outra vez como indexado.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="motivo-reabrir">Motivo (opcional)</Label>
            <Textarea
              id="motivo-reabrir"
              value={motivo}
              maxLength={MAX_MOTIVO}
              rows={3}
              placeholder="Ex.: o banco pediu os recibos e extratos de setembro e outubro"
              onChange={(e) => setMotivo(e.target.value)}
              data-testid="motivo-reabrir"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={fechar} disabled={reabrir.isPending}>
              Cancelar
            </Button>
            <Button onClick={enviar} disabled={reabrir.isPending} data-testid="confirmar-reabrir">
              {reabrir.isPending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden="true" />}
              Reabrir
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export default ReabrirProcesso;
