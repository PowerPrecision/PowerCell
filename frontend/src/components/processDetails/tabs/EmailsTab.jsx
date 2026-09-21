/**
 * EmailsTab — extraído de ProcessDetails.js (tab emails).
 * Histórico de emails associados ao processo (filtro estrito por process_id).
 *
 * PACOTE 12 (Eixo 2):
 * - Subtítulo com a semântica estrita (apenas emails associados ao processo);
 * - Botão "+ Novo" que abre o compositor do Webmail pré-preenchido com o
 *   email do cliente e o processo activo (?compose=new&to=&process_id=).
 */
import { Button } from "../../ui/button";
import { Card, CardContent } from "../../ui/card";
import EmailHistoryPanel from "../../EmailHistoryPanel";
import { Plus, Send } from "lucide-react";
import { useNavigate } from "react-router-dom";

export default function EmailsTab({ id, savedProcessRef, process, token }) {
  const navigate = useNavigate();
  const clientEmail = savedProcessRef.current?.client_email || process?.client_email;

  // PACOTE 12 — abre o Webmail com o compositor pré-preenchido (destinatário
  // = email do cliente; processo já associado para a Tag Mágica/histórico).
  const handleNewEmail = () => {
    const params = new URLSearchParams({ compose: "new", process_id: id });
    if (clientEmail) params.set("to", clientEmail);
    navigate(`/webmail?${params.toString()}`);
  };

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border bg-muted/40 p-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/10">
            <Send className="h-6 w-6 text-primary" />
          </div>
          <div className="min-w-0">
            <h3 className="font-semibold text-foreground">Histórico de Emails</h3>
            <p className="text-sm text-muted-foreground">
              Emails enviados e recebidos associados a este processo.
              Clique numa linha para ler.
            </p>
          </div>
          <Button
            size="sm"
            className="h-8 text-xs gap-1.5 ml-auto shrink-0"
            onClick={handleNewEmail}
          >
            <Plus className="h-3.5 w-3.5" />
            Novo
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="pt-6">
          <EmailHistoryPanel
            processId={id}
            clientEmail={clientEmail}
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
