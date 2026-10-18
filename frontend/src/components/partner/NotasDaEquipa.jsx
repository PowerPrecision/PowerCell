/**
 * As notas que a equipa escreveu no processo, só de leitura.
 *
 * O parceiro não escreve aqui: as notas são do CRM (cartão «Observações»);
 * o servidor devolve-as no detalhe do caso e este cartão só as mostra. Sem
 * notas, diz-se — um cartão que desaparece lê-se como funcionalidade partida.
 */
import React from "react";
import { StickyNote } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatarData } from "@/utils/partnerPortal";

export default function NotasDaEquipa({ notas }) {
  const lista = Array.isArray(notas) ? notas : [];
  return (
    <Card data-testid="notas-da-equipa" className="border-2 border-border">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <StickyNote className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          Notas da equipa
        </CardTitle>
      </CardHeader>
      <CardContent>
        {lista.length === 0 ? (
          <p className="text-sm text-muted-foreground">A equipa ainda não deixou notas neste processo.</p>
        ) : (
          <ul className="space-y-3">
            {lista.map((n) => (
              <li key={n.id} className="rounded-md border border-border bg-secondary/40 p-3">
                <p className="whitespace-pre-line text-sm">{n.text}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {[n.author_name, n.created_at && formatarData(n.created_at)].filter(Boolean).join(" · ")}
                </p>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
