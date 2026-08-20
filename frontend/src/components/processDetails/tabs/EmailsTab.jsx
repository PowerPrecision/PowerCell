/**
 * EmailsTab — extraído de ProcessDetails.js (tab emails).
 * Histórico de emails associados ao processo (from/to/cc do cliente).
 */
import { Card, CardContent } from "../../ui/card";
import EmailHistoryPanel from "../../EmailHistoryPanel";
import { Send } from "lucide-react";

export default function EmailsTab({ id, savedProcessRef, process, token }) {
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border bg-muted/40 p-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/10">
            <Send className="h-6 w-6 text-primary" />
          </div>
          <div>
            <h3 className="font-semibold text-foreground">Histórico de Emails</h3>
            <p className="text-sm text-muted-foreground">
              Mensagens ligadas a este processo ou em que o cliente aparece em De, Para ou CC.
              Clique numa linha para ler.
            </p>
          </div>
        </div>
      </div>

      <Card>
        <CardContent className="pt-6">
          <EmailHistoryPanel
            processId={id}
            clientEmail={savedProcessRef.current?.client_email || process?.client_email}
            clientName={savedProcessRef.current?.client_name || process?.client_name}
            compact={false}
            maxHeight="500px"
            token={token}
          />
        </CardContent>
      </Card>
    </div>
  );
}
