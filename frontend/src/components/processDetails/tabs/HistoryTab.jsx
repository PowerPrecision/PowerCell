/**
 * HistoryTab — separador "Histórico" da página de detalhes do processo.
 *
 * PORQUÊ (Progressive Disclosure): agrupa tudo o que é cronológico — a
 * timeline de fases, o registo manual de notas/atividades, e o "Filme da
 * Lead" (auditoria unificada de todos os eventos do sistema) — num único
 * separador, fora do fluxo principal de edição de dados ("Resumo").
 *
 * O formulário "Registar Atividade" vive num Dialog (aberto sob pedido) em
 * vez de ocupar espaço permanentemente, e a lista "Atividades Recentes" é
 * compacta e contida num ScrollArea com altura máxima — nenhum dos dois
 * elementos deve fazer a página crescer indefinidamente.
 */
import { useEffect, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../../ui/card";
import { Button } from "../../ui/button";
import { Textarea } from "../../ui/textarea";
import { ScrollArea } from "../../ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "../../ui/dialog";
import { Clock, MessageSquare, Send, Loader2, Trash2, Plus } from "lucide-react";
import { pt } from "date-fns/locale";
import ProcessTimeline from "../../ProcessTimeline";
import UnifiedAuditTrail from "../../UnifiedAuditTrail";
import { safeString } from "../../../utils/safeString";
import { safeFormat, safeDate } from "../../../lib/utils";
import { hasRole } from "../../../utils/roleUtils";

export default function HistoryTab({
  processId,
  process,
  history,
  workflowStatuses,
  activities,
  newComment,
  setNewComment,
  sendingComment,
  handleSendComment,
  handleDeleteComment,
  user,
  isProcessLocked,
}) {
  const [isNoteDialogOpen, setIsNoteDialogOpen] = useState(false);
  const wasSendingRef = useRef(false);

  // Fecha o diálogo automaticamente assim que o envio termina com sucesso
  // (o comentário fica vazio); em caso de erro o texto permanece e o
  // diálogo continua aberto para o utilizador tentar de novo.
  useEffect(() => {
    if (wasSendingRef.current && !sendingComment && !newComment.trim()) {
      setIsNoteDialogOpen(false);
    }
    wasSendingRef.current = sendingComment;
  }, [sendingComment, newComment]);

  const sortedActivities = [...activities].sort((a, b) => {
    // Ordenação descendente por data (mais recentes primeiro), com
    // tratamento defensivo de datas inválidas (ficam no fim).
    const dateA = safeDate(a.created_at || a.timestamp);
    const dateB = safeDate(b.created_at || b.timestamp);
    if (!dateA && !dateB) return 0;
    if (!dateA) return 1;
    if (!dateB) return -1;
    return dateB - dateA;
  });

  return (
    <div className="space-y-6">
      {/* Timeline de fases do processo */}
      <ProcessTimeline
        processId={processId}
        currentStatus={process?.status}
        history={history}
        workflowStatuses={workflowStatuses}
      />

      {/* Atividades Recentes, com "Registar Atividade" atrás de um Dialog (Progressive Disclosure) */}
      <Card className="border-border">
        <CardHeader className="pb-2 py-3 flex flex-row items-center justify-between gap-2 space-y-0">
          <CardTitle className="text-sm flex items-center gap-2">
            <Clock className="h-4 w-4 text-muted-foreground" />
            Atividades Recentes
          </CardTitle>
          {!isProcessLocked && (
            <Dialog open={isNoteDialogOpen} onOpenChange={setIsNoteDialogOpen}>
              <DialogTrigger asChild>
                <Button size="sm" className="gap-1.5" data-testid="quick-note-open">
                  <Plus className="h-3.5 w-3.5" />
                  Registar Atividade
                </Button>
              </DialogTrigger>
              <DialogContent
                title="Registar Atividade / Nota"
                description="Escreva uma nota ou registo de atividade para este processo."
              >
                <DialogHeader>
                  <DialogTitle className="flex items-center gap-2 text-base">
                    <MessageSquare className="h-4 w-4 text-primary" />
                    Registar Atividade / Nota
                  </DialogTitle>
                  <DialogDescription>
                    Escreva uma nota ou registo de atividade para este processo.
                  </DialogDescription>
                </DialogHeader>
                <Textarea
                  placeholder="Escreva uma nota ou registo de atividade para este processo..."
                  value={newComment}
                  onChange={(e) => setNewComment(e.target.value)}
                  className="min-h-[100px] text-sm resize-none"
                  data-testid="quick-note-input"
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                      e.preventDefault();
                      handleSendComment();
                    }
                  }}
                />
                <p className="text-xs text-muted-foreground -mt-2">Cmd/Ctrl+Enter para enviar rápido</p>
                <DialogFooter>
                  <Button
                    onClick={handleSendComment}
                    disabled={sendingComment || !newComment.trim()}
                    data-testid="quick-note-submit"
                  >
                    {sendingComment ? (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <Send className="h-4 w-4 mr-2" />
                    )}
                    Enviar
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          )}
        </CardHeader>
        <CardContent className="pt-0 pb-3">
          <ScrollArea className="h-[500px]">
            <div className="space-y-1.5 pr-2">
              {sortedActivities.length === 0 ? (
                <p className="text-center text-muted-foreground py-4 text-xs">
                  Sem registos. Clique em &quot;Registar Atividade&quot; para adicionar o primeiro.
                </p>
              ) : (
                sortedActivities.map((activity) => (
                  <div
                    key={activity.id}
                    className="px-2 py-1.5 bg-muted/50 rounded text-xs"
                    data-testid={`activity-${activity.id}`}
                  >
                    <div className="flex items-start justify-between gap-1">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-baseline gap-1.5">
                          <span className="font-medium text-xs">{safeString(activity.user_name)}</span>
                          <span className="text-[10px] text-muted-foreground shrink-0">
                            {safeFormat(activity.created_at, "dd/MM HH:mm", { locale: pt })}
                          </span>
                        </div>
                        <p className="text-xs mt-0.5 text-muted-foreground whitespace-pre-wrap">
                          {safeString(activity.comment)}
                        </p>
                      </div>
                      {(activity.user_id === user.id || hasRole(user, "admin")) && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-6 w-6 shrink-0"
                          onClick={() => handleDeleteComment(activity.id)}
                        >
                          <Trash2 className="h-3 w-3 text-destructive" />
                        </Button>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>

      {/* Filme da Lead — auditoria unificada de todos os eventos */}
      <Card className="border-border">
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <Clock className="h-4 w-4 text-primary" />
            Filme da Lead
          </CardTitle>
        </CardHeader>
        <CardContent>
          <UnifiedAuditTrail history={history} activities={activities} maxHeight="450px" />
        </CardContent>
      </Card>
    </div>
  );
}
