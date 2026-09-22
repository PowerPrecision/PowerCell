/**
 * Coluna 3 do Webmail — leitura da mensagem seleccionada.
 *
 * Extraído de `pages/WebmailPage.jsx` (Épico 6). Componente de
 * APRESENTAÇÃO: recebe o email já carregado e o HTML JÁ sanitizado, e
 * devolve intenções pelos callbacks. Não busca nada, não sanitiza nada e
 * não conhece o router — o `href` do "Novo Separador" e a navegação para o
 * processo são decididos pelo contentor.
 *
 * O corpo do email vive num `<iframe sandbox>` com o HTML sanitizado a
 * montante (`utils/sanitize`): é conteúdo de terceiros e não pode correr
 * no nosso contexto. Não trocar por `dangerouslySetInnerHTML`.
 *
 * REQUISITO: tem de ser montado dentro de um `<TooltipProvider>` (a página
 * envolve tudo num). Sem ele, os `Tooltip` das acções rebentam.
 */
import {
  ExternalLink,
  FileText,
  FolderInput,
  Forward,
  Link2,
  Loader2,
  Mail,
  MailOpen,
  Paperclip,
  Reply,
  ReplyAll,
  Star,
  Trash2,
} from "lucide-react";

import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { ScrollArea } from "../ui/scroll-area";
import { Separator } from "../ui/separator";
import { Skeleton } from "../ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";
import { safeString } from "../../utils/safeString";
import { formatFileSize, formatFullDate, getAttachmentIcon } from "./webmailFormatters";

/**
 * @param {object} props
 * @param {object|null} props.email Detalhe já carregado (null = nada seleccionado).
 * @param {boolean} [props.loading]
 * @param {string} [props.sanitizedBodyHtml] HTML já sanitizado; vazio cai no texto simples.
 * @param {number} [props.replyAllRecipientCount] "Responder a Todos" só aparece acima de 1.
 * @param {string|null} [props.downloadingAttachmentId]
 * @param {() => void} props.onReply
 * @param {() => void} props.onReplyAll
 * @param {() => void} props.onForward
 * @param {() => void} props.onToggleRead
 * @param {(e: Event) => void} props.onToggleStar
 * @param {() => void} props.onLinkToProcess
 * @param {() => void} props.onMoveToFolder
 * @param {() => void} props.onDelete
 * @param {() => void} props.onOpenProcess
 * @param {() => void} props.onOpenInNewTab
 * @param {(attachment: object, index: number) => void} props.onDownloadAttachment
 */
