/**
 * ProcessLabelFilter — filtrar processos por etiquetas.
 *
 * Ponto 15 (Lote 5, Secção B). Partilhado pela Lista de Processos e
 * pelo Kanban: são dois ecrãs com construtores de query SEPARADOS no
 * backend (foi assim que o quadro ficou de fora do isolamento no Lote
 * 4), mas do lado do utilizador a pergunta é a mesma e a UI também tem
 * de ser.
 *
 * APRESENTAÇÃO, NÃO DECISÃO: diz o que foi escolhido (`onChange`); quem
 * decide o que isso implica — parâmetro de URL, refetch, cache — é a
 * página.
 */
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Checkbox } from "../ui/checkbox";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "../ui/popover";
import { ScrollArea } from "../ui/scroll-area";
import { Tag, X } from "lucide-react";
import { corDaEtiqueta, normalizarEtiquetas } from "../../utils/processLabels";

export default function ProcessLabelFilter({
  disponiveis = [],
  seleccionadas = [],
  onChange,
  logica = "OR",
  onLogicaChange,
}) {
  const opcoes = normalizarEtiquetas(disponiveis);
  const activas = normalizarEtiquetas(seleccionadas);

  // Sem etiquetas em uso não há nada para filtrar — um dropdown vazio é
  // um convite a um clique que não faz nada.
  if (opcoes.length === 0 && activas.length === 0) return null;

  const alternar = (etiqueta) => {
    const ja = activas.some((e) => e.toLowerCase() === etiqueta.toLowerCase());
    onChange?.(
      ja
        ? activas.filter((e) => e.toLowerCase() !== etiqueta.toLowerCase())
        : [...activas, etiqueta],
    );
  };

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <Popover>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className="h-9 gap-1.5"
            data-testid="filtro-etiquetas"
          >
            <Tag className="h-3.5 w-3.5" aria-hidden="true" />
            Etiquetas
            {activas.length > 0 && (
              <Badge variant="secondary" className="ml-1 px-1.5 py-0 text-[10px]">
                {activas.length}
              </Badge>
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-60 p-2" align="start">
          {activas.length > 1 && (
            <div className="flex items-center justify-between gap-2 pb-2 mb-2 border-b">
              {/* Espelha o `assigned_logic` que já existe nas listagens:
                  segmentar a sério é "Sub 35" E "VIP", não "ou". */}
              <span className="text-xs text-muted-foreground">Corresponder</span>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-xs"
                onClick={() => onLogicaChange?.(logica === "AND" ? "OR" : "AND")}
                data-testid="alternar-logica-etiquetas"
              >
                {logica === "AND" ? "todas" : "qualquer uma"}
              </Button>
            </div>
          )}
          <ScrollArea className="max-h-[240px]">
            <ul className="space-y-0.5">
              {opcoes.map((etiqueta) => {
                const activa = activas.some(
                  (e) => e.toLowerCase() === etiqueta.toLowerCase(),
                );
                return (
                  <li key={etiqueta}>
                    <label className="flex items-center gap-2 rounded-sm px-1.5 py-1.5 hover:bg-accent cursor-pointer">
                      <Checkbox
                        checked={activa}
                        onCheckedChange={() => alternar(etiqueta)}
                        aria-label={etiqueta}
                      />
                      <span className="text-sm truncate">{etiqueta}</span>
                    </label>
                  </li>
                );
              })}
            </ul>
          </ScrollArea>
        </PopoverContent>
      </Popover>

      {activas.map((etiqueta) => (
        <Badge
          key={etiqueta}
          variant="outline"
          className={`text-xs gap-1 pr-1 ${corDaEtiqueta(etiqueta)}`}
        >
          {etiqueta}
          <button
            type="button"
            onClick={() => alternar(etiqueta)}
            aria-label={`Remover filtro ${etiqueta}`}
            className="rounded-sm hover:bg-background/50 p-0.5"
          >
            <X className="h-3 w-3" aria-hidden="true" />
          </button>
        </Badge>
      ))}

      {activas.length > 0 && (
        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-xs text-muted-foreground"
          onClick={() => onChange?.([])}
        >
          Limpar
        </Button>
      )}
    </div>
  );
}
