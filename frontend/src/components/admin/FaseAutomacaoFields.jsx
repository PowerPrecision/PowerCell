import { Plus, Trash2, Workflow } from "lucide-react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Switch } from "../ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import {
  DESCRICAO_DA_OMISSAO,
  MAXIMO_DE_DIAS,
  MAXIMO_DE_MODELOS_POR_FASE,
  MAXIMO_DO_TITULO,
  PAPEIS_ATRIBUIVEIS,
  PRIORIDADES,
  RESPONSAVEIS,
  modeloVazio,
} from "../../utils/faseAutomacao";

/**
 * O que o sistema faz quando um processo ENTRA nesta fase (Admin/CEO).
 *
 * Apresentação pura: recebe o estado e diz o que mudou. Cada secção tem um
 * interruptor «Personalizar»: desligado = herda o por-omissão (`null`),
 * ligado = o que estiver na lista, mesmo que vazia («não fazer nada»).
 *
 * @param {object} props
 * @param {string} props.prefix Prefixo dos ids (um editor tem criar e editar).
 * @param {{papeis: (string[]|null), modelos: (object[]|null)}} props.value
 * @param {(proximo: object) => void} props.onChange
 */
export default function FaseAutomacaoFields({ prefix, value, onChange }) {
  const papeis = Array.isArray(value?.papeis) ? value.papeis : null;
  const modelos = Array.isArray(value?.modelos) ? value.modelos : null;

  const alternarPapel = (papel, ligado) => {
    const atuais = papeis || [];
    onChange({
      ...value,
      papeis: ligado ? [...new Set([...atuais, papel])] : atuais.filter((p) => p !== papel),
    });
  };

  const mudarModelo = (indice, campo, valor) =>
    onChange({
      ...value,
      modelos: modelos.map((m, i) => (i === indice ? { ...m, [campo]: valor } : m)),
    });

  return (
    <div
      className="space-y-4 rounded-lg border border-border bg-muted/30 p-4"
      data-testid={`${prefix}-fase-automacao`}
    >
      <div className="flex items-center gap-2">
        <Workflow className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        <h4 className="text-sm font-semibold">Ao entrar nesta fase</h4>
      </div>
      <p className="text-xs text-muted-foreground">{DESCRICAO_DA_OMISSAO}</p>

      {/* ── Atribuição ── */}
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-3">
          <Label htmlFor={`${prefix}-personalizar-papeis`} className="text-sm font-medium">
            Atribuição automática
          </Label>
          <Switch
            id={`${prefix}-personalizar-papeis`}
            checked={papeis !== null}
            onCheckedChange={(ligado) => onChange({ ...value, papeis: ligado ? [] : null })}
            aria-label="Personalizar a atribuição automática"
          />
        </div>
        {papeis === null ? (
          <p className="text-xs text-muted-foreground">A herdar o comportamento por omissão.</p>
        ) : (
          <div className="space-y-1.5 pl-1">
            <p className="text-xs text-muted-foreground">
              Atribui o de menor carga, só se o papel estiver vazio. Nenhum marcado = não atribui.
            </p>
            {PAPEIS_ATRIBUIVEIS.map((p) => (
              <label key={p.value} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={papeis.includes(p.value)}
                  onChange={(e) => alternarPapel(p.value, e.target.checked)}
                />
                {p.label}
              </label>
            ))}
          </div>
        )}
      </div>

      {/* ── Tarefas ── */}
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-3">
          <Label htmlFor={`${prefix}-personalizar-tarefas`} className="text-sm font-medium">
            Tarefas automáticas
          </Label>
          <Switch
            id={`${prefix}-personalizar-tarefas`}
            checked={modelos !== null}
            onCheckedChange={(ligado) => onChange({ ...value, modelos: ligado ? [] : null })}
            aria-label="Personalizar as tarefas automáticas"
          />
        </div>
        {modelos === null ? (
          <p className="text-xs text-muted-foreground">A herdar o comportamento por omissão.</p>
        ) : (
          <div className="space-y-3">
            {modelos.length === 0 && (
              <p className="text-xs text-muted-foreground">Sem tarefas: esta fase não cria nenhuma.</p>
            )}
            {modelos.map((m, i) => (
              <div
                key={m.id || `novo-${i}`}
                className="space-y-2 rounded-md border border-border bg-background p-3"
                data-testid={`${prefix}-tarefa-${i}`}
              >
                <div className="flex items-start gap-2">
                  <div className="flex-1 space-y-1">
                    <Label htmlFor={`${prefix}-tarefa-${i}-titulo`} className="text-xs">
                      Título da tarefa {i + 1}
                    </Label>
                    <Input
                      id={`${prefix}-tarefa-${i}-titulo`}
                      value={m.title}
                      maxLength={MAXIMO_DO_TITULO}
                      onChange={(e) => mudarModelo(i, "title", e.target.value)}
                      placeholder="Ex.: Pedir os últimos 3 recibos de vencimento"
                    />
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={`Remover a tarefa ${i + 1}`}
                    onClick={() => onChange({ ...value, modelos: modelos.filter((_, j) => j !== i) })}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                  <div className="space-y-1">
                    <Label className="text-xs">Prioridade</Label>
                    <Select value={m.priority} onValueChange={(v) => mudarModelo(i, "priority", v)}>
                      <SelectTrigger aria-label={`Prioridade da tarefa ${i + 1}`}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {PRIORIDADES.map((p) => (
                          <SelectItem key={p} value={p}>{p}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor={`${prefix}-tarefa-${i}-prazo`} className="text-xs">
                      Prazo (dias)
                    </Label>
                    <Input
                      id={`${prefix}-tarefa-${i}-prazo`}
                      inputMode="numeric"
                      value={m.due_in_days}
                      onChange={(e) => mudarModelo(i, "due_in_days", e.target.value.replace(/[^\d]/g, ""))}
                      placeholder={`0–${MAXIMO_DE_DIAS}`}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Para quem</Label>
                    <Select value={m.assigned_role} onValueChange={(v) => mudarModelo(i, "assigned_role", v)}>
                      <SelectTrigger aria-label={`Responsável da tarefa ${i + 1}`}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {RESPONSAVEIS.map((r) => (
                          <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={modelos.length >= MAXIMO_DE_MODELOS_POR_FASE}
              onClick={() => onChange({ ...value, modelos: [...modelos, modeloVazio()] })}
            >
              <Plus className="mr-1 h-4 w-4" /> Adicionar tarefa
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
