/**
 * ManualRenameDialog — renomear um ficheiro à mão (Épico 8, Eixo 2).
 *
 * COMPONENTE DE APRESENTAÇÃO E CONTROLADO: o nome em edição vive no
 * contentor, porque é ele que o envia. A extensão é mantida pelo backend.
 */
import { Loader2, Pencil } from "lucide-react";

import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../../ui/dialog";

/**
 * @param {Object} props
 * @param {boolean} props.open
 * @param {string} [props.fileName] - Nome actual, mostrado na descrição.
 * @param {string} props.newName - Nome em edição (controlado).
 * @param {boolean} [props.renaming] - Envio em curso.
 * @param {(aberto: boolean) => void} props.onOpenChange
 * @param {(nome: string) => void} props.onNameChange
 * @param {() => void} props.onConfirm
 */
export default function ManualRenameDialog({
  open,
  fileName,
  newName = "",
  renaming = false,
  onOpenChange,
  onNameChange,
  onConfirm,
}) {
  return (
  <Dialog open={open} onOpenChange={(aberto) => !aberto && onOpenChange(false)}>
    <DialogContent className="sm:max-w-md">
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          <Pencil className="h-5 w-5 text-blue-600" />
          Renomear Ficheiro
        </DialogTitle>
        <DialogDescription>
          Introduza o novo nome para "{fileName}".
          <br />
          <span className="text-xs text-muted-foreground">
            A extensão será mantida automaticamente.
          </span>
        </DialogDescription>
      </DialogHeader>
      
      <div className="space-y-4 py-4">
        <div className="space-y-2">
          <label className="text-sm font-medium">Novo nome</label>
          <Input
            placeholder="Introduza o novo nome..."
            value={newName}
            onChange={(evento) => onNameChange(evento.target.value)}
            autoFocus
            onKeyDown={(evento) => {
              if (evento.key === "Enter" && newName.trim()) onConfirm();
            }}
          />
        </div>
      </div>

      <DialogFooter className="flex gap-2">
        <Button
          variant="outline"
          onClick={() => onOpenChange(false)}
          disabled={renaming}
        >
          Cancelar
        </Button>
        <Button
          onClick={onConfirm}
          disabled={!newName.trim() || renaming}
          className="bg-blue-600 hover:bg-blue-700"
        >
          {renaming ? (
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
          ) : (
            <Pencil className="h-4 w-4 mr-2" />
          )}
          Renomear
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
  );
}
