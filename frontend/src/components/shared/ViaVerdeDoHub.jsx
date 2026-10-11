/**
 * «Via Verde» da partilha com o Hub.
 *
 * A Precision é o Hub (tem a equipa de Index). Quando um processo de uma rede
 * satélite é partilhado com o Hub, entra na fila de triagem (Index) do Hub —
 * salvo se esta opção estiver ligada, caso em que salta o Index e vai direto
 * para a consultoria.
 *
 * É DIFERENTE da «Via Verde (Ignorar fase de Indexação)» do próprio processo:
 * aquela dispensa o Index da rede onde o processo nasce; esta decide o que
 * acontece ao partilhá-lo com outra.
 */
import React from "react";
import { Share2 } from "lucide-react";

import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

export default function ViaVerdeDoHub({ id = "via-verde-hub-switch", checked, onCheckedChange }) {
  return (
    <div className="flex items-start gap-3 rounded-md border border-border bg-muted/30 p-3">
      <Switch id={id} checked={Boolean(checked)} onCheckedChange={onCheckedChange} />
      <div className="space-y-0.5">
        <Label htmlFor={id} className="flex cursor-pointer items-center gap-1.5 text-sm">
          <Share2 className="h-3.5 w-3.5" aria-hidden="true" />
          Via Verde ao partilhar com o Hub
        </Label>
        <p className="text-xs text-muted-foreground">
          Se este processo for partilhado com a Precision (o Hub), salta a fila de triagem
          (Index) e vai direto para a consultoria. Desligado, entra na triagem do Hub.
        </p>
      </div>
    </div>
  );
}
