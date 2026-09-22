/**
 * AIReviewDialog — resolução de conflitos da análise IA (Épico 8, Eixo 1).
 *
 * Quando a extracção automática devolve, para um campo, um valor diferente
 * do que já está na ficha, o consultor escolhe: fica o existente, fica o
 * extraído, ou escreve outro à mão.
 *
 * COMPONENTE DE APRESENTAÇÃO. Devolve `onResolve(campo, valor)` e deixa o
 * contentor decidir o que isso faz à ficha. O texto por escrever à mão é
 * a única coisa que guarda — é rascunho seu, não estado do contentor.
 *
 * BUG CORRIGIDO NA EXTRACÇÃO: o botão "Aplicar" do campo manual lia o
 * valor com `e.target.parentElement.querySelector("input")`. Basta pôr um
 * ícone dentro do botão para `e.target` passar a ser o `<svg>`,
 * `parentElement` o botão, e o `querySelector` devolver `null` — o clique
 * deixaria de fazer nada, em silêncio. O campo passa a ser controlado.
 */
import { useState } from "react";
import { AlertTriangle, Check, CheckCircle, Sparkles } from "lucide-react";

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
import { Input } from "../../ui/input";

/** "monthly_income" → "Monthly Income" */
const rotuloDoCampo = (campo) =>
  String(campo || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letra) => letra.toUpperCase());

/**
 * @typedef {Object} ConflitoIA
 * @property {string} field - Nome do campo em conflito.
 * @property {any} existing_value - O que está na ficha.
 * @property {any} new_value - O que a IA extraiu.
 * @property {string} [source] - Documento de onde veio o valor extraído.
 */

/**
 * Uma linha de conflito. Vive aqui dentro para que cada campo manual tenha
 * o seu próprio rascunho sem o contentor ter de conhecer nenhum deles.
 *
 * @param {{conflito: ConflitoIA, onResolve: (campo: string, valor: any) => void}} props
 */
function LinhaDeConflito({ conflito, onResolve }) {
  const [valorManual, setValorManual] = useState("");

  const aplicarManual = () => {
    if (!valorManual) return;
    onResolve(conflito.field, valorManual);
    setValorManual("");
  };

  return (
    <div className="border rounded-lg p-4 space-y-3">
      <div className="font-medium text-sm">{rotuloDoCampo(conflito.field)}</div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <button
          type="button"
          className="text-left border rounded p-3 cursor-pointer hover:border-blue-500 hover:bg-blue-50 dark:hover:bg-blue-950"
          onClick={() => onResolve(conflito.field, conflito.existing_value)}
        >
          <div className="text-xs text-muted-foreground mb-1">Valor Existente</div>
          <div className="font-medium">{safeString(conflito.existing_value, "-")}</div>
        </button>

        <button
          type="button"
          className="text-left border rounded p-3 cursor-pointer hover:border-green-500 hover:bg-green-50 dark:hover:bg-green-950"
          onClick={() => onResolve(conflito.field, conflito.new_value)}
        >
          <div className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
            <Sparkles className="h-3 w-3" />
            Valor Extraído (IA)
          </div>
          <div className="font-medium text-green-700 dark:text-green-400">
            {safeString(conflito.new_value, "-")}
          </div>
          {conflito.source && (
            <div className="text-xs text-muted-foreground mt-1">
              Fonte: {safeString(conflito.source)}
            </div>
          )}
        </button>
      </div>

      <div className="flex items-center gap-2">
        <Input
          placeholder="Ou edite manualmente..."
          className="flex-1 text-sm"
          aria-label={`Valor manual para ${rotuloDoCampo(conflito.field)}`}
          value={valorManual}
          onChange={(evento) => setValorManual(evento.target.value)}
          onKeyDown={(evento) => {
            if (evento.key === "Enter") {
              evento.preventDefault();
              aplicarManual();
            }
          }}
        />
        <Button size="sm" variant="outline" onClick={aplicarManual} disabled={!valorManual}>
          Aplicar
        </Button>
      </div>
    </div>
  );
}

/**
 * @param {Object} props
 * @param {boolean} props.open
 * @param {ConflitoIA[]} props.conflicts - Conflitos por resolver.
 * @param {(aberto: boolean) => void} props.onOpenChange
 * @param {(campo: string, valor: any) => void} props.onResolve
 * @param {() => void} props.onConfirmAll - Só quando não sobra nenhum.
 */
export default function AIReviewDialog({
  open,
  conflicts = [],
  onOpenChange,
  onResolve,
  onConfirmAll,
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl w-[calc(100vw-2rem)] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-yellow-500" />
            Revisão de Dados Extraídos
          </DialogTitle>
          <DialogDescription>
            A análise IA detectou valores diferentes para alguns campos. Escolha o valor correcto ou edite manualmente.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {conflicts.map((conflito, idx) => (
            <LinhaDeConflito
              key={conflito.field || idx}
              conflito={conflito}
              onResolve={onResolve}
            />
          ))}

          {conflicts.length === 0 && (
            <div className="text-center py-8 text-muted-foreground">
              <CheckCircle className="h-12 w-12 mx-auto mb-3 text-green-500" />
              <p>Todos os conflitos foram resolvidos!</p>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Fechar
          </Button>
          <Button onClick={onConfirmAll} disabled={conflicts.length > 0}>
            <Check className="h-4 w-4 mr-2" />
            Confirmar Todos
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
