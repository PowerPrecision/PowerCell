/**
 * BulkDeleteDialog — confirmação de eliminação em massa (Épico 8, Eixo 2).
 *
 * COMPONENTE DE APRESENTAÇÃO. O `preventDefault` no confirmar é
 * deliberado: sem ele o `AlertDialogAction` do Radix fecha o diálogo antes
 * de a eliminação terminar, e o utilizador perde o indicador de progresso.
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
 * @param {number} props.count - Quantos ficheiros vão ser eliminados.
 * @param {boolean} [props.deleting] - Eliminação em curso; tranca o fecho.
 * @param {(aberto: boolean) => void} props.onOpenChange
 * @param {() => void} props.onConfirm
 */
export default function BulkDeleteDialog({
  open,
  count = 0,
  deleting = false,
  onOpenChange,
  onConfirm,
}) {
  return (
          <AlertDialog open={open} onOpenChange={(aberto) => !deleting && onOpenChange(aberto)}>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Eliminar {count} ficheiro(s)</AlertDialogTitle>
                <AlertDialogDescription>
                  Tem a certeza que pretende eliminar {count} ficheiro(s) selecionado(s)? 
                  Esta ação não pode ser revertida. Os ficheiros serão removidos permanentemente do armazenamento.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel disabled={deleting}>Cancelar</AlertDialogCancel>
                <AlertDialogAction
                  onClick={(evento) => {
                    evento.preventDefault();
                    onConfirm();
                  }}
                  disabled={deleting}
                  className="bg-red-600 text-white hover:bg-red-700 focus-visible:ring-red-300"
                >
                  {deleting ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin mr-1" />
                      A eliminar...
                    </>
                  ) : (
                    <>
                      <Trash2 className="h-4 w-4 mr-1" />
                      Eliminar {count} ficheiro(s)
                    </>
                  )}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
  );
}
