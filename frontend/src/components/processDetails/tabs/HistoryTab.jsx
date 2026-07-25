/**
 * HistoryTab — separador "Histórico" da página de detalhes do processo.
 *
 * PORQUÊ (Progressive Disclosure): agrupa tudo o que é cronológico — a
 * timeline de fases, o registo manual de notas/atividades, e o "Filme da
 * Lead" (auditoria unificada de todos os eventos do sistema) — num único
 * separador, fora do fluxo principal de edição de dados ("Resumo").
 */
import { Card, CardContent, CardHeader, CardTitle } from "../../ui/card";
import { Button } from "../../ui/button";
import { Textarea } from "../../ui/textarea";
import { ScrollArea } from "../../ui/scroll-area";
import { Clock, MessageSquare, Send, Loader2, Trash2 } from "lucide-react";
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
  return (
    <div className="space-y-6">
      {/* Timeline de fases do processo */}
      <ProcessTimeline
        processId={processId}
        currentStatus={process?.status}
        history={history}
        workflowStatuses={workflowStatuses}
      />

      {/* Registar Atividade / Nota + Atividades Recentes */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {!isProcessLocked && (
          <Card className="border-border">
            <CardHeader className="pb-2 py-3">
              <CardTitle className="text-sm flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-primary" />
                Registar Atividade / Nota
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0 pb-3">
              <div className="flex gap-2">
                <Textarea
                  placeholder="Escreva uma nota ou registo de atividade para este processo..."
                  value={newComment}
                  onChange={(e) => setNewComment(e.target.value)}
                  className="flex-1 min-h-[60px] text-sm resize-none"
                  data-testid="quick-note-input"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                      e.preventDefault();
                      handleSendComment();
                    }
                  }}
                />
                <Button
                  onClick={handleSendComment}
                  disabled={sendingComment || !newComment.trim()}
                  size="sm"
                  data-testid="quick-note-submit"
                >
                  {sendingComment ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </Button>
              </div>
              <p className="text-[10px] text-muted-foreground mt-1.5">Cmd/Ctrl+Enter para enviar rápido</p>
            </CardContent>
          </Card>
        )}

        <Card className="border-border">
          <CardHeader className="pb-2 py-3">
            <CardTitle className="text-sm flex items-center gap-2">
              <Clock className="h-4 w-4 text-muted-foreground" />
              Atividades Recentes
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0 pb-3">
            <ScrollArea className="h-[300px]">
              <div className="space-y-2 pr-2">
                {activities.length === 0 ? (
                  <p className="text-center text-muted-foreground py-4 text-xs">Sem registos. Adicione a primeira nota à esquerda.</p>
                ) : (
                  // Ordenação descendente por data (mais recentes primeiro), com
                  // tratamento defensivo de datas inválidas (ficam no fim).
                  [...activities].sort((a, b) => {
                    const dateA = safeDate(a.created_at || a.timestamp);
                    const dateB = safeDate(b.created_at || b.timestamp);
                    if (!dateA && !dateB) return 0;
                    if (!dateA) return 1;
                    if (!dateB) return -1;
                    return dateB - dateA;
                  }).map((activity) => (
                    <div key={activity.id} className="p-2 bg-muted/50 rounded text-xs" data-testid={`activity-${activity.id}`}>
                      <div className="flex items-start justify-between gap-1">
                        <div className="flex-1 min-w-0">
                          <span className="font-medium">{safeString(activity.user_name)}</span>
                          <p className="text-xs mt-0.5 text-muted-foreground whitespace-pre-wrap">{safeString(activity.comment)}</p>
                          <p className="text-[10px] text-muted-foreground">{safeFormat(activity.created_at, "dd/MM HH:mm", { locale: pt })}</p>
                        </div>
                        {(activity.user_id === user.id || hasRole(user, "admin")) && (
                          <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={() => handleDeleteComment(activity.id)}>
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
      </div>

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
