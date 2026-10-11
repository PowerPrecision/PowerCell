/**
 * «Partilhar com…» — enviar o processo para uma REDE DE DESTINO escolhida.
 *
 * Multi-fornecedor: não há um Hub único. A Empresa A escolhe a quem pede o
 * serviço (outra empresa de crédito, a equipa de Index de outra rede…). Se o
 * destino tem Index, o processo entra na fila dessa rede; com «Via Verde» salta
 * o Index e fica logo à guarda da consultoria (ex.: só crédito, sem análise
 * documental).
 *
 * O servidor decide tudo (papel, casa dona, destino válido); o diálogo mostra a
 * lista que ele devolve e o efeito previsto. A mensagem de erro é a dele.
 */
import { useEffect, useState } from "react";
import { Loader2, Share2 } from "lucide-react";
import { toast } from "sonner";

import { getProcessShareTargets, shareProcessWithNetwork } from "../../services/api";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import { efeitoDaPartilha, nomeDoDestino } from "../../utils/partilhaProcesso";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Label } from "../ui/label";
import { Switch } from "../ui/switch";

/**
 * @param {Object} props
 * @param {string} props.processId
 * @param {boolean} props.open
 * @param {(aberto: boolean) => void} props.onOpenChange
 * @param {(parceiros: Array) => void} [props.onShared] - `partner_companies` actualizado.
 */
export default function PartilharComRedeDialog({ processId, open, onOpenChange, onShared }) {
  const [destinos, setDestinos] = useState(null); // null = a carregar
  const [erro, setErro] = useState("");
  const [escolhido, setEscolhido] = useState("");
  const [viaVerde, setViaVerde] = useState(false);
  const [aEnviar, setAEnviar] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    let cancelado = false;
    setDestinos(null);
    setErro("");
    setEscolhido("");
    getProcessShareTargets(processId)
      .then((res) => {
        if (cancelado) return;
        setDestinos(Array.isArray(res?.data?.destinos) ? res.data.destinos : []);
        setViaVerde(res?.data?.via_verde === true);
      })
      .catch((e) => {
        if (cancelado) return;
        setDestinos([]);
        setErro(extractErrorMessage(e?.response?.data?.detail, "Não foi possível carregar as redes de destino."));
      });
    return () => { cancelado = true; };
  }, [open, processId]);

  const destino = (destinos || []).find((d) => d.network_id === escolhido) || null;

  const enviar = async () => {
    if (!destino) return;
    setAEnviar(true);
    try {
      const res = await shareProcessWithNetwork(processId, { networkId: destino.network_id, viaVerde });
      toast.success(
        res?.data?.ja_partilhado
          ? "Este processo já estava partilhado com essa rede"
          : `Processo enviado para ${nomeDoDestino(destino)}`,
      );
      if (onShared) onShared(res?.data?.parceiros ?? []);
      onOpenChange(false);
    } catch (e) {
      setErro(extractErrorMessage(e?.response?.data?.detail, "Não foi possível partilhar o processo."));
    } finally {
      setAEnviar(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(aberto) => { if (!aEnviar) onOpenChange(aberto); }}>
      <DialogContent data-testid="dialogo-partilhar-com-rede">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Share2 className="h-4 w-4" aria-hidden="true" /> Partilhar com…
          </DialogTitle>
          <DialogDescription>
            A rede escolhida passa a ver este processo. O processo continua a ser seu.
          </DialogDescription>
        </DialogHeader>

        {destinos === null ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> A carregar redes…
          </div>
        ) : (
          <div className="space-y-4">
            {destinos.length === 0 ? (
              <p className="text-sm text-muted-foreground" data-testid="sem-destinos">
                Não há outras redes para onde enviar este processo.
              </p>
            ) : (
              <fieldset className="space-y-2">
                <legend className="text-sm font-medium">Rede de destino</legend>
                {destinos.map((d) => (
                  <label
                    key={d.network_id}
                    className="flex cursor-pointer items-start gap-2 rounded-md border p-2 text-sm has-[:checked]:border-primary"
                  >
                    <input
                      type="radio"
                      name="rede-de-destino"
                      value={d.network_id}
                      checked={escolhido === d.network_id}
                      onChange={() => setEscolhido(d.network_id)}
                      className="mt-1"
                    />
                    <span className="min-w-0">
                      <span className="block font-medium">{nomeDoDestino(d)}</span>
                      <span className="block text-xs text-muted-foreground">
                        {d.ja_partilhado ? "Já partilhado" : d.tem_index ? "Tem equipa de Index" : "Sem equipa de Index"}
                      </span>
                    </span>
                  </label>
                ))}
              </fieldset>
            )}

            <div className="flex items-start gap-3 rounded-md border border-border bg-muted/30 p-3">
              <Switch id="partilha-via-verde" checked={viaVerde} onCheckedChange={setViaVerde} />
              <div className="space-y-0.5">
                <Label htmlFor="partilha-via-verde" className="cursor-pointer text-sm">
                  Via Verde (saltar o Index)
                </Label>
                <p className="text-xs text-muted-foreground">
                  Para processos que não precisam de análise documental (ex.: só intermediação de crédito).
                </p>
              </div>
            </div>

            {destino && (
              <p className="text-sm" data-testid="efeito-da-partilha">
                {efeitoDaPartilha(destino, viaVerde)}
              </p>
            )}
            {erro && (
              <p role="alert" className="text-sm text-destructive" data-testid="erro-da-partilha">
                {erro}
              </p>
            )}
          </div>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" disabled={aEnviar} onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button
            type="button"
            data-testid="partilhar-confirmar"
            disabled={!destino || aEnviar || destino.ja_partilhado}
            onClick={enviar}
          >
            {aEnviar ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : "Partilhar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
