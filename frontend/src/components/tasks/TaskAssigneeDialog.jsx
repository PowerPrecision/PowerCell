/**
 * TaskAssigneeDialog — mudar o responsável de uma tarefa.
 *
 * Ponto 10 (Lote 5, Secção B). O backend já aceitava `assigned_to` no
 * `PUT /tasks/{id}`; o que não havia era forma de lá chegar — o diálogo
 * da tarefa mostrava "Atribuído a" como TEXTO. Uma tarefa que caísse na
 * pessoa errada só se resolvia apagando-a e criando outra, o que perde
 * o histórico e o prefixo `[PROC-012]`.
 *
 * APRESENTAÇÃO, NÃO DECISÃO: devolve a lista escolhida (`onConfirm`);
 * quem chama a API e decide o que isso implica é o contentor.
 *
 * A equipa do processo aparece primeiro e o resto atrás de um separador
 * (Lote 4, ponto 13) — e quando a equipa não se confirma, isso é DITO.
 */
import { useEffect, useState } from "react";
import { Button } from "../ui/button";
import { Checkbox } from "../ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { ScrollArea } from "../ui/scroll-area";
import { Loader2, UserCog, AlertCircle } from "lucide-react";
import { agruparResponsaveis } from "../../utils/taskAssignees";

export default function TaskAssigneeDialog({
  open,
  onOpenChange,
  task,
  users = [],
  equipaDoProcesso = [],
  onConfirm,
  saving = false,
}) {
  const [escolhidos, setEscolhidos] = useState([]);

  // Reabrir parte sempre do que está gravado — um rascunho abandonado
  // não pode reaparecer como se tivesse sido aceite.
  useEffect(() => {
    if (open) setEscolhidos((task?.assigned_to || []).map(String));
  }, [open, task]);

  const { daEquipa, foraDaEquipa, temGrupos, equipaPorConfirmar } = agruparResponsaveis({
    users,
    equipaDoProcesso,
    dentroDeProcesso: Boolean(task?.process_id),
  });

  const alternar = (userId) =>
    setEscolhidos((anteriores) =>
      anteriores.includes(String(userId))
        ? anteriores.filter((u) => u !== String(userId))
        : [...anteriores, String(userId)],
    );

  const linha = (utilizador) => {
    const activo = escolhidos.includes(String(utilizador.id));
    return (
      <li key={utilizador.id}>
        <label
          className={`flex items-center gap-3 p-2 rounded cursor-pointer transition-colors ${
            activo ? "bg-accent" : "hover:bg-muted"
          }`}
        >
          <Checkbox
            checked={activo}
            onCheckedChange={() => alternar(utilizador.id)}
            aria-label={utilizador.name}
          />
          <span className="min-w-0">
            <span className="block font-medium text-sm truncate">{utilizador.name}</span>
            <span className="block text-xs text-muted-foreground">{utilizador.role}</span>
          </span>
        </label>
      </li>
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <UserCog className="h-4 w-4" aria-hidden="true" />
            Mudar responsável
          </DialogTitle>
          <DialogDescription>
            {task?.title
              ? `Quem fica com "${task.title}".`
              : "Escolha quem fica responsável por esta tarefa."}
          </DialogDescription>
        </DialogHeader>

        {equipaPorConfirmar && (
          <p
            className="text-xs text-muted-foreground flex items-start gap-1.5"
            data-testid="equipa-por-confirmar"
          >
            <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" aria-hidden="true" />
            Não foi possível confirmar a equipa deste processo — está a ver
            todo o staff.
          </p>
        )}

        <ScrollArea className="max-h-[300px] pr-2">
          {temGrupos && (
            <p className="text-[11px] uppercase tracking-wide text-muted-foreground px-2 py-1">
              Equipa do processo
            </p>
          )}
          <ul className="space-y-0.5">{daEquipa.map(linha)}</ul>

          {temGrupos && (
            <>
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground px-2 py-1 mt-2 border-t pt-2">
                Fora da equipa do processo
              </p>
              <ul className="space-y-0.5">{foraDaEquipa.map(linha)}</ul>
            </>
          )}
        </ScrollArea>

        {escolhidos.length === 0 && (
          <p className="text-xs text-muted-foreground" role="status">
            Sem ninguém escolhido, a tarefa fica sem responsável.
          </p>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange?.(false)}>
            Cancelar
          </Button>
          <Button
            onClick={() => onConfirm?.(escolhidos)}
            disabled={saving}
            className="gap-1.5"
            data-testid="confirmar-responsaveis"
          >
            {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
