/**
 * Conversa com a equipa de análise (o Index) sobre um processo que o parceiro carregou (Out 2026).
 *
 * O Index escreve da bancada; o parceiro lê e responde aqui (e recebe um email quando há mensagem nova
 * por ler). Só se vêem as mensagens trocadas COM o parceiro — nunca as internas da equipa.
 *
 * Sem mensagens e sem ninguém do Index no processo, o cartão não aparece: não há com quem falar.
 */
import React, { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, MessagesSquare, Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { queryKeys } from "@/lib/queryClient";
import { enviarConversaIndex, obterConversaIndex } from "@/services/partnerApi";
import { formatarData, mensagemDeErro } from "@/utils/partnerPortal";

const MAX_CARACTERES = 4000;

export default function ConversaComAEquipa({ caseId, podeEscrever = true }) {
  const queryClient = useQueryClient();
  const chave = queryKeys.partner.conversaIndex(caseId);
  const [texto, setTexto] = useState("");
  const [erro, setErro] = useState("");
  const [aEnviar, setAEnviar] = useState(false);

  const { data, isLoading, isError } = useQuery({
    queryKey: chave,
    queryFn: () => obterConversaIndex(caseId),
    enabled: Boolean(caseId),
    refetchInterval: 30000,
  });

  const mensagens = data?.messages || [];
  const interlocutor = data?.interlocutor || null;
  if (isLoading || isError || (!interlocutor && mensagens.length === 0)) return null;

  const enviar = async (evento) => {
    evento?.preventDefault?.();
    const t = texto.trim();
    if (!t || aEnviar) return;
    setAEnviar(true);
    setErro("");
    try {
      await enviarConversaIndex(caseId, t);
      setTexto("");
      await queryClient.invalidateQueries({ queryKey: chave });
    } catch (e) {
      // o texto fica na caixa: perder o que se escreveu por uma falha é pior do que a falha
      setErro(mensagemDeErro(e, "Não foi possível enviar a mensagem."));
    } finally {
      setAEnviar(false);
    }
  };

  return (
    <Card data-testid="conversa-com-a-equipa">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <MessagesSquare className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          Conversa com a equipa de análise
          {interlocutor?.name && (
            <span className="text-sm font-normal text-muted-foreground">· {interlocutor.name}</span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {mensagens.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Ainda sem mensagens. Se tiver alguma dúvida sobre os documentos, escreva aqui.
          </p>
        ) : (
          <ul className="max-h-72 space-y-2 overflow-y-auto pr-1" data-testid="conversa-mensagens">
            {mensagens.map((m) => (
              <li key={m.id} className={`flex ${m.mine ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[85%] rounded-lg px-3 py-2 ${
                    m.mine ? "bg-primary text-primary-foreground" : "bg-muted text-foreground"
                  }`}
                >
                  <p className="whitespace-pre-wrap text-sm">{m.content}</p>
                  <p className={`mt-1 text-[11px] ${m.mine ? "text-primary-foreground/80" : "text-muted-foreground"}`}>
                    {m.sender_name}
                    {m.created_at ? ` · ${formatarData(m.created_at)}` : ""}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}

        {podeEscrever && interlocutor && (
          <form onSubmit={enviar} className="space-y-2" noValidate>
            <Label htmlFor={`conversa-equipa-${caseId}`} className="sr-only">
              Mensagem para a equipa
            </Label>
            <Textarea
              id={`conversa-equipa-${caseId}`}
              data-testid="conversa-texto"
              rows={2}
              maxLength={MAX_CARACTERES}
              value={texto}
              disabled={aEnviar}
              placeholder="Responder à equipa…"
              onChange={(e) => { setTexto(e.target.value); setErro(""); }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) enviar(e);
              }}
            />
            {erro && <p role="alert" className="text-sm text-destructive">{erro}</p>}
            <div className="flex justify-end">
              <Button type="submit" size="sm" disabled={aEnviar || !texto.trim()} data-testid="conversa-enviar">
                {aEnviar
                  ? <Loader2 className="mr-1 h-4 w-4 animate-spin" aria-hidden="true" />
                  : <Send className="mr-1 h-4 w-4" aria-hidden="true" />}
                Enviar
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
