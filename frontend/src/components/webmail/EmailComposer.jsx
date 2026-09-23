/**
 * Compositor de email do Webmail (diálogo).
 *
 * Extraído de `pages/WebmailPage.jsx` (Épico 6). Componente CONTROLADO: o
 * contentor detém os dados do rascunho e o estado de envio; o compositor só
 * apresenta e comunica alterações campo a campo (`onFieldChange`).
 *
 * A canalização do upload (o `input` escondido, o clique na zona e o
 * arrastar-largar) vive AQUI, porque é só DOM: o contentor recebe os
 * ficheiros já prontos em `onUploadFiles(File[])` e trata do resto.
 */
import { useRef } from "react";
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  Mail,
  Send,
  Upload,
  X,
} from "lucide-react";

import { Button } from "../ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "../ui/collapsible";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Input } from "../ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { Textarea } from "../ui/textarea";
import { sanitizeEmailHtml, htmlToText } from "../../utils/sanitize";
import { formatFileSize, getAttachmentIcon } from "./webmailFormatters";

/**
 * @param {object} props
 * @param {boolean} props.open
 * @param {object} props.data Rascunho: to_emails, cc_emails, bcc_emails, subject, body, account.
 * @param {boolean} [props.sending]
 * @param {boolean} [props.ccExpanded]
 * @param {boolean} [props.bccExpanded]
 * @param {Array} [props.attachments] Anexos já carregados.
 * @param {boolean} [props.uploading]
 * @param {(open: boolean) => void} props.onOpenChange
 * @param {(campo: string, valor: string) => void} props.onFieldChange
 * @param {(aberto: boolean) => void} [props.onToggleCc]
 * @param {(aberto: boolean) => void} [props.onToggleBcc]
 * @param {() => void} props.onSend
 * @param {() => void} props.onCancel
 * @param {(ficheiros: File[]) => void} props.onUploadFiles
 * @param {(id: string) => void} props.onRemoveAttachment
 * @param {boolean} [props.canUseGlobalAccounts] Só admin/CEO/diretor escolhem conta.
 * @param {string} [props.effectiveRole] Decide a frase mostrada a quem não escolhe.
 * @param {string} [props.resolvedSignature] Assinatura HTML da empresa activa.
 */