const EmailThreadViewer = ({
  email,
  loading = false,
  sanitizedBodyHtml = "",
  replyAllRecipientCount = 0,
  downloadingAttachmentId = null,
  onReply,
  onReplyAll,
  onForward,
  onToggleRead,
  onToggleStar,
  onLinkToProcess,
  onMoveToFolder,
  onDelete,
  onOpenProcess,
  onOpenInNewTab,
  onDownloadAttachment,
}) => {
  return (
    <div
      className="h-full flex flex-col bg-background overflow-hidden"
      data-testid="webmail-reading-pane"
    >
      {loading ? (
        // Loading skeleton
        <div className="flex-1 p-5 space-y-4">
          <Skeleton className="h-7 w-[70%]" />
          <div className="space-y-2">
            <Skeleton className="h-4 w-[200px]" />
            <Skeleton className="h-4 w-[250px]" />
            <Skeleton className="h-4 w-[150px]" />
          </div>
          <Separator />
          <div className="space-y-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-4 w-full" />
            ))}
            <Skeleton className="h-4 w-[80%]" />
            <Skeleton className="h-4 w-[60%]" />
          </div>
        </div>
      ) : email ? (
        /* ===== EMAIL DETAIL ===== */
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Header */}
          <div className="px-5 py-4 border-b shrink-0">
            {/* Subject */}
            <h2 className="text-lg font-semibold leading-snug break-words">
              {safeString(email.subject, "(Sem assunto)")}
            </h2>

            {/* Meta info */}
            <div className="mt-2 space-y-1.5 text-sm">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-muted-foreground shrink-0">De:</span>
                <span className="font-medium truncate">
                  {safeString(email.from_email, "-")}
                </span>
              </div>
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-muted-foreground shrink-0">Para:</span>
                <span className="truncate">
                  {email.to_emails?.join(", ") || "-"}
                </span>
              </div>
              {email.cc_emails?.length > 0 && (
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-muted-foreground shrink-0">CC:</span>
                  <span className="truncate">
                    {email.cc_emails.join(", ")}
                  </span>
                </div>
              )}
              <div className="flex items-center gap-2 text-muted-foreground">
                <span>Data:</span>
                <span>{formatFullDate(email.sent_at)}</span>
              </div>
              {/* Label badges on detail */}
              {email.labels?.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap pt-1">
                  {email.labels.map((lbl) => (
                    <span
                      key={lbl.id || lbl.name}
                      className="rounded-full px-2 py-0.5 text-white leading-none"
                      style={{
                        backgroundColor: lbl.color || "#6b7280",
                        fontSize: "11px",
                      }}
                    >
                      {safeString(lbl.name)}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Action buttons */}
            <div className="flex items-center gap-1.5 mt-3 flex-wrap">
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs gap-1.5"
                onClick={() => onReply()}
              >
                <Reply className="h-3.5 w-3.5" />
                Responder
              </Button>
              {/* "Responder a Todos" só faz sentido quando há mais
                  alguém na conversa além de nós e do remetente. */}
              {replyAllRecipientCount > 1 && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 text-xs gap-1.5"
                  onClick={() => onReplyAll()}
                >
                  <ReplyAll className="h-3.5 w-3.5" />
                  Responder a Todos
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs gap-1.5"
                onClick={() => onForward()}
              >
                <Forward className="h-3.5 w-3.5" />
                Encaminhar
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs gap-1.5"
                onClick={() => onToggleRead()}
              >
                {email.is_read === false ? (
                  <><MailOpen className="h-3.5 w-3.5" />Marcar como lida</>
                ) : (
                  <><Mail className="h-3.5 w-3.5" />Marcar como não lida</>
                )}
              </Button>
              {/* PACOTE 8 — abrir a visualização do email num novo separador */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-8 text-xs gap-1.5"
                    onClick={onOpenInNewTab}
                    aria-label="Abrir email num novo separador"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                    Novo Separador
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Abrir email num novo separador</TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    className={`h-8 w-8 p-0 ${
                      email.is_starred
                        ? "text-amber-500"
                        : "text-muted-foreground"
                    }`}
                    onClick={(e) => onToggleStar(e)}
                  >
                    <Star
                      className={`h-3.5 w-3.5 ${
                        email.is_starred ? "fill-amber-500" : ""
                      }`}
                    />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  {email.is_starred ? "Remover destaque" : "Destacar"}
                </TooltipContent>
              </Tooltip>
              {email.process_id ? (
                <Badge
                  variant="secondary"
                  className="h-8 text-xs gap-1.5 cursor-pointer hover:bg-accent"
                  onClick={() => onOpenProcess()}
                >
                  <Link2 className="h-3.5 w-3.5" />
                  {safeString(email.client_name) || safeString(email.process_id)} Associado
                </Badge>
              ) : (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 text-xs gap-1.5"
                      onClick={onLinkToProcess}
                    >
                      <Link2 className="h-3.5 w-3.5" />
                      Ligar a Processo
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Ligar a Processo</TooltipContent>
                </Tooltip>
              )}
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => onMoveToFolder()}
                    className="p-1.5 rounded-md hover:bg-accent/50 text-muted-foreground hover:text-foreground transition-colors"
                    title="Mover para pasta"
                  >
                    <FolderInput className="h-4 w-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent>Mover para pasta</TooltipContent>
              </Tooltip>
              {email.process_id && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 text-xs gap-1.5"
                  onClick={() => onOpenProcess()}
                >
                  <FileText className="h-3.5 w-3.5" />
                  Ver Processo
                </Button>
              )}
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-8 w-8 p-0 text-destructive hover:text-destructive hover:bg-destructive/10"
                    onClick={onDelete}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Eliminar email</TooltipContent>
              </Tooltip>
            </div>
          </div>

          {/* Body */}
          <ScrollArea className="flex-1">
            <div className="p-5">
              {sanitizedBodyHtml ? (
                <iframe
                  srcDoc={sanitizedBodyHtml}
                  className="w-full border-0 rounded-md"
                  style={{ minHeight: "200px", maxHeight: "600px" }}
                  title="Email content"
                  sandbox="allow-same-origin"
                  onLoad={(e) => {
                    const doc = e.target.contentDocument;
                    if (doc) {
                      const h = doc.body?.scrollHeight || 200;
                      e.target.style.height = Math.min(h + 20, 600) + "px";
                    }
                  }}
                />
              ) : (
                <pre className="whitespace-pre-wrap font-sans text-sm">
                  {email.body || ""}
                </pre>
              )}

              {/* Attachments - Visual Cards */}
              {email.attachments?.length > 0 && (
                <div className="mt-6 pt-4 border-t">
                  <h4 className="font-medium text-sm flex items-center gap-2 mb-3">
                    <Paperclip className="h-4 w-4" />
                    Anexos ({email.attachments.length})
                  </h4>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {email.attachments.map((attachment, idx) => {
                      const AttIcon = getAttachmentIcon(attachment.filename);
                      return (
                        <div
                          key={attachment.id || idx}
                          className="flex items-center gap-3 p-3 rounded-lg border bg-muted/20 hover:bg-muted/40 transition-colors group"
                        >
                          <div className="h-9 w-9 rounded-md bg-muted flex items-center justify-center shrink-0">
                            <AttIcon className="h-4 w-4 text-muted-foreground" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium truncate">
                              {attachment.filename || attachment.file_name || `Anexo ${idx + 1}`}
                            </p>
                            {(attachment.size || attachment.file_size) && (
                              <p className="text-xs text-muted-foreground mt-0.5">
                                {formatFileSize(attachment.size || attachment.file_size)}
                              </p>
                            )}
                          </div>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                type="button"
                                variant="outline"
                                size="icon"
                                className="h-8 w-8 shrink-0"
                                disabled={downloadingAttachmentId === (attachment.id || `${email.id}:${idx}`)}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onDownloadAttachment(attachment, idx);
                                }}
                                aria-label={`Abrir ${attachment.filename || "anexo"} num novo separador`}
                              >
                                {downloadingAttachmentId === (attachment.id || `${email.id}:${idx}`) ? (
                                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                ) : (
                                  <ExternalLink className="h-3.5 w-3.5" />
                                )}
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>Abrir num novo separador</TooltipContent>
                          </Tooltip>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          </ScrollArea>
        </div>
      ) : (
        /* ===== EMPTY STATE ===== */
        <div className="flex-1 flex flex-col items-center justify-center text-center p-6">
          <Mail className="h-14 w-14 text-muted-foreground opacity-30 mb-4" />
          <p className="text-muted-foreground text-sm">
            Selecione um email para visualizar
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            Clique num email da lista à esquerda
          </p>
        </div>
      )}
    </div>  );
};

export default EmailThreadViewer;
