/**
 * Coluna 2 do Webmail — lista de conversas.
 *
 * Extraído de `pages/WebmailPage.jsx` (Épico 6). Componente de
 * APRESENTAÇÃO: não conhece a API, o React Query nem o WebSocket. Recebe as
 * conversas JÁ agrupadas (`groupEmailsIntoThreads`, que continua a correr no
 * contentor, onde vive o tempo real do Épico 5) e devolve intenções pelos
 * callbacks.
 *
 * O desenho dos dois botões irmãos — expandir a conversa e abrir a mensagem —
 * é deliberado: são acções distintas e um `<button>` não pode viver dentro de
 * outro. `__tests__/EmailList.test.jsx` tranca esse contrato.
 */
import {
  CheckSquare,
  ChevronDown,
  ChevronRight,
  MailOpen,
  Paperclip,
  Square,
  Star,
  X,
} from "lucide-react";

import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Skeleton } from "../ui/skeleton";
import { safeString } from "../../utils/safeString";
import { formatEmailDate } from "./webmailFormatters";

/** Set vazio partilhado — um literal novo por render invalidaria memos a jusante. */
const EMPTY_SET = new Set();

/** Nome a mostrar: destinatário nos enviados, remetente nos recebidos. */
const nomeVisivel = (email) =>
  email.direction === "sent"
    ? email.to_emails?.[0] || "Destinatário"
    : safeString(email.client_name) || safeString(email.from_email) || "Remetente";

/**
 * @param {object} props
 * @param {Array} props.threads Conversas já agrupadas por `groupEmailsIntoThreads`.
 * @param {boolean} [props.loading]
 * @param {string} [props.headerTitle] Nome da pasta/marcador activo.
 * @param {string} [props.emptyMessage] Texto do estado vazio (decidido pelo contentor).
 * @param {number} [props.totalEmails] Total da página — usado pelo "Selecionar tudo".
 * @param {string|null} [props.selectedEmailId]
 * @param {Set<string>} [props.selectedEmails]
 * @param {boolean} [props.multiSelectMode]
 * @param {Set<string>} [props.expandedThreads]
 * @param {number} [props.currentPage]
 * @param {number} [props.totalPages]
 * @param {(email: object) => void} props.onSelectEmail
 * @param {(threadKey: string) => void} props.onToggleThread
 * @param {() => void} [props.onSelectAll]
 * @param {(page: number) => void} [props.onPageChange]
 * @param {(() => void)|null} [props.onClearFolder] `null` se não há pasta personalizada activa.
 * @param {(() => void)|null} [props.onClearLabel] `null` se não há marcador activo.
 */
