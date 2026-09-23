/**
 * RGPDRequestDialog — pedido de consentimento RGPD (Épico 8, Eixo 1).
 *
 * Envia ao cliente o pedido de assinatura do consentimento, com uma
 * mensagem opcional do consultor.
 *
 * COMPONENTE DE APRESENTAÇÃO: controlado de ponta a ponta. O texto da
 * mensagem vive no contentor porque é ele que o envia — o diálogo só o
 * mostra e avisa quando muda.
 */
import { Loader2 } from "lucide-react";

import { safeString } from "../../../utils/safeString";
import { Button } from "../../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../../ui/dialog";
import { Textarea } from "../../ui/textarea";

/**
 * @param {Object} props
 * @param {boolean} props.open
 * @param {(aberto: boolean) => void} props.onOpenChange
 * @param {string} props.clientName - Nome do titular, para o texto.
 * @param {string} props.clientEmail - Destino do pedido.
 * @param {string} props.message - Mensagem personalizada (controlada).
 * @param {(texto: string) => void} props.onMessageChange
 * @param {() => void} props.onConfirm
 * @param {boolean} [props.sending] - Envio em curso.
 */
export default function RGPDRequestDialog({
  open,
  onOpenChange,
  clientName,
  clientEmail,
  message,
  onMessageChange,
  onConfirm,
  sending = false,
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Solicitar Consentimento RGPD</DialogTitle>
          <DialogDescription>
            Envie um pedido de consentimento RGPD para{" "}
            <strong>{safeString(clientName)}</strong> ({safeString(clientEmail)}).
          </DialogDescription>
        </DialogHeader>

        <div className="py-4">
          <label
            htmlFor="rgpd-mensagem"
            className="text-sm font-medium text-foreground mb-2 block"
          >
            Mensagem personalizada{" "}
            <span className="text-muted-foreground font-normal">(opcional)</span>
          </label>
          <Textarea
            id="rgpd-mensagem"
            placeholder="Adicione uma mensagem personalizada para o cliente..."
            value={message}
            onChange={(evento) => onMessageChange(evento.target.value)}
            rows={3}
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button onClick={onConfirm} disabled={sending}>
            {sending ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
            Solicitar RGPD
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
