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
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "./ui/dialog";
import { VisuallyHidden } from "@radix-ui/react-visually-hidden";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { ScrollArea } from "./ui/scroll-area";
import {
  downloadEmailAttachment,
  getEmailAttachmentPreview,
  archiveEmailAttachment,
} from "../services/api";
import { useAuthOpcional } from "../contexts/AuthContext";
import { CATEGORIA_POR_OMISSAO, erroDoArquivo, mensagemDoArquivo, podeArquivarAnexos } from "../utils/emailArchive";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import { 
  Mail, Send, Inbox, Clock, X, ChevronLeft, ChevronRight,
  Paperclip, User, Star,
  AlertCircle, CheckCircle, Download, Eye, EyeOff, Reply,
  ReplyAll, Archive, MoreVertical, Image, FileText, FileSpreadsheet, Copy, Tag, Loader2, FolderInput
} from "lucide-react";
import { pt } from "date-fns/locale";
import { sanitizeEmailHtml } from "../utils/sanitize";
import { safeFormat } from "../lib/utils";
import { toast } from "sonner";

// PACOTE 11 (Eixo 2) — converte o corpo em TEXTO SIMPLES num fragmento
// HTML sanitizado com parágrafos reais: o <pre> denso passa a ter a mesma
// tipografia espaçada do corpo HTML (parágrafos com margens, quebras
// preservadas, sem monospace nem bloco denso).
const escapeHtml = (text) =>
  String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

