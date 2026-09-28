/**
 * PACOTE DU — Observações como feed de notas.
 * Lista notas antigas e um campo para acrescentar novas.
 *
 * PONTO 9: É AQUI QUE AS NOTAS SE ESCREVEM
 * ========================================
 * Este cartão passou a ser o local OFICIAL e único das notas do
 * consultor. O separador Histórico deixou de as aceitar (é uma trilha de
 * auditoria automática) e a coluna "Notas do Consultor" da Listagem de
 * Processos espelha o que aqui está — é a MESMA função que resolve as
 * duas (`resolveProcessObservationNotes`), para não poderem divergir.
 *
 * O botão de nota de voz mudou-se para cá pela mesma razão: uma nota
 * ditada é uma nota. Componente de APRESENTAÇÃO — pede a abertura do
 * gravador (`onAbrirNotaDeVoz`) e é o contentor que decide; o diálogo
 * vive ao nível da página, para o utilizador não o perder ao mudar de
 * separador.
 */
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Button } from "../ui/button";
import { Textarea } from "../ui/textarea";
import { Label } from "../ui/label";
import { ScrollArea } from "../ui/scroll-area";
import { EmptyState } from "../ui/EmptyState";
import { Badge } from "../ui/badge";
import { Loader2, StickyNote, Plus, Mic } from "lucide-react";
import { formatDateTime } from "../../lib/utils";
import { resolveProcessObservationNotes } from "../../utils/processObservationNotes";

/**
 * De onde veio cada nota. O feed é o caso normal e não leva crachá —
 * marcar tudo seria ruído; marcam-se as origens que surpreendem.
 */
const ORIGENS = {
  legacy: "Quadro",
  ai: "IA",
};

export default function ProcessObservationsCard({
  process,
  onAdd,
  disabled = false,
  saving = false,
  onAbrirNotaDeVoz,
}) {
  const notes = resolveProcessObservationNotes(process);
  const [draft, setDraft] = useState("");

  const persist = async () => {
    const text = draft.trim();
    if (disabled || saving || !text) return;
    try {
      await onAdd?.(text);
      setDraft("");
    } catch {
      // toast de erro vem do pai
    }
  };

  return (
    <Card className="border-border h-auto" data-testid="process-observations-card">
      <CardHeader className="pb-2 py-3 flex flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle className="text-sm flex items-center gap-2">
          <StickyNote className="h-4 w-4 text-muted-foreground" />
          Observações
        </CardTitle>
        {/* Sem callback não há botão: um botão que não faz nada é pior
            do que botão nenhum (mesma regra que valia no Histórico). */}
        {!disabled && onAbrirNotaDeVoz && (
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5"
            onClick={() => onAbrirNotaDeVoz()}
            data-testid="voice-note-open"
          >
            <Mic className="h-3.5 w-3.5" />
            Nota de voz
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {notes.length === 0 ? (
          <EmptyState
            icon={StickyNote}
            message="Ainda não há notas neste processo"
            className="py-6"
          />
        ) : (
          <ScrollArea className="h-[180px] pr-2">
            <ul className="space-y-2" data-testid="process-observations-feed">
              {notes.map((note) => (
                <li
                  key={note.id || `${note.created_at}-${note.text}`}
                  className="rounded-md border border-border bg-muted/30 p-2.5"
                >
                  <p className="text-sm whitespace-pre-wrap">{note.text}</p>
                  <p className="text-[11px] text-muted-foreground mt-1 flex items-center gap-1.5 flex-wrap">
                    {/* Ponto 14: as notas vêm de três sítios e o leitor
                        precisa de saber qual. Uma nota lida pela IA não
                        tem o mesmo peso que uma escrita pelo consultor. */}
                    {ORIGENS[note.origin] && (
                      <Badge variant="outline" className="text-[10px] px-1 py-0 font-normal">
                        {ORIGENS[note.origin]}
                      </Badge>
                    )}
                    <span>
                      {note.user_name ? `${note.user_name} · ` : ""}
                      {note.created_at ? formatDateTime(note.created_at) : ""}
                    </span>
                  </p>
                </li>
              ))}
            </ul>
          </ScrollArea>
        )}

        <div className="space-y-2">
          <Label htmlFor="process-observations" className="sr-only">
            Nova observação
          </Label>
          <Textarea
            id="process-observations"
            data-testid="process-observations-input"
            placeholder="Escrever uma nova nota…"
            value={draft}
            disabled={disabled || saving}
            onChange={(e) => setDraft(e.target.value)}
            rows={2}
            className="min-h-[64px] h-auto text-sm resize-y"
          />
          <div className="flex justify-end">
            <Button
              size="sm"
              onClick={persist}
              disabled={disabled || saving || !draft.trim()}
              data-testid="process-observations-save"
              className="gap-1.5"
            >
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
              Adicionar
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
