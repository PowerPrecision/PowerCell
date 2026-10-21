/**
 * As notas do processo: as da equipa (só leitura) e as do próprio parceiro (que ele escreve).
 *
 * O parceiro é um interveniente activo: lê o que a equipa escreveu no cartão «Observações» do CRM e
 * deixa as suas notas — que entram nesse mesmo feed, marcadas como suas. O servidor devolve tudo no
 * detalhe do caso (`notas_da_equipa`, com `do_parceiro` / `e_minha`); a nota nova refaz o detalhe.
 *
 * Só se escreve num PROCESSO aberto (`podeEscreverNotas`); numa lead ou num processo fechado o
 * formulário nem existe — o servidor recusava, e um botão que falha é pior do que nenhum. Sem notas,
 * diz-se: um cartão que desaparece lê-se como funcionalidade partida.
 */
import React, { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Send, StickyNote } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { queryKeys } from "@/lib/queryClient";
import { escreverNota } from "@/services/partnerApi";
import {
  MAX_CARACTERES_DA_NOTA,
  formatarData,
  mensagemDeErro,
  validarNota,
} from "@/utils/partnerPortal";

function NovaNota({ caseId }) {
  const queryClient = useQueryClient();
  const [texto, setTexto] = useState("");
  const [erro, setErro] = useState("");
  const [aEnviar, setAEnviar] = useState(false);

  const enviar = async (evento) => {
    evento.preventDefault();
    if (aEnviar) return;
    const problema = validarNota(texto);
    setErro(problema);
    if (problema) return;
    setAEnviar(true);
    try {
      await escreverNota(caseId, texto.trim());
      setTexto("");
      // O detalhe leva a nota nova (e as que a equipa escreveu entretanto); a actividade mudou.
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.partner.caso(caseId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.partner.casosAll() }),
      ]);
    } catch (e) {
      // O texto fica na caixa: perder o que se escreveu por uma falha de rede é pior do que a falha.
      setErro(mensagemDeErro(e, "Não foi possível gravar a nota."));
    } finally {
      setAEnviar(false);
    }
  };

  return (
    <form onSubmit={enviar} className="space-y-2" data-testid="nova-nota" noValidate>
      <Label htmlFor={`nova-nota-${caseId}`}>Nova nota</Label>
      <Textarea
        id={`nova-nota-${caseId}`}
        value={texto}
        maxLength={MAX_CARACTERES_DA_NOTA}
        onChange={(e) => { setTexto(e.target.value); setErro(""); }}
        placeholder="Ex.: o cliente já reuniu os recibos de vencimento."
        aria-invalid={Boolean(erro)}
        disabled={aEnviar}
        rows={3}
      />
      {erro && <p role="alert" className="text-sm text-destructive">{erro}</p>}
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">{texto.length}/{MAX_CARACTERES_DA_NOTA}</span>
        <Button type="submit" size="sm" disabled={aEnviar} data-testid="enviar-nota">
          {aEnviar
            ? <Loader2 className="mr-1 h-4 w-4 animate-spin" aria-hidden="true" />
            : <Send className="mr-1 h-4 w-4" aria-hidden="true" />}
          Guardar nota
        </Button>
      </div>
    </form>
  );
}

export default function NotasDaEquipa({ notas, caseId, podeEscrever = false }) {
  const lista = Array.isArray(notas) ? notas : [];
  return (
    <Card data-testid="notas-da-equipa" className="border-2 border-border">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <StickyNote className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          Notas
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {podeEscrever && caseId && <NovaNota caseId={caseId} />}
        {lista.length === 0 ? (
          <p className="text-sm text-muted-foreground">Ainda não há notas neste processo.</p>
        ) : (
          <ul className="space-y-3">
            {lista.map((n) => (
              <li
                key={n.id}
                data-testid={n.e_minha ? "nota-minha" : n.do_parceiro ? "nota-de-parceiro" : "nota-da-equipa"}
                className={`rounded-md border p-3 ${n.e_minha ? "border-primary/40 bg-primary/5" : "border-border bg-secondary/40"}`}
              >
                <p className="whitespace-pre-line break-words text-sm">{n.text}</p>
                <p className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                  {n.e_minha
                    ? <Badge variant="secondary">Você</Badge>
                    : n.do_parceiro
                      ? <Badge variant="outline">Parceiro</Badge>
                      : null}
                  <span>
                    {[n.e_minha ? null : n.author_name, n.created_at && formatarData(n.created_at)].filter(Boolean).join(" · ")}
                  </span>
                </p>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