const buildPlainTextEmailHtml = (body) => {
  if (!body) return "";
  const blocks = String(body)
    .split(/\n\s*\n/)
    .map((block) => block.replace(/\r/g, "").trim())
    .filter(Boolean);
  if (blocks.length === 0) return "";
  return blocks
    .map((block) => `<p>${escapeHtml(block).replace(/\n/g, "<br/>")}</p>`)
    .join("");
};

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
  processId = null,
  // Sem `onReply` (ex.: Index, que só consulta) não há botões de responder.
  onReply = null,
}) => {
  const auth = useAuthOpcional();
  // «Guardar nos Documentos do Processo»: só no contexto de um processo e para quem trata documentos
  // (o servidor repete a regra: perfil, âmbito e processo aberto).
  const podeGuardarAnexos = Boolean(processId) && Boolean(auth) && podeArquivarAnexos(auth.effectiveRole);
  const [aGuardar, setAGuardar] = useState(null);
  const [currentEmail, setCurrentEmail] = useState(null);
  const [currentIndex, setCurrentIndex] = useState(0);


  // Memorizar o HTML sanitizado (PACOTE 11 — o corpo em texto simples é
  // convertido em parágrafos HTML para tipografia consistente e espaçada)
  const sanitizedBodyHtml = useMemo(() => {
    if (currentEmail?.body_html) {
      return sanitizeEmailHtml(currentEmail.body_html);
    }
    return buildPlainTextEmailHtml(currentEmail?.body);
  }, [currentEmail?.body_html, currentEmail?.body]);

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
      
      // Pelo Axios (com `X-Company-Id`/`X-Active-Role`): o servidor decide se este
      // utilizador pode ler o email pelo perfil activo.
      const { data: blob } = await downloadEmailAttachment(currentEmail.id, attachment.id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = attachment.filename;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Erro ao descarregar anexo:", error);
      toast.error("Não foi possível descarregar o anexo.");
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
        const { data } = await getEmailAttachmentPreview(currentEmail.id, attachment.id);
        if (data?.preview_url) {
          window.open(data.preview_url, '_blank');
        }
      } catch {
        console.error("Preview não disponível");
      }
    }
    
    // Para outros tipos, fazer download
    downloadAttachment(attachment);
  };

  // Responder (pergunta 10a): abre o compositor do Webmail — com a conversa
  // (In-Reply-To), Cc, anexos e assinatura. A caixa pequena que existia aqui partia
  // o fio e respondia ao próprio remetente quando o email tinha sido enviado por nós.
  const handleReply = (modo = "reply") => {
    if (!currentEmail || !onReply) return;
    onReply(modo, currentEmail);
  };

  // Envia o anexo directamente para a pasta do processo aberto (o mesmo caminho do «Arquivar no
  // Processo» do Webmail: validação, Index/IA, histórico e pedido do Portal), sem o descarregar.
  const guardarNosDocumentos = async (attachment, idx) => {
    const idDoAnexo = attachment.id || `${currentEmail.id}:${idx}`;
    setAGuardar(idDoAnexo);
    try {
      const { data } = await archiveEmailAttachment(currentEmail.id, idDoAnexo, {
        process_id: processId,
        category: CATEGORIA_POR_OMISSAO,
      });
      toast.success(mensagemDoArquivo(data));
    } catch (erro) {
      toast.error(erroDoArquivo(erro));
    } finally {
      setAGuardar(null);
    }
  };

  if (!currentEmail) return null;

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      {/* O DialogContent é uma GRELHA de uma linha `auto`: a linha cresce até ao tamanho do conteúdo
            (o `min-height: auto` do filho) e o corpo do email nunca transborda — o scroll
            "desaparecia" mesmo com `overflow-y-auto` no sítio certo. `minmax(0,1fr)` prende a linha à
            altura do diálogo (QA-9). */}
      <DialogContent className="max-w-6xl h-[100vh] sm:h-[85vh] sm:max-w-6xl sm:rounded-lg p-0 gap-0 overflow-hidden grid-rows-[minmax(0,1fr)]">
        <VisuallyHidden>
          <DialogTitle>Visualização de Email</DialogTitle>
          <DialogDescription>{currentEmail?.subject || "Email"}</DialogDescription>
        </VisuallyHidden>
        
        <div className="flex h-full min-h-0">
          {/* Lista de emails - lado esquerdo */}
          <div className="hidden sm:flex w-72 border-r bg-muted/30 flex-col shrink-0">
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
                          ? "bg-primary/10 text-primary" 
                          : "bg-muted text-muted-foreground"
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
                          {email.is_important && <AlertCircle className="h-3 w-3 text-primary shrink-0" />}
                          {email.is_starred && <Star className="h-3 w-3 text-primary fill-primary shrink-0" />}
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
                            <div className="h-2 w-2 rounded-full bg-primary" />
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
          <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
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
                  <AlertCircle className={`h-4 w-4 ${currentEmail.is_important ? "text-primary" : ""}`} />
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
                    <Star className="h-4 w-4 text-primary fill-primary" />
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
                    {onReply && (
                      <>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem onClick={() => handleReply("reply")}>
                          <Reply className="h-4 w-4 mr-2" /> Responder
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => handleReply("reply_all")}>
                          <ReplyAll className="h-4 w-4 mr-2" /> Responder a todos
                        </DropdownMenuItem>
                      </>
                    )}
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
                    ? "bg-primary/10 text-primary" 
                    : "bg-muted text-muted-foreground"
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
                        <Badge variant="outline" className="bg-accent text-accent-foreground border-border text-xs">
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
                        <Copy className="h-4 w-4 text-primary shrink-0" />
                        <span className="text-primary w-8 font-medium">CC:</span>
                        <span className="break-all text-primary">{currentEmail.cc_emails.join(", ")}</span>
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

            {/* Corpo do email — PACOTE 11 (Eixo 2): tipografia prose com
                margens/interlinha confortáveis (ver .email-content no
                index.css); texto simples é renderizado como parágrafos. */}
            {/* Contentor nativo, não `ScrollArea`: o Radix corta a Root e o viewport nunca transborda
                (FRONTEND_GUIDELINES § 27.14) — um email comprido ficava cortado e ilegível. */}
            <div className="flex-1 min-h-0 overflow-y-auto p-4" data-testid="corpo-do-email">
              <div className="prose prose-sm max-w-none dark:prose-invert">
                {sanitizedBodyHtml ? (
                  <div
                    dangerouslySetInnerHTML={{ __html: sanitizedBodyHtml }}
                    className="email-content"
                  />
                ) : (
                  <p className="text-sm text-muted-foreground whitespace-pre-wrap break-words leading-relaxed">
                    {currentEmail.body || "(sem conteúdo)"}
                  </p>
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
                            {podeGuardarAnexos && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => guardarNosDocumentos(attachment, idx)}
                                disabled={aGuardar !== null}
                                title="Guardar nos Documentos do Processo"
                                aria-label={`Guardar ${attachment.filename} nos Documentos do Processo`}
                              >
                                {aGuardar === (attachment.id || `${currentEmail.id}:${idx}`)
                                  ? <Loader2 className="h-4 w-4 animate-spin" />
                                  : <FolderInput className="h-4 w-4" />}
                                <span className="hidden sm:inline ml-1 text-xs">Guardar no Processo</span>
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
            </div>

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
                  {onReply && (
                    <>
                      <Button size="sm" variant="outline" onClick={() => handleReply("reply_all")}>
                        <ReplyAll className="h-4 w-4 mr-1" /> Responder a todos
                      </Button>
                      <Button size="sm" onClick={() => handleReply("reply")}>
                        <Reply className="h-4 w-4 mr-1" /> Responder
                      </Button>
                    </>
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
