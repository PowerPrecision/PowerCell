/**
 * EmailViewerModal - Modal para visualização de emails
 * Mostra email selecionado com lista de emails ao lado para navegação
 * 
 * MELHORIAS:
 * - Preview e download de anexos
 * - Marcação de emails (importante, lido, estrela)
 * - Resposta rápida com templates
 * - Navegação por setas
 */
import { useState, useEffect, useMemo } from "react";
import { Dialog, DialogContent, DialogTitle, DialogDescription, DialogFooter } from "./ui/dialog";
import { VisuallyHidden } from "@radix-ui/react-visually-hidden";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { ScrollArea } from "./ui/scroll-area";
import { Textarea } from "./ui/textarea";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import { 
  Mail, Send, Inbox, Clock, X, ChevronLeft, ChevronRight,
  Paperclip, User, Star, StarOff, Bookmark, BookmarkX,
  AlertCircle, CheckCircle, Download, Eye, EyeOff, Reply,
  Forward, Archive, MoreVertical, Image, FileText, FileSpreadsheet,
  Sparkles, Copy, ExternalLink, Tag
} from "lucide-react";
import { pt } from "date-fns/locale";
import { sanitizeEmailHtml } from "../utils/sanitize";
import { safeFormat } from "../lib/utils";
import { toast } from "sonner";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Tamanhos de arquivo
const formatFileSize = (bytes) => {
  if (!bytes) return "";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
};

// Ícone por tipo de anexo
const getAttachmentIcon = (contentType) => {
  if (!contentType) return FileText;
  if (contentType.includes("image")) return Image;
  if (contentType.includes("pdf")) return FileText;
  if (contentType.includes("spreadsheet") || contentType.includes("excel")) return FileSpreadsheet;
  return FileText;
};

