/**
 * EmailViewerModal - Modal para visualização de emails
 * Mostra email selecionado com lista de emails ao lado para navegação
 */
import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "./ui/dialog";
import { VisuallyHidden } from "@radix-ui/react-visually-hidden";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { 
  Mail, Send, Inbox, Clock, X, ChevronLeft, ChevronRight,
  Paperclip, User
} from "lucide-react";
import { format, parseISO } from "date-fns";
import { pt } from "date-fns/locale";

const EmailViewerModal = ({ 
  isOpen, 
  onClose, 
  emails = [], 
  selectedEmailId,
  onSelectEmail 
}) => {
  const [currentEmail, setCurrentEmail] = useState(null);
  const [currentIndex, setCurrentIndex] = useState(0);

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

  if (!currentEmail) return null;

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-6xl h-[85vh] p-0 gap-0 overflow-hidden">
        {/* Título acessível mas visualmente oculto */}
        <VisuallyHidden>
          <DialogTitle>Visualização de Email</DialogTitle>
          <DialogDescription>
            {currentEmail?.subject || "Email selecionado"}
          </DialogDescription>
        </VisuallyHidden>
        
        <div className="flex h-full">
          {/* Lista de emails - lado esquerdo */}
          <div className="w-80 border-r bg-muted/30 flex flex-col">
            <div className="p-3 border-b bg-background">
              <h3 className="font-semibold text-sm flex items-center gap-2">
                <Mail className="h-4 w-4" />
                Emails ({emails.length})
              </h3>
            </div>
            <div className="flex-1 overflow-y-auto scrollbar-thin scrollbar-thumb-muted-foreground/30 scrollbar-track-transparent hover:scrollbar-thumb-muted-foreground/50">
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
                      <div className={`mt-0.5 p-1 rounded ${
                        email.direction === "sent" 
                          ? "bg-blue-100 text-blue-600" 
                          : "bg-emerald-100 text-emerald-600"
                      }`}>
                        {email.direction === "sent" ? (
                          <Send className="h-3 w-3" />
                        ) : (
                          <Inbox className="h-3 w-3" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium truncate" title={email.subject}>
                          {email.subject}
                        </p>
                        <p className="text-[10px] text-muted-foreground truncate">
                          {email.direction === "sent" ? email.to_emails?.[0] : email.from_email}
                        </p>
                        <p className="text-[10px] text-muted-foreground mt-0.5">
                          {email.sent_at && format(parseISO(email.sent_at), "dd/MM/yy HH:mm")}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Conteúdo do email - lado direito */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Header */}
            <div className="p-4 border-b flex items-center justify-between bg-background shrink-0">
              <div className="flex items-center gap-2">
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={handlePrevious}
                  disabled={currentIndex === 0}
                  className="h-8"
                >
                  <ChevronLeft className="h-4 w-4 mr-1" />
                  Anterior
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
                  Seguinte
                  <ChevronRight className="h-4 w-4 ml-1" />
                </Button>
              </div>
              <Button variant="ghost" size="icon" onClick={onClose}>
                <X className="h-4 w-4" />
              </Button>
            </div>

            {/* Detalhes do email */}
            <div className="p-4 border-b bg-muted/20">
              <div className="flex items-start gap-3">
                <div className={`p-2 rounded-full ${
                  currentEmail.direction === "sent" 
                    ? "bg-blue-100 text-blue-600" 
                    : "bg-emerald-100 text-emerald-600"
                }`}>
                  {currentEmail.direction === "sent" ? (
                    <Send className="h-5 w-5" />
                  ) : (
                    <Inbox className="h-5 w-5" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <h2 className="font-semibold text-lg break-words">
                    {currentEmail.subject}
                  </h2>
                  <div className="mt-2 space-y-1 text-sm">
                    <div className="flex items-center gap-2">
                      <span className="text-muted-foreground w-12">De:</span>
                      <span className="font-medium">{currentEmail.from_email}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-muted-foreground w-12">Para:</span>
                      <span className="break-all">{currentEmail.to_emails?.join(", ")}</span>
                    </div>
                    {currentEmail.cc_emails?.length > 0 && (
                      <div className="flex items-center gap-2">
                        <span className="text-muted-foreground w-12">CC:</span>
                        <span className="break-all">{currentEmail.cc_emails.join(", ")}</span>
                      </div>
                    )}
                    <div className="flex items-center gap-2">
                      <span className="text-muted-foreground w-12">Data:</span>
                      <span>
                        {currentEmail.sent_at 
                          ? format(parseISO(currentEmail.sent_at), "EEEE, dd 'de' MMMM 'de' yyyy 'às' HH:mm", { locale: pt })
                          : "-"
                        }
                      </span>
                    </div>
                  </div>
                  {currentEmail.attachments?.length > 0 && (
                    <div className="mt-2 flex items-center gap-2">
                      <Paperclip className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm text-muted-foreground">
                        {currentEmail.attachments.length} anexo(s)
                      </span>
                    </div>
                  )}
                </div>
                <Badge variant={currentEmail.direction === "sent" ? "default" : "secondary"}>
                  {currentEmail.direction === "sent" ? "Enviado" : "Recebido"}
                </Badge>
              </div>
            </div>

            {/* Corpo do email - com scroll visível */}
            <div className="flex-1 overflow-y-auto p-4 scrollbar-thin scrollbar-thumb-muted-foreground/30 scrollbar-track-transparent hover:scrollbar-thumb-muted-foreground/50">
              <div className="prose prose-sm max-w-none dark:prose-invert">
                {currentEmail.body_html ? (
                  <div 
                    dangerouslySetInnerHTML={{ __html: currentEmail.body_html }}
                    className="email-content"
                  />
                ) : (
                  <pre className="whitespace-pre-wrap font-sans text-sm">
                    {currentEmail.body}
                  </pre>
                )}
              </div>
            </div>

            {/* Footer com notas */}
            {currentEmail.notes && (
              <div className="p-3 border-t bg-muted/30 shrink-0">
                <p className="text-xs text-muted-foreground">
                  <strong>Notas:</strong> {currentEmail.notes}
                </p>
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default EmailViewerModal;
