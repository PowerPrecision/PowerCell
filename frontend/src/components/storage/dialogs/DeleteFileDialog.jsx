/**
 * DeleteFileDialog — confirmação de eliminação de um ficheiro
 * (Épico 8, Eixo 2).
 *
 * COMPONENTE DE APRESENTAÇÃO: pergunta e devolve a resposta. Quem elimina
 * — e quem sabe que ficheiro é — é o contentor.
 */
import { Loader2, Trash2 } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../../ui/alert-dialog";

/**
 * @param {Object} props
 * @param {boolean} props.open
 * @param {string} [props.fileName] - Nome mostrado na pergunta.
 * @param {boolean} [props.deleting] - Eliminação em curso.
 * @param {(aberto: boolean) => void} props.onOpenChange
 * @param {() => void} props.onConfirm
 */
export default function DeleteFileDialog({
  open,
  fileName,
  deleting = false,
  onOpenChange,
  onConfirm,
}) {
  return (
  <AlertDialog open={open} onOpenChange={onOpenChange}>
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>Eliminar ficheiro?</AlertDialogTitle>
        <AlertDialogDescription>
          Tem a certeza que deseja eliminar "{fileName}"?
          Esta ação não pode ser revertida.
        </AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel disabled={deleting}>Cancelar</AlertDialogCancel>
        <AlertDialogAction
          onClick={onConfirm}
          disabled={deleting}
          className="bg-red-500 hover:bg-red-600"
        >
          {deleting ? (
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
          ) : (
            <Trash2 className="h-4 w-4 mr-2" />
          )}
          Eliminar
        </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
  );
}