const EmailList = ({
  threads,
  loading = false,
  headerTitle = "",
  emptyMessage = "Sem emails nesta pasta",
  totalEmails = 0,
  selectedEmailId = null,
  selectedEmails = EMPTY_SET,
  multiSelectMode = false,
  expandedThreads = EMPTY_SET,
  currentPage = 1,
  totalPages = 1,
  onSelectEmail,
  onToggleThread,
  onSelectAll = () => {},
  onPageChange = () => {},
  onClearFolder = null,
  onClearLabel = null,
}) => {
  const tudoSeleccionado = selectedEmails.size === totalEmails && totalEmails > 0;

  return (
    <div
      className="h-full border-r border-border flex flex-col bg-background overflow-hidden"
      data-testid="webmail-list-pane"
    >
      {/* Cabeçalho da lista */}
      <div className="flex items-center justify-between px-3 py-2 border-b shrink-0">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold">{headerTitle}</h2>
          {/* Dois botões, não um: a pasta personalizada e o marcador PODEM
              estar activos ao mesmo tempo (escolher um marcador não limpa a
              pasta). Um só X obrigaria a dois cliques e limparia pela ordem
              errada — era uma mudança de comportamento disfarçada de
              refactor. */}
          {onClearFolder && (
            <button
              type="button"
              onClick={onClearFolder}
              aria-label="Limpar pasta"
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="h-3 w-3" />
            </button>
          )}
          {onClearLabel && (
            <button
              type="button"
              onClick={onClearLabel}
              aria-label="Limpar marcador"
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
        <div className="flex items-center gap-2">
          {multiSelectMode && (
            <button
              type="button"
              onClick={onSelectAll}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              {tudoSeleccionado ? "Desselecionar" : "Selecionar tudo"}
            </button>
          )}
          {totalPages > 1 && (
            <span className="text-xs text-muted-foreground">
              Página {currentPage} de {totalPages}
            </span>
          )}
        </div>
      </div>

      {/* Conversas */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="divide-y">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="p-3 space-y-2" data-testid="esqueleto-email">
                <div className="flex items-center gap-2">
                  <Skeleton className="h-3 w-3 rounded-full" />
                  <Skeleton className="h-4 w-[140px]" />
                  <Skeleton className="h-3 w-[40px] ml-auto" />
                </div>
                <Skeleton className="h-3.5 w-full" />
                <Skeleton className="h-3 w-[70%]" />
              </div>
            ))}
          </div>
        ) : threads.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center p-6">
            <MailOpen className="h-10 w-10 text-muted-foreground opacity-40 mb-3" />
            <p className="text-sm text-muted-foreground">{emptyMessage}</p>
          </div>
        ) : (
          <div className="divide-y">
            {threads.map((thread) => {
              const email = thread.latest;
              const isThread = thread.count > 1;
              const isExpanded = expandedThreads.has(thread.key);
              const isSelected = selectedEmailId === email.id;
              const isChecked = selectedEmails.has(email.id);

              return (
                <div key={thread.key}>
                  <div className="flex items-stretch">
                    {/* Expandir a conversa é uma acção SEPARADA de abrir a
                        mensagem — e um <button> não pode viver dentro de
                        outro <button>, daí os dois lado a lado. */}
                    {isThread && (
                      <button
                        type="button"
                        onClick={() => onToggleThread(thread.key)}
                        aria-expanded={isExpanded}
                        aria-label={
                          isExpanded
                            ? "Fechar conversa"
                            : `Expandir conversa com ${thread.count} mensagens`
                        }
                        className="px-1.5 shrink-0 text-muted-foreground hover:text-foreground hover:bg-accent/50 transition-colors"
                      >
                        {isExpanded ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                      </button>
                    )}
                    <button
                      type="button"
                      data-testid={`linha-email-${email.id}`}
                      aria-current={isSelected && !multiSelectMode ? "true" : undefined}
                      onClick={() => onSelectEmail(email)}
                      className={`
                        flex-1 min-w-0 text-left p-3 transition-colors hover:bg-accent/50
                        ${isSelected && !multiSelectMode ? "bg-accent" : ""}
                      `}
                    >
                      <div className="flex items-start gap-2">
                        {/* Caixa de selecção múltipla */}
                        {multiSelectMode && (
                          <span className="mt-1 shrink-0">
                            {isChecked ? (
                              <CheckSquare
                                className="h-4 w-4 text-primary"
                                data-testid={`caixa-seleccionada-${email.id}`}
                              />
                            ) : (
                              <Square className="h-4 w-4 text-muted-foreground" />
                            )}
                          </span>
                        )}

                        {/* Ponto de não lida */}
                        {!multiSelectMode && !email.is_read && (
                          <span
                            className="bg-primary w-2 h-2 rounded-full mt-1.5 shrink-0"
                            data-testid="indicador-nao-lida"
                          />
                        )}
                        {!multiSelectMode && email.is_read && (
                          <span className="w-2 shrink-0" />
                        )}

                        <div className="flex-1 min-w-0">
                          {/* Remetente + contagem + data */}
                          <div className="flex items-center gap-1.5">
                            <span
                              className={`text-sm truncate flex-1 ${
                                !email.is_read
                                  ? "font-semibold text-foreground"
                                  : "text-muted-foreground"
                              }`}
                            >
                              {nomeVisivel(email)}
                            </span>
                            {isThread && (
                              <Badge
                                variant="secondary"
                                className="h-4 text-[10px] px-1.5 py-0 shrink-0"
                                title={`${thread.count} mensagens nesta conversa`}
                              >
                                {thread.count}
                              </Badge>
                            )}
                            <span className="text-[11px] text-muted-foreground whitespace-nowrap shrink-0">
                              {formatEmailDate(email.sent_at)}
                            </span>
                          </div>

                          {/* Assunto */}
                          <p
                            className={`text-sm truncate mt-0.5 ${
                              !email.is_read ? "font-medium" : ""
                            }`}
                          >
                            {safeString(email.subject, "(Sem assunto)")}
                          </p>

                          {/* Pré-visualização + indicadores */}
                          <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                            <p className="text-xs text-muted-foreground truncate flex-1 min-w-0">
                              {safeString(email.preview)}
                            </p>
                            {email.labels?.length > 0 && (
                              <span className="flex items-center gap-1 shrink-0">
                                {email.labels.slice(0, 2).map((lbl) => (
                                  <span
                                    key={lbl.id || lbl.name}
                                    className="rounded-full px-1.5 py-0.5 text-white leading-none"
                                    style={{
                                      backgroundColor: lbl.color || "#6b7280",
                                      fontSize: "10px",
                                    }}
                                  >
                                    {safeString(lbl.name)}
                                  </span>
                                ))}
                                {email.labels.length > 2 && (
                                  <span
                                    className="rounded-full px-1.5 py-0.5 text-muted-foreground leading-none border"
                                    style={{ fontSize: "10px" }}
                                  >
                                    +{email.labels.length - 2}
                                  </span>
                                )}
                              </span>
                            )}
                            {email.is_starred && (
                              <Star
                                className="h-3 w-3 text-amber-500 fill-amber-500 shrink-0"
                                data-testid="indicador-destaque"
                              />
                            )}
                            {email.attachments?.length > 0 && (
                              <Paperclip
                                className="h-3 w-3 text-muted-foreground shrink-0"
                                data-testid="indicador-anexo"
                              />
                            )}
                            {email.process_id && (
                              <Badge
                                variant="outline"
                                className="h-4 text-[9px] px-1 py-0 shrink-0"
                              >
                                Proc.
                              </Badge>
                            )}
                          </div>
                        </div>
                      </div>
                    </button>
                  </div>

                  {/* Mensagens anteriores da conversa */}
                  {isThread && isExpanded && (
                    <div
                      className="divide-y border-l-2 border-border ml-4 bg-muted/30"
                      data-testid={`conversa-anteriores-${thread.key}`}
                    >
                      {thread.emails.slice(1).map((prev) => (
                        <button
                          type="button"
                          key={prev.id}
                          data-testid={`linha-email-${prev.id}`}
                          onClick={() => onSelectEmail(prev)}
                          className={`w-full text-left px-3 py-2 transition-colors hover:bg-accent/50 ${
                            selectedEmailId === prev.id && !multiSelectMode ? "bg-accent" : ""
                          }`}
                        >
                          <div className="flex items-center gap-1.5">
                            {!prev.is_read && (
                              <span className="bg-primary w-1.5 h-1.5 rounded-full shrink-0" />
                            )}
                            <span
                              className={`text-xs truncate flex-1 ${
                                !prev.is_read
                                  ? "font-semibold text-foreground"
                                  : "text-muted-foreground"
                              }`}
                            >
                              {nomeVisivel(prev)}
                            </span>
                            {prev.attachments?.length > 0 && (
                              <Paperclip className="h-3 w-3 text-muted-foreground shrink-0" />
                            )}
                            <span className="text-[10px] text-muted-foreground whitespace-nowrap shrink-0">
                              {formatEmailDate(prev.sent_at)}
                            </span>
                          </div>
                          <p className="text-xs text-muted-foreground truncate mt-0.5">
                            {safeString(prev.preview) || safeString(prev.subject, "(Sem assunto)")}
                          </p>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Paginação */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-3 py-2 border-t shrink-0">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            disabled={currentPage <= 1}
            onClick={() => onPageChange(currentPage - 1)}
          >
            Anterior
          </Button>
          <span className="text-xs text-muted-foreground">
            {currentPage} / {totalPages}
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            disabled={currentPage >= totalPages}
            onClick={() => onPageChange(currentPage + 1)}
          >
            Seguinte
          </Button>
        </div>
      )}
    </div>
  );
};

export default EmailList;
