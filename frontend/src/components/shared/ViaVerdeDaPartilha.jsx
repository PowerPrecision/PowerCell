/**
 * «Via Verde» da partilha com uma rede de destino.
 *
 * Quando um processo é partilhado com uma rede que tem equipa de Index, entra na
 * fila de triagem (Index) dessa rede — salvo se esta opção estiver ligada, caso
 * em que salta o Index e vai direto para a consultoria (ex.: só crédito).
 *
 * É DIFERENTE da «Via Verde (Ignorar fase de Indexação)» do próprio processo:
 * aquela dispensa o Index da rede onde o processo nasce; esta decide o que
 * acontece ao partilhá-lo com outra.
 */
import React from "react";
import { Share2 } from "lucide-react";

import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

export default function ViaVerdeDaPartilha({ id = "via-verde-partilha-switch", checked, onCheckedChange }) {
  return (
    <div className="flex items-start gap-3 rounded-md border border-border bg-muted/30 p-3">
      <Switch id={id} checked={Boolean(checked)} onCheckedChange={onCheckedChange} />
      <div className="space-y-0.5">
        <Label htmlFor={id} className="flex cursor-pointer items-center gap-1.5 text-sm">
          <Share2 className="h-3.5 w-3.5" aria-hidden="true" />
          Via Verde ao partilhar com outra rede
        </Label>
        <p className="text-xs text-muted-foreground">
          Se este processo for partilhado com uma rede que tem Index, salta a fila de triagem
          e vai direto para a consultoria. Desligado, entra na fila de Index dessa rede.
        </p>
      </div>
    </div>
  );
}
