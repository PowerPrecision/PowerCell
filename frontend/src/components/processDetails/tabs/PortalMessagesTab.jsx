/**
 * Tab de Mensagens do Portal (cliente ↔ staff).
 * Extraído de ProcessDetails.js — recebe o estado do hook useProcessPortalMessages.
 */
import { useRef } from "react";
import { Card, CardContent } from "../../ui/card";
import { Button } from "../../ui/button";
import { Textarea } from "../../ui/textarea";
import {
  MessageSquare,
  RefreshCw,
  Loader2,
  Send,
} from "lucide-react";
import { pt } from "date-fns/locale";
import { safeString } from "../../../utils/safeString";
import { safeFormat } from "../../../lib/utils";

export default function PortalMessagesTab({
  messages = [],
  loading = false,
  newMessage = "",
  setNewMessage,
  sending = false,
  onRefresh,
  onSend,
}) {
  const endRef = useRef(null);

  return (
    <div className="space-y-4">
      <div className="bg-violet-50 dark:bg-violet-900/20 border border-violet-200 dark:border-violet-800 rounded-lg p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-violet-100 dark:bg-violet-900/40 rounded-lg">
              <MessageSquare className="h-6 w-6 text-violet-600 dark:text-violet-400" />
            </div>
            <div>
              <h3 className="font-semibold text-violet-800 dark:text-violet-200">Mensagens com o Cliente</h3>
              <p className="text-sm text-violet-600 dark:text-violet-400">
                Comunicação direta com o cliente via Portal
              </p>
            </div>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5"
            onClick={() => onRefresh?.()}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Actualizar
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="p-4">
          {loading && messages.length === 0 ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-violet-500" />
              <span className="ml-3 text-muted-foreground">A carregar mensagens...</span>
            </div>
          ) : messages.length === 0 ? (
            <div className="text-center py-12">
              <MessageSquare className="h-12 w-12 mx-auto mb-3 text-muted-foreground/30" />
              <p className="text-muted-foreground">Sem mensagens ainda</p>
              <p className="text-xs text-muted-foreground/70 mt-1">Envie a primeira mensagem ao cliente</p>
            </div>
          ) : (
            <div className="max-h-96 overflow-y-auto space-y-3 pr-1">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex ${msg.sender_type === "staff" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[80%] rounded-xl px-4 py-2.5 ${
                      msg.sender_type === "staff"
                        ? "bg-violet-100 dark:bg-violet-900/30 rounded-br-sm"
                        : "bg-gray-100 dark:bg-gray-800 rounded-bl-sm"
                    }`}
                  >
                    {msg.sender_type === "client" && (
                      <p className="text-xs font-medium text-violet-600 dark:text-violet-400 mb-1">
                        {safeString(msg.sender_name)}
                      </p>
                    )}
                    {msg.sender_type === "staff" && (
                      <p className="text-xs font-medium text-right text-gray-500 dark:text-gray-400 mb-1">
                        {safeString(msg.sender_name)} (Equipamento)
                      </p>
                    )}
                    <p className="text-sm whitespace-pre-wrap break-words">{safeString(msg.content)}</p>
                    <p className="text-[10px] text-muted-foreground mt-1 text-right">
                      {msg.created_at ? safeFormat(msg.created_at, "dd/MM/yyyy HH:mm", { locale: pt }) : ""}
                    </p>
                  </div>
                </div>
              ))}
              <div ref={endRef} />
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4">
          <div className="flex gap-2">
            <Textarea
              placeholder="Escreva uma mensagem para o cliente..."
              value={newMessage}
              onChange={(e) => setNewMessage?.(e.target.value)}
              className="flex-1 min-h-[44px] max-h-32 resize-none"
              rows={2}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  onSend?.();
                }
              }}
            />
            <Button
              className="bg-violet-600 hover:bg-violet-700 self-end gap-1.5"
              onClick={onSend}
              disabled={!newMessage.trim() || sending}
            >
              {sending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
              Enviar
            </Button>
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            A mensagem ficará visível no portal do cliente. Prima Enter para enviar.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
