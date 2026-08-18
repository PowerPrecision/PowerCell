/**
 * PACOTE DO.1 — Observações no Resumo do Processo.
 * Textarea Shadcn + guardar no onBlur / botão. Campo `observations`
 * (com fallback para `notes` em processos antigos).
 */
import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Button } from "../ui/button";
import { Textarea } from "../ui/textarea";
import { Label } from "../ui/label";
import { Loader2, StickyNote } from "lucide-react";
import { resolveProcessObservations } from "../../utils/summaryTimeline";

export default function ProcessObservationsCard({
  process,
  onSave,
  disabled = false,
  saving = false,
}) {
  const stored = resolveProcessObservations(process);
  const [value, setValue] = useState(stored);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (!dirty) setValue(stored);
  }, [stored, dirty]);

  const persist = async () => {
    if (disabled || saving) return;
    const next = value ?? "";
    if (next === stored) {
      setDirty(false);
      return;
    }
    await onSave?.(next);
    setDirty(false);
  };

  return (
    <Card className="border-border" data-testid="process-observations-card">
      <CardHeader className="pb-2 py-3 flex flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle className="text-sm flex items-center gap-2">
          <StickyNote className="h-4 w-4 text-muted-foreground" />
          Observações
        </CardTitle>
        <Button
          size="sm"
          variant={dirty ? "default" : "outline"}
          onClick={persist}
          disabled={disabled || saving || !dirty}
          data-testid="process-observations-save"
        >
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Guardar"}
        </Button>
      </CardHeader>
      <CardContent>
        <Label htmlFor="process-observations" className="sr-only">
          Observações do processo
        </Label>
        <Textarea
          id="process-observations"
          data-testid="process-observations-input"
          placeholder="Notas internas de fácil acesso — escrituras, contexto da lead, combinados com o cliente…"
          value={value}
          disabled={disabled || saving}
          onChange={(e) => {
            setValue(e.target.value);
            setDirty(true);
          }}
          onBlur={persist}
          className="min-h-[120px] text-sm resize-none"
        />
      </CardContent>
    </Card>
  );
}
