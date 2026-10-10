/**
 * ReabrirProcessoDialog — "Reabrir" um processo fechado.
 *
 * Um processo em fase terminal está em modo de leitura para toda a equipa; o
 * consultor que precise de mexer reabre-o primeiro, escolhendo a fase activa
 * para onde volta. Não se adivinha a fase anterior: uma fase errada põe o
 * processo no sítio errado do Kanban.
 *
 * COMPONENTE DE APRESENTAÇÃO: não chama a API; diz ao contentor a fase
 * escolhida (`onConfirmar(fase)`).
 */
import { useEffect, useState } from "react";
import { Loader2, Unlock } from "lucide-react";

import { Button } from "../../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../../ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../ui/select";

/**
 * @param {Object} props
 * @param {boolean} props.open
 * @param {(aberto: boolean) => void} props.onOpenChange
 * @param {Array<{name: string, label: string}>} props.fases - fases activas do motor
 * @param {boolean} [props.aReabrir] - pedido em curso
 * @param {(fase: string) => void} props.onConfirmar
 */
export default function ReabrirProcessoDialog({
  open,
  onOpenChange,
  fases,
  aReabrir = false,
  onConfirmar,
}) {
  const [fase, setFase] = useState("");

  // Cada abertura começa sem fase escolhida: confirmar sem ter escolhido não
  // pode reabrir para a que ficou do diálogo anterior.
  useEffect(() => {
    if (open) setFase("");
  }, [open]);

  const opcoes = Array.isArray(fases) ? fases : [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="reabrir-processo-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Unlock className="h-5 w-5" />
            Reabrir processo
          </DialogTitle>
          <DialogDescription>
            O processo volta a estar activo e pode ser editado. Escolha a fase para onde regressa.
          </DialogDescription>
        </DialogHeader>

        {opcoes.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="reabrir-sem-fases">
            Não há fases activas configuradas. Contacte um administrador.
          </p>
        ) : (
          <Select value={fase} onValueChange={setFase}>
            <SelectTrigger aria-label="Fase de destino" data-testid="reabrir-fase-select">
              <SelectValue placeholder="Escolha a fase" />
            </SelectTrigger>
            <SelectContent>
              {opcoes.map((o) => (
                <SelectItem key={o.name} value={o.name}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={aReabrir}>
            Cancelar
          </Button>
          <Button
            type="button"
            onClick={() => onConfirmar(fase)}
            disabled={!fase || aReabrir}
            data-testid="reabrir-confirmar"
          >
            {aReabrir ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Unlock className="h-4 w-4 mr-2" />}
            Reabrir
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
