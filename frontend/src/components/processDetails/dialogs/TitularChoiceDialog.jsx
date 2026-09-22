/**
 * TitularChoiceDialog — "Este documento é de quem?" (Épico 8, Eixo 1).
 *
 * Quando a análise IA de um documento não consegue associar os dados de
 * identidade a um dos titulares com confiança (`needs_titular_choice` em
 * `document_titular_match`), o consultor decide: Titular 1, Titular 2 ou
 * ignorar o documento.
 *
 * COMPONENTE DE APRESENTAÇÃO. Não sabe o que é um processo, não chama a
 * API e — sobretudo — não guarda a escolha: diz ao contentor qual foi
 * (`onChoose(indice, escolha)`) e ele decide o que isso implica. No
 * monolito, cada botão fazia um `setTitularChoiceDialog(prev => ...)` com
 * a reconstrução do array aqui dentro; era estado do contentor a ser
 * manipulado a partir da UI (§ 20 do FRONTEND_GUIDELINES).
 */
import { Check, Users } from "lucide-react";

import { Button } from "../../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../../ui/dialog";

/** Escolhas possíveis para cada documento ambíguo. */
export const ESCOLHAS = {
  TITULAR_1: "titular1",
  TITULAR_2: "titular2",
  IGNORAR: "ignore",
};

/**
 * @typedef {Object} DocumentoAmbiguo
 * @property {string} [key] - Chave estável; o índice serve de recurso.
 * @property {string} file_name - Nome do ficheiro analisado.
 * @property {string} [choice] - Escolha actual (ver `ESCOLHAS`).
 * @property {string} [titular1_name] - Nome do 1.º titular, se conhecido.
 * @property {string} [titular2_name] - Nome do 2.º titular, se conhecido.
 */

/**
 * @param {Object} props
 * @param {boolean} props.open
 * @param {DocumentoAmbiguo[]} props.items - Documentos por decidir.
 * @param {(aberto: boolean) => void} props.onOpenChange
 * @param {(indice: number, escolha: string) => void} props.onChoose
 * @param {() => void} props.onConfirm - Aplica todas as escolhas.
 */
export default function TitularChoiceDialog({
  open,
  items = [],
  onOpenChange,
  onChoose,
  onConfirm,
}) {
  // Aplicar com um documento por decidir aplicaria dados ao titular errado.
  const faltaDecidir = items.some((item) => !item.choice);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg w-[calc(100vw-2rem)] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Users className="h-5 w-5 text-purple-600" />
            Este documento é de quem?
          </DialogTitle>
          <DialogDescription>
            A IA não conseguiu associar com confiança. Escolha o titular para aplicar os dados de identidade
            (o 2º titular já está definido no processo).
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {items.map((item, idx) => (
            <div key={item.key || idx} className="border rounded-lg p-3 space-y-2">
              <div className="text-sm font-medium truncate">{item.file_name}</div>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant={item.choice === ESCOLHAS.TITULAR_1 ? "default" : "outline"}
                  onClick={() => onChoose(idx, ESCOLHAS.TITULAR_1)}
                >
                  Titular 1{item.titular1_name ? `: ${item.titular1_name}` : ""}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={item.choice === ESCOLHAS.TITULAR_2 ? "default" : "outline"}
                  onClick={() => onChoose(idx, ESCOLHAS.TITULAR_2)}
                >
                  Titular 2{item.titular2_name ? `: ${item.titular2_name}` : ""}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={item.choice === ESCOLHAS.IGNORAR ? "secondary" : "ghost"}
                  onClick={() => onChoose(idx, ESCOLHAS.IGNORAR)}
                >
                  Ignorar
                </Button>
              </div>
            </div>
          ))}
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button onClick={onConfirm} disabled={faltaDecidir}>
            <Check className="h-4 w-4 mr-2" />
            Aplicar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