const EmailViewerModal = ({ 
  isOpen, 
  onClose, 
  emails = [], 
  selectedEmailId,
  onSelectEmail,
  onMarkEmail,
  onUnmarkEmail,
  token,
  clientName,
  processId
}) => {
  const [currentEmail, setCurrentEmail] = useState(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [showReplyBox, setShowReplyBox] = useState(false);
  const [replySubject, setReplySubject] = useState("");
  const [replyBody, setReplyBody] = useState("");
  const [sendingReply, setSendingReply] = useState(false);

  // Memorizar o HTML sanitizado
  const sanitizedBodyHtml = useMemo(() => {
    if (currentEmail?.body_html) {
      return sanitizeEmailHtml(currentEmail.body_html);
    }
    return '';
  }, [currentEmail?.body_html]);

  useEffect(() => {
    if (selectedEmailId && emails.length > 0) {
      const index = emails.findIndex(e => e.id === selectedEmailId);
      if (index !== -1) {
        setCurrentIndex(index);
        setCurrentEmail(emails[index]);
      }
    }
  }, [selectedEmailId, emails]);

  const handleSelectEmail = (email, index) => {
    setCurrentEmail(email);
    setCurrentIndex(index);
    if (onSelectEmail) {
      onSelectEmail(email.id);
    }
    setShowReplyBox(false);
  };

  const handlePrevious = () => {
    if (currentIndex > 0) {
      const newIndex = currentIndex - 1;
      handleSelectEmail(emails[newIndex], newIndex);
    }
  };

  const handleNext = () => {
    if (currentIndex < emails.length - 1) {
      const newIndex = currentIndex + 1;
      handleSelectEmail(emails[newIndex], newIndex);
    }
  };

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (!isOpen) return;
      if (e.key === 'ArrowLeft') {
        handlePrevious();
      } else if (e.key === 'ArrowRight') {
        handleNext();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, currentIndex]);

  // Download de anexo
  const downloadAttachment = async (attachment) => {
    try {
      if (attachment.url) {
        window.open(attachment.url, '_blank');
        return;
      }
      
      const response = await fetch(
        `${API_URL}/api/emails/${currentEmail.id}/attachments/${attachment.id}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = attachment.filename;
        a.click();
        window.URL.revokeObjectURL(url);
      }
    } catch (error) {
      console.error("Erro ao descarregar anexo:", error);
    }
  };

  // Preview de anexo
  const previewAttachment = async (attachment) => {
    const contentType = attachment.content_type || "";
    
    // Imagens e PDFs podem ter preview
    if (contentType.includes("image") || contentType.includes("pdf")) {
      if (attachment.preview_url) {
        window.open(attachment.preview_url, '_blank');
        return;
      }
      
      try {
        const response = await fetch(
          `${API_URL}/api/emails/${currentEmail.id}/attachments/${attachment.id}/preview`,
          { headers: { Authorization: `Bearer ${token}` } }
        );
        
        if (response.ok) {
          const data = await response.json();
          if (data.preview_url) {
            window.open(data.preview_url, '_blank');
          }
        }
      } catch (error) {
        console.error("Preview não disponível");
      }
    }
    
    // Para outros tipos, fazer download
    downloadAttachment(attachment);
  };

  // Resposta rápida
  const handleReply = () => {
    const originalSubject = currentEmail?.subject || "";
    setReplySubject(originalSubject.startsWith("RE:") ? originalSubject : `RE: ${originalSubject}`);
    setReplyBody("");
    setShowReplyBox(true);
  };

  const sendReply = async () => {
    if (!replyBody.trim()) return;

    setSendingReply(true);
    try {
      const response = await fetch(`${API_URL}/api/emails/send?account=personal`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          to_emails: [currentEmail.from_email],
          subject: replySubject,
          body: replyBody,
          process_id: currentEmail.process_id,
          from_box: "personal"
        })
      });

      if (!response.ok) {
        // Preservar a mensagem útil do backend (ex.: 403 "Configuração de
        // email pessoal não encontrada. Vá ao seu Perfil > Configuração de
        // Webmail para configurar o seu email antes de enviar.").
        let detail = "Erro ao enviar resposta";
        try {
          const errData = await response.json();
          detail = errData.detail || errData.message || errData.error || detail;
        } catch (_) {
          /* resposta sem corpo JSON — manter mensagem genérica */
        }
        throw new Error(detail);
      }

      toast.success("Resposta enviada com sucesso");
      setShowReplyBox(false);
      // TODO: Actualizar lista de emails
    } catch (error) {
      console.error("Erro ao enviar resposta:", error);
      toast.error(error.message || "Erro ao enviar resposta", { duration: 8000 });
    } finally {
      setSendingReply(false);
    }
  };

  if (!currentEmail) return null;

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-6xl h-[100vh] sm:h-[85vh] sm:max-w-6xl sm:rounded-lg p-0 gap-0 overflow-hidden">
        <VisuallyHidden>
          <DialogTitle>Visualização de Email</DialogTitle>
          <DialogDescription>{currentEmail?.subject || "Email"}</DialogDescription>
        </VisuallyHidden>
        
        <div className="flex h-full">
          {/* Lista de emails - lado esquerdo */}
          <div className="w-72 border-r bg-muted/30 flex flex-col shrink-0">
            <div className="p-3 border-b bg-background">
              <h3 className="font-semibold text-sm flex items-center gap-2">
                <Mail className="h-4 w-4" />
                Emails ({emails.length})
              </h3>
            </div>
            <ScrollArea className="flex-1">
              <div className="p-2 space-y-1">
                {emails.map((email, index) => (
                  <div
                    key={email.id}
                    onClick={() => handleSelectEmail(email, index)}
                    className={`p-2 rounded cursor-pointer transition-colors ${
                      currentEmail?.id === email.id 
                        ? "bg-primary/10 border border-primary/30" 
                        : "hover:bg-muted"
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <div className={`mt-0.5 p-1 rounded shrink-0 ${
                        email.direction === "sent" 
                          ? "bg-blue-100 text-blue-600 dark:bg-blue-900/50 dark:text-blue-300" 
                          : "bg-emerald-100 text-emerald-600 dark:bg-emerald-900/50 dark:text-emerald-300"
                      }`}>
                        {email.direction === "sent" ? (
                          <Send className="h-3 w-3" />
                        ) : (
                          <Inbox className="h-3 w-3" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1">
                          <p className={`text-xs truncate flex-1 ${!email.is_read ? "font-semibold" : ""}`}>
                            {email.subject}
                          </p>
                          {email.is_important && <AlertCircle className="h-3 w-3 text-amber-500 shrink-0" />}
                          {email.is_starred && <Star className="h-3 w-3 text-amber-500 fill-amber-500 shrink-0" />}
                        </div>
                        <p className="text-[10px] text-muted-foreground truncate">
                          {email.direction === "sent" ? email.to_emails?.[0] : email.from_email}
                        </p>
                        <div className="flex items-center gap-1 mt-0.5">
                          <span className="text-[10px] text-muted-foreground">
                            {email.sent_at && safeFormat(email.sent_at, "dd/MM/yy HH:mm")}
                          </span>
                          {email.attachments?.length > 0 && (
                            <Paperclip className="h-3 w-3 text-muted-foreground" />
                          )}
                          {!email.is_read && (
                            <div className="h-2 w-2 rounded-full bg-amber-500" />
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </div>

          {/* Conteúdo do email - lado direito */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Barra de navegação com breadcrumb de contexto */}
            <div className="px-3 py-1.5 border-b bg-muted/30 shrink-0">
              {/* Breadcrumb de contexto */}
              {clientName && (
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
                  <Mail className="h-3 w-3" />
                  <span>Processo: {clientName}</span>
                  <ChevronLeft className="h-3 w-3 rotate-180" />
                  <span className="text-foreground font-medium truncate">
                    {currentEmail?.subject || "Email"}
                  </span>
                </div>
              )}
            </div>

            {/* Header com navegação prev/next */}
            <div className="px-3 py-2 border-b flex items-center justify-between bg-background shrink-0">
              <div className="flex items-center gap-2">
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={handlePrevious}
                  disabled={currentIndex === 0}
                  className="h-8"
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <span className="text-sm text-muted-foreground px-2">
                  {currentIndex + 1} de {emails.length}
                </span>
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={handleNext}
                  disabled={currentIndex === emails.length - 1}
                  className="h-8"
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
              
              <div className="flex items-center gap-1">
                {/* Marcações rápidas */}
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => currentEmail.is_important 
                    ? onUnmarkEmail?.(currentEmail.id, "important")
                    : onMarkEmail?.(currentEmail.id, "important")
                  }
                  title={currentEmail.is_important ? "Remover importante" : "Marcar importante"}
                >
                  <AlertCircle className={`h-4 w-4 ${currentEmail.is_important ? "text-amber-500" : ""}`} />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => currentEmail.is_starred 
                    ? onUnmarkEmail?.(currentEmail.id, "starred")
                    : onMarkEmail?.(currentEmail.id, "starred")
                  }
                  title={currentEmail.is_starred ? "Remover estrela" : "Marcar estrela"}
                >
                  {currentEmail.is_starred ? (
                    <Star className="h-4 w-4 text-amber-500 fill-amber-500" />
                  ) : (
                    <Star className="h-4 w-4" />
                  )}
                </Button>
                
                {/* Menu de ações */}
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon">
                      <MoreVertical className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {!currentEmail.is_read ? (
                      <DropdownMenuItem onClick={() => onMarkEmail?.(currentEmail.id, "read")}>
                        <CheckCircle className="h-4 w-4 mr-2" /> Marcar lido
                      </DropdownMenuItem>
                    ) : (
                      <DropdownMenuItem onClick={() => onMarkEmail?.(currentEmail.id, "unread")}>
                        <EyeOff className="h-4 w-4 mr-2" /> Marcar não lido
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={handleReply}>
                      <Reply className="h-4 w-4 mr-2" /> Responder
                    </DropdownMenuItem>
                    <DropdownMenuItem>
                      <Forward className="h-4 w-4 mr-2" /> Encaminhar
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={() => onMarkEmail?.(currentEmail.id, "archived")}>
                      <Archive className="h-4 w-4 mr-2" /> Arquivar
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
                
                <Button variant="ghost" size="icon" onClick={onClose}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {/* Detalhes do email */}
            <div className="p-4 border-b bg-muted/20 shrink-0">
              <div className="flex items-start gap-3">
                <div className={`p-2 rounded-full shrink-0 ${
                  currentEmail.direction === "sent" 
                    ? "bg-blue-100 text-blue-600 dark:bg-blue-900/50 dark:text-blue-300" 
                    : "bg-emerald-100 text-emerald-600 dark:bg-emerald-900/50 dark:text-emerald-300"
                }`}>
                  {currentEmail.direction === "sent" ? (
                    <Send className="h-5 w-5" />
                  ) : (
                    <Inbox className="h-5 w-5" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <h2 className="font-semibold text-lg break-words">
                      {currentEmail.subject}
                    </h2>
                    <div className="flex items-center gap-1 shrink-0">
                      {currentEmail.is_important && (
                        <Badge variant="outline" className="bg-amber-100 text-amber-700 border-amber-300 text-xs">
                          <AlertCircle className="h-3 w-3 mr-1" /> Importante
                        </Badge>
                      )}
                      <Badge variant={currentEmail.direction === "sent" ? "default" : "secondary"}>
                        {currentEmail.direction === "sent" ? "Enviado" : "Recebido"}
                      </Badge>
                    </div>
                  </div>
                  <div className="mt-2 space-y-1 text-sm">
                    <div className="flex items-center gap-2">
                      <User className="h-4 w-4 text-muted-foreground shrink-0" />
                      <span className="text-muted-foreground w-8">De:</span>
                      <span className="font-medium break-all">{currentEmail.from_email}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Mail className="h-4 w-4 text-muted-foreground shrink-0" />
                      <span className="text-muted-foreground w-8">Para:</span>
                      <span className="break-all">{currentEmail.to_emails?.join(", ")}</span>
                    </div>
                    {currentEmail.cc_emails?.length > 0 && (
                      <div className="flex items-center gap-2">
                        <Copy className="h-4 w-4 text-amber-500 shrink-0" />
                        <span className="text-amber-600 w-8 font-medium">CC:</span>
                        <span className="break-all text-amber-600">{currentEmail.cc_emails.join(", ")}</span>
                      </div>
                    )}
                    <div className="flex items-center gap-2">
                      <Clock className="h-4 w-4 text-muted-foreground shrink-0" />
                      <span className="text-muted-foreground w-8">Data:</span>
                      <span>
                        {currentEmail.sent_at 
                          ? safeFormat(currentEmail.sent_at, "EEEE, dd 'de' MMMM 'de' yyyy 'às' HH:mm", { locale: pt })
                          : "-"
                        }
                      </span>
                    </div>
                  </div>
                  {currentEmail.account && (
                    <Badge variant="outline" className="mt-2 text-xs">
                      {currentEmail.account === "precision" ? "Precision Crédito" : "Power Real Estate"}
                    </Badge>
                  )}
                </div>
              </div>
            </div>

            {/* Corpo do email */}
            <ScrollArea className="flex-1 p-4">
              <div className="prose prose-sm max-w-none dark:prose-invert">
                {sanitizedBodyHtml ? (
                  <div 
                    dangerouslySetInnerHTML={{ __html: sanitizedBodyHtml }}
                    className="email-content"
                  />
                ) : (
                  <pre className="whitespace-pre-wrap font-sans text-sm">
                    {currentEmail.body}
                  </pre>
                )}
              </div>

              {/* Anexos */}
              {currentEmail.attachments?.length > 0 && (
                <div className="mt-6 pt-4 border-t">
                  <h4 className="font-medium text-sm flex items-center gap-2 mb-3">
                    <Paperclip className="h-4 w-4" />
                    Anexos ({currentEmail.attachments.length})
                  </h4>
                  <div className="grid gap-2">
                    {currentEmail.attachments.map((attachment, idx) => {
                      const AttachmentIcon = getAttachmentIcon(attachment.content_type);
                      const isPreviewable = attachment.content_type?.includes("image") || 
                                           attachment.content_type?.includes("pdf");
                      
                      return (
                        <div
                          key={attachment.id || idx}
                          className="flex items-center gap-3 p-3 rounded-lg border bg-muted/30 hover:bg-muted/50 transition-colors"
                        >
                          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 shrink-0">
                            <AttachmentIcon className="h-5 w-5 text-primary" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="font-medium text-sm truncate" title={attachment.filename}>
                              {attachment.filename}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {formatFileSize(attachment.size)}
                              {attachment.content_type && ` • ${attachment.content_type}`}
                            </p>
                          </div>
                          <div className="flex items-center gap-1 shrink-0">
                            {isPreviewable && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => previewAttachment(attachment)}
                                title="Preview"
                              >
                                <Eye className="h-4 w-4" />
                              </Button>
                            )}
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => downloadAttachment(attachment)}
                              title="Download"
                            >
                              <Download className="h-4 w-4" />
                            </Button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </ScrollArea>

            {/* Caixa de resposta */}
            {showReplyBox && (
              <div className="border-t p-4 bg-muted/30 shrink-0">
                <div className="space-y-3">
                  <div>
                    <Label className="text-xs">Assunto</Label>
                    <Input
                      value={replySubject}
                      onChange={(e) => setReplySubject(e.target.value)}
                      className="h-8 mt-1"
                    />
                  </div>
                  <div>
                    <Label className="text-xs">Resposta</Label>
                    <Textarea
                      value={replyBody}
                      onChange={(e) => setReplyBody(e.target.value)}
                      placeholder="Escreva a sua resposta..."
                      rows={4}
                      className="mt-1"
                    />
                  </div>
                  <div className="flex justify-end gap-2">
                    <Button variant="outline" size="sm" onClick={() => setShowReplyBox(false)}>
                      Cancelar
                    </Button>
                    <Button size="sm" onClick={sendReply} disabled={sendingReply}>
                      {sendingReply ? (
                        <span className="flex items-center gap-1">
                          <span className="animate-spin">⏳</span> A enviar...
                        </span>
                      ) : (
                        <span className="flex items-center gap-1">
                          <Send className="h-4 w-4" /> Enviar
                        </span>
                      )}
                    </Button>
                  </div>
                </div>
              </div>
            )}

            {/* Footer com notas e ações */}
            <div className="border-t bg-muted/30 shrink-0">
              {currentEmail.notes && (
                <div className="p-3 border-b">
                  <p className="text-xs text-muted-foreground">
                    <strong>Notas:</strong> {currentEmail.notes}
                  </p>
                </div>
              )}
              <div className="p-3 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {currentEmail.labels?.length > 0 && (
                    <div className="flex items-center gap-1">
                      {currentEmail.labels.map((label, idx) => (
                        <Badge key={idx} variant="outline" className="text-xs">
                          <Tag className="h-3 w-3 mr-1" />
                          {label}
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {!showReplyBox && (
                    <Button size="sm" onClick={handleReply}>
                      <Reply className="h-4 w-4 mr-1" /> Responder
                    </Button>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default EmailViewerModal;
