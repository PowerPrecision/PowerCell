/**
 * HistoryTab — separador "Histórico" da página de detalhes do processo.
 *
 * PACOTE DS: a auditoria deixa de ser uma lista básica. Junta timeline de
 * fases + tabela rica (quem / o quê / quando / detalhes) + notas manuais
 * atrás de um Dialog (Progressive Disclosure).
 */
import { useEffect, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../../ui/card";
import { Button } from "../../ui/button";
import { Textarea } from "../../ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "../../ui/dialog";
import { History, MessageSquare, Mic, Send, Loader2, Plus } from "lucide-react";
import ProcessTimeline from "../../ProcessTimeline";
import VoiceNoteRecorder from "../VoiceNoteRecorder";
import UnifiedAuditTrail from "../../UnifiedAuditTrail";

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
  // ── Nota de voz (Épico 7) ──────────────────────────────────────────
  // O separador só rende o botão e o diálogo: quem detém o estado e quem
  // fala com a API é o contentor (`ProcessDetails`).
  voiceNoteOpen = false,
  onVoiceNoteOpenChange,
  onEnviarNotaDeVoz,
  aEnviarNotaDeVoz = false,
  aProcessarNotaDeVoz = false,
}) {
  const [isNoteDialogOpen, setIsNoteDialogOpen] = useState(false);
  const wasSendingRef = useRef(false);

  useEffect(() => {
    if (wasSendingRef.current && !sendingComment && !newComment.trim()) {
      setIsNoteDialogOpen(false);
    }
    wasSendingRef.current = sendingComment;
  }, [sendingComment, newComment]);

  return (
    <div className="space-y-6">
      <ProcessTimeline
        processId={processId}
        currentStatus={process?.status}
        history={history}
        workflowStatuses={workflowStatuses}
      />

      <Card className="border-border">
        <CardHeader className="pb-2 py-3 flex flex-row items-center justify-between gap-2 space-y-0">
          <CardTitle className="text-sm flex items-center gap-2">
            <History className="h-4 w-4 text-primary" />
            Histórico de Auditoria
          </CardTitle>
          {!isProcessLocked && onEnviarNotaDeVoz && (
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5"
              onClick={() => onVoiceNoteOpenChange?.(true)}
              data-testid="voice-note-open"
            >
              <Mic className="h-3.5 w-3.5" />
              Nota de voz
            </Button>
          )}
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
          {/* BUGFIX (visual): maxHeight alinhado com o contentor de scroll
              nativo do UnifiedAuditTrail (overflow-x-auto + overflow-y-auto). */}
          <UnifiedAuditTrail
            history={history}
            activities={activities}
            maxHeight="600px"
            currentUser={user}
            onDeleteComment={handleDeleteComment}
          />
        </CardContent>
      </Card>

      {onEnviarNotaDeVoz && (
        <VoiceNoteRecorder
          open={voiceNoteOpen}
          onOpenChange={onVoiceNoteOpenChange}
          onEnviar={onEnviarNotaDeVoz}
          aEnviar={aEnviarNotaDeVoz}
          aProcessar={aProcessarNotaDeVoz}
        />
      )}
    </div>
  );
}