const EmailComposer = ({
  open,
  data,
  sending = false,
  ccExpanded = false,
  bccExpanded = false,
  attachments = [],
  uploading = false,
  onOpenChange,
  onFieldChange,
  onToggleCc = () => {},
  onToggleBcc = () => {},
  onSend,
  onCancel,
  onUploadFiles,
  onRemoveAttachment,
  canUseGlobalAccounts = false,
  effectiveRole = "",
  resolvedSignature = "",
}) => {
  const fileInputRef = useRef(null);

  const aoClicarNaZona = () => fileInputRef.current?.click();

  const aoEscolherFicheiros = (e) => {
    const ficheiros = e.target.files;
    if (ficheiros && ficheiros.length > 0) {
      onUploadFiles(Array.from(ficheiros));
    }
    // Repor o input para o mesmo ficheiro poder ser escolhido outra vez.
    if (e.target) e.target.value = "";
  };

  const aoArrastar = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const aoLargar = (e) => {
    e.preventDefault();
    e.stopPropagation();
    const ficheiros = e.dataTransfer?.files;
    if (ficheiros && ficheiros.length > 0) {
      onUploadFiles(Array.from(ficheiros));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] flex flex-col gap-0 p-0 overflow-hidden">
        <DialogHeader className="px-6 pt-5 pb-3">
          <DialogTitle>
            Nova Mensagem
          </DialogTitle>
          <DialogDescription>
            Componha e envie um email
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto px-6 space-y-3 pb-4">
          {/* To */}
          <div className="flex items-center gap-2">
            <label className="text-sm font-medium w-12 shrink-0">Para:</label>
            <Input
              placeholder="email@exemplo.com"
              value={data.to_emails}
              onChange={(e) =>
                onFieldChange("to_emails", e.target.value)
              }
              className="flex-1"
            />
          </div>

          {/* CC (collapsible) */}
          <Collapsible open={ccExpanded} onOpenChange={onToggleCc}>
            <CollapsibleTrigger asChild>
              <button className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors">
                {ccExpanded ? (
                  <ChevronDown className="h-3 w-3" />
                ) : (
                  <ChevronRight className="h-3 w-3" />
                )}
                {ccExpanded ? "Ocultar CC" : "Mostrar CC"}
              </button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2">
              <div className="flex items-center gap-2">
                <label className="text-sm font-medium w-12 shrink-0">CC:</label>
                <Input
                  placeholder="email@exemplo.com (separar por vírgulas)"
                  value={data.cc_emails}
                  onChange={(e) =>
                    onFieldChange("cc_emails", e.target.value)
                  }
                  className="flex-1"
                />
              </div>
            </CollapsibleContent>
          </Collapsible>

          {/* BCC (collapsible) — PACOTE 12 (Eixo 2): cópia oculta,
              espelhando a linha do CC */}
          <Collapsible open={bccExpanded} onOpenChange={onToggleBcc}>
            <CollapsibleTrigger asChild>
              <button className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors">
                {bccExpanded ? (
                  <ChevronDown className="h-3 w-3" />
                ) : (
                  <ChevronRight className="h-3 w-3" />
                )}
                {bccExpanded ? "Ocultar BCC" : "Mostrar BCC"}
              </button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2">
              <div className="flex items-center gap-2">
                <label className="text-sm font-medium w-12 shrink-0">BCC:</label>
                <Input
                  placeholder="email@exemplo.com (separar por vírgulas)"
                  value={data.bcc_emails}
                  onChange={(e) =>
                    onFieldChange("bcc_emails", e.target.value)
                  }
                  className="flex-1"
                />
              </div>
            </CollapsibleContent>
          </Collapsible>

          {/* Subject */}
          <div className="flex items-center gap-2">
            <label className="text-sm font-medium w-12 shrink-0">
              Assunto:
            </label>
            <Input
              placeholder="Assunto do email"
              value={data.subject}
              onChange={(e) =>
                onFieldChange("subject", e.target.value)
              }
              className="flex-1"
            />
          </div>

          {/* Account — só visível para perfis que podem usar contas globais
              (admin/CEO/diretor). Os restantes perfis enviam sempre pela sua
              conta pessoal (o backend força "personal"), pelo que o seletor
              não deve aparecer — o utilizador só tem uma conta útil. */}
          {canUseGlobalAccounts ? (
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium w-12 shrink-0">Conta:</label>
              <Select
                value={data.account}
                onValueChange={(v) =>
                  onFieldChange("account", v)
                }
              >
                <SelectTrigger className="flex-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="precision">Precision Crédito</SelectItem>
                  <SelectItem value="power">Power Real Estate</SelectItem>
                </SelectContent>
              </Select>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Mail className="h-3.5 w-3.5 shrink-0" />
              <span>
                {effectiveRole === 'indexacao'
                  ? 'Envio pela conta partilhada de Indexação.'
                  : 'Envio pela sua conta pessoal — configure em Perfil > Configuração de Webmail.'}
              </span>
            </div>
          )}

          {/* Drag & Drop upload zone */}
          <div
            onClick={aoClicarNaZona}
            onDragOver={aoArrastar}
            onDrop={aoLargar}
            className={`
              border-2 border-dashed rounded-lg p-4 text-center cursor-pointer
              transition-colors
              ${uploading
                ? "border-primary/50 bg-primary/5"
                : "border-muted-foreground/25 hover:border-muted-foreground/50 hover:bg-muted/30"
              }
            `}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={aoEscolherFicheiros}
            />
            {uploading ? (
              <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                A carregar ficheiro(s)...
              </div>
            ) : (
              <div className="flex flex-col items-center gap-1.5">
                <Upload className="h-5 w-5 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  Arraste ficheiros aqui ou clique para selecionar
                </p>
              </div>
            )}
          </div>

          {/* Uploaded files list — PACOTE 12 (Eixo 2): o upload devolve
              file_name/file_size (backend); chips aceitam ambos os
              formatos (filename/size legado incluído) */}
          {attachments.length > 0 && (
            <div className="space-y-1.5">
              {attachments.map((file) => {
                const displayName = file.filename || file.file_name;
                const displaySize = file.size ?? file.file_size;
                const UpIcon = getAttachmentIcon(displayName);
                return (
                  <div
                    key={file.id}
                    className="flex items-center gap-2 p-2 rounded-md border bg-muted/20"
                  >
                    <UpIcon className="h-4 w-4 text-muted-foreground shrink-0" />
                    <span className="flex-1 text-sm truncate">
                      {displayName || "Ficheiro"}
                    </span>
                    {displaySize ? (
                      <span className="text-xs text-muted-foreground shrink-0">
                        {formatFileSize(displaySize)}
                      </span>
                    ) : null}
                    <button
                      type="button"
                      aria-label={`Remover ${displayName || "anexo"}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onRemoveAttachment(file.id);
                      }}
                      className="h-5 w-5 rounded-full hover:bg-accent flex items-center justify-center text-muted-foreground hover:text-foreground shrink-0 transition-colors"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          {/* Body */}
          <div>
            <Textarea
              placeholder="Escreva a sua mensagem..."
              value={data.body}
              onChange={(e) =>
                onFieldChange("body", e.target.value)
              }
              className="min-h-[200px] resize-y"
              rows={12}
            />
            {/* Pré-visualização da assinatura que será anexada automaticamente
                pelo backend ao enviar. Cada user pode ter uma assinatura por
                empresa (UCR) — mostra a da empresa ativa ou a global. */}
            {resolvedSignature && htmlToText(resolvedSignature).trim() ? (
              <div className="mt-2 rounded-md border border-dashed border-muted-foreground/30 bg-muted/20 p-3">
                <div className="flex items-center gap-1.5 mb-1.5 text-xs font-medium text-muted-foreground">
                  <Mail className="h-3.5 w-3.5" />
                  Assinatura (anexada automaticamente no envio)
                </div>
                <div
                  className="text-xs text-muted-foreground/90 prose prose-sm max-w-none [&_a]:text-primary [&_img]:max-w-full [&_img]:h-auto [&_p]:my-1"
                  dangerouslySetInnerHTML={{
                    __html: sanitizeEmailHtml(resolvedSignature),
                  }}
                />
              </div>
            ) : (
              <p className="mt-2 text-xs text-muted-foreground/70">
                Sem assinatura configurada — pode definir a sua em Perfil &gt; Assinatura de Email.
              </p>
            )}
          </div>
        </div>

        <DialogFooter className="px-6 py-3 border-t shrink-0">
          <Button
            variant="ghost"
            onClick={() => onCancel()}
            disabled={sending}
          >
            Cancelar
          </Button>
          <Button onClick={onSend} disabled={sending}>
            {sending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                A enviar...
              </>
            ) : (
              <>
                <Send className="h-4 w-4 mr-2" />
                Enviar
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default EmailComposer;
