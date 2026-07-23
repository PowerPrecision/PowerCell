/**
 * EmailsTab — extraído de ProcessDetails.js (tab emails).
 * Histórico de emails associados ao processo.
 */
import { Card, CardContent } from "../../ui/card";
import EmailHistoryPanel from "../../EmailHistoryPanel";
import { Send } from "lucide-react";

export default function EmailsTab({ id, savedProcessRef, process, token }) {
  return (
    <div className="space-y-4">
      {/* Header com info */}
      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-100 dark:bg-blue-900/40 rounded-lg">
            <Send className="h-6 w-6 text-blue-600 dark:text-blue-400" />
          </div>
          <div>
            <h3 className="font-semibold text-blue-800 dark:text-blue-200">Histórico de Emails</h3>
            <p className="text-sm text-blue-600 dark:text-blue-400">
              Emails associados a este processo
            </p>
          </div>
        </div>
      </div>

      {/* Painel de Emails */}
      <Card className="border-blue-200 dark:border-blue-800">
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
