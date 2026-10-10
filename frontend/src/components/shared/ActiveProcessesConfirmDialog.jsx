/**
 * ActiveProcessesConfirmDialog — «este cliente já tem processos activos»
 * (Bloco 1, ponto 5).
 *
 * COMPONENTE DE APRESENTAÇÃO: lista o que o servidor devolveu e devolve a
 * resposta. A decisão — e o que fazer a seguir — é do contentor.
 *
 * Consultivo: um cliente pode ter dois processos legitimamente. O botão
 * principal é «Continuar», e cada processo é uma ligação para o abrir (em
 * separador novo, para o utilizador não perder o que estava a fazer).
 */
import { AlertTriangle } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../ui/alert-dialog";
import { frase, processosOcultos, rotuloDoTitular } from "../../utils/processosActivos";

/**
 * @param {Object} props
 * @param {boolean} props.open
 * @param {string} [props.nome] - Nome do cliente (cai para o devolvido pelo servidor).
 * @param {{total:number, processos:Array, client_name:string}|null} props.resposta
 * @param {() => void} props.onConfirm - «Continuar mesmo assim».
 * @param {() => void} props.onCancel
 */
export default function ActiveProcessesConfirmDialog({ open, nome, resposta, onConfirm, onCancel }) {
  const processos = resposta?.processos ?? [];
  const oculto = processosOcultos(resposta);
  const quem = nome || resposta?.client_name || "Este cliente";

  return (
    <AlertDialog open={open} onOpenChange={(aberto) => { if (!aberto) onCancel(); }}>
      <AlertDialogContent data-testid="active-processes-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-500" aria-hidden="true" />
            Este cliente já tem {frase(resposta)}
          </AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-3">
              <p>
                {quem} já está associado a processos que ainda não terminaram. Quer
                continuar mesmo assim?
              </p>
              <ul className="divide-y rounded-md border text-sm" data-testid="active-processes-list">
                {processos.map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-3 px-3 py-2">
                    <div className="min-w-0">
                      <a
                        href={`/processo/${p.id}`}
                        target="_blank"
                        rel="noreferrer"
                        className="font-medium text-primary hover:underline"
                      >
                        {p.process_number != null ? `Processo #${p.process_number}` : "Processo"}
                      </a>
                      <p className="text-xs text-muted-foreground truncate">
                        {p.status_label}
                        {p.consultor_names.length > 0 ? ` · ${p.consultor_names.join(", ")}` : ""}
                      </p>
                    </div>
                    <span className="shrink-0 text-xs text-muted-foreground">{rotuloDoTitular(p.titular)}</span>
                  </li>
                ))}
              </ul>
              {oculto > 0 && (
                <p className="text-xs text-muted-foreground">e mais {oculto}.</p>
              )}
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onCancel}>Cancelar</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>Continuar mesmo assim</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
