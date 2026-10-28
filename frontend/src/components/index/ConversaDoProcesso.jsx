/**
 * ConversaDoProcesso — a conversa entre o Index e quem carregou o processo (Out 2026).
 *
 * O mesmo cartão vive nos dois lados:
 *   - `lado="index"`: na bancada do Index, a falar com quem carregou o processo;
 *   - `lado="processo"`: no detalhe do processo, a responder ao Index.
 *
 * As mensagens são do chat interno (ligadas ao processo), por isso também aparecem lá, com o contador
 * de não lidas; uma resposta dada no chat interno volta aqui. Abrir o cartão marca como lido.
 */
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, MessagesSquare, Send } from "lucide-react";
import { toast } from "sonner";

import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Label } from "../ui/label";
import { Textarea } from "../ui/textarea";
import { formatDateTime } from "../../lib/utils";
import { queryKeys } from "../../lib/queryClient";
import {
  getIndexConversa,
  getProcessConversaIndex,
  sendIndexConversa,
  sendProcessConversaIndex,
} from "../../services/api";
import { extractErrorMessage } from "../../utils/extractErrorMessage";

const LADOS = {
  index: {
    titulo: "Conversa com quem carregou",
    ler: getIndexConversa,
    enviar: sendIndexConversa,
    semInterlocutor: "Não foi possível identificar quem carregou este processo.",
    vazio: "Ainda sem mensagens. Escreva aqui o que falta ou o que precisa de esclarecer.",
    placeholder: "Escrever a quem carregou o processo…",
  },
  processo: {
    titulo: "Conversa com o Index",
    ler: getProcessConversaIndex,
    enviar: sendProcessConversaIndex,
    semInterlocutor: "Este processo ainda não tem ninguém do Index atribuído.",
    vazio: "Ainda sem mensagens do Index sobre este processo.",
    placeholder: "Responder ao Index…",
  },
};

const INTERVALO_DE_ACTUALIZACAO = 20000;

export function ConversaDoProcesso({ processoId, lado = "index", className = "" }) {
  const cfg = LADOS[lado] || LADOS.index;
  const queryClient = useQueryClient();
  const chave = queryKeys.index.conversa(processoId, lado);
  const [rascunho, setRascunho] = useState("");
  const fimRef = useRef(null);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: chave,
    queryFn: () => cfg.ler(processoId).then((r) => r.data),
    enabled: Boolean(processoId),
    refetchInterval: INTERVALO_DE_ACTUALIZACAO,
  });

  const enviar = useMutation({
    mutationFn: (text) => cfg.enviar(processoId, text).then((r) => r.data),
    onSuccess: () => {
      setRascunho("");
      queryClient.invalidateQueries({ queryKey: chave });
    },
    onError: (erro) => toast.error(extractErrorMessage(erro?.response?.data?.detail, "A mensagem não foi enviada.")),
  });

  const mensagens = data?.messages || [];
  const interlocutor = data?.interlocutor || null;

  useEffect(() => {
    fimRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [mensagens.length]);

  const submeter = () => {
    const texto = rascunho.trim();
    if (!texto || enviar.isPending || !interlocutor) return;
    enviar.mutate(texto);
  };

  return (
    <Card className={className} data-testid={`conversa-${lado}`}>
      <CardHeader className="pb-3">
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          <MessagesSquare className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          {cfg.titulo}
          {interlocutor && (
            <span className="text-sm font-normal text-muted-foreground" data-testid="conversa-interlocutor">
              · {interlocutor.name}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />A carregar a conversa…
          </p>
        ) : isError ? (
          <p className="text-sm text-destructive">
            Não foi possível carregar a conversa.{" "}
            <button type="button" className="underline" onClick={() => refetch()}>
              Tentar de novo
            </button>
          </p>
        ) : mensagens.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="conversa-vazia">
            {interlocutor ? cfg.vazio : cfg.semInterlocutor}
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
                    {m.mine ? "Eu" : m.sender_name}
                    {m.created_at ? ` · ${formatDateTime(m.created_at)}` : ""}
                  </p>
                </div>
              </li>
            ))}
            <li ref={fimRef} aria-hidden="true" />
          </ul>
        )}

        {interlocutor && (
          <div className="space-y-2">
            <Label htmlFor={`conversa-texto-${lado}`} className="sr-only">
              Mensagem
            </Label>
            {/* Enter envia; Shift+Enter muda de linha (como no chat interno) */}
            <Textarea
              id={`conversa-texto-${lado}`}
              data-testid="conversa-texto"
              rows={2}
              maxLength={4000}
              placeholder={cfg.placeholder}
              value={rascunho}
              disabled={enviar.isPending}
              onChange={(e) => setRascunho(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  submeter();
                }
              }}
              className="min-h-[64px] resize-y text-sm"
            />
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-muted-foreground">
                Também chega ao chat interno de {interlocutor.name}.
              </span>
              <Button
                size="sm"
                onClick={submeter}
                disabled={!rascunho.trim() || enviar.isPending}
                data-testid="conversa-enviar"
              >
                {enviar.isPending ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                ) : (
                  <Send className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                )}
                Enviar
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default ConversaDoProcesso;
