/**
 * Coluna 1 do Webmail — caixas, pastas, marcadores e pastas personalizadas.
 *
 * Extraído de `pages/WebmailPage.jsx` (Épico 6). Componente de
 * APRESENTAÇÃO: não muda estado nenhum. Onde antes havia quatro `set*`
 * encadeados num `onClick` (escolher uma pasta também repunha a página, o
 * marcador e a pasta personalizada), há agora UMA intenção —
 * `onSelectFolder(id)` — e é o contentor que decide o que isso implica.
 *
 * Os três diálogos de pasta (menu de contexto, criar/editar e mover)
 * ficaram no contentor: são modais em portal, com estado próprio, e
 * arrastá-los para aqui aumentaria o risco sem reduzir acoplamento.
 *
 */
import { Folder, FolderOpen, FolderPlus, MoreVertical, Plus, Tag } from "lucide-react";

import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Label } from "../ui/label";
import { Separator } from "../ui/separator";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "../ui/select";

/**
 * @param {object} props
 * @param {Array} props.folders Pastas do sistema (id, label, icon).
 * @param {Array} [props.customFolders]
 * @param {Array} [props.labels]
 * @param {Array} [props.mailboxOptions] Caixas disponíveis para o selector.
 * @param {string} props.activeFolder
 * @param {string|null} [props.activeCustomFolder]
 * @param {string|null} [props.selectedLabel]
 * @param {string} [props.mailboxValue] Valor actual do selector de caixa.
 * @param {boolean} [props.mailboxLocked] O perfil de indexação não troca de caixa.
 * @param {number} [props.unreadCount] Não lidas da Caixa de Entrada.
 * @param {object} [props.folderCounts] Contagens por pasta do sistema.
 * @param {number} [props.totalEmails]
 * @param {(folderId: string) => void} props.onSelectFolder
 * @param {(labelName: string|null) => void} props.onSelectLabel
 * @param {(folderId: string|null) => void} props.onSelectCustomFolder
 * @param {(folder: object, posicao: {x: number, y: number}) => void} props.onOpenFolderMenu
 * @param {() => void} props.onCreateFolder
 * @param {() => void} props.onCompose
 * @param {(mailbox: string) => void} props.onMailboxChange
 */
const FolderNavigation = ({
  folders,
  customFolders = [],
  labels = [],
  mailboxOptions = [],
  activeFolder,
  activeCustomFolder = null,
  selectedLabel = null,
  mailboxValue = "",
  mailboxLocked = false,
  unreadCount = 0,
  folderCounts = {},
  totalEmails = 0,
  onSelectFolder,
  onSelectLabel,
  onSelectCustomFolder,
  onOpenFolderMenu,
  onCreateFolder,
  onCompose,
  onMailboxChange,
}) => {
  return (
    <div
      className="h-full border-r border-border bg-muted/30 flex flex-col overflow-hidden"
      data-testid="webmail-folder-pane"
    >
      {/* Pacote DR — selector de caixa no topo da coluna 1 */}
      <div className="p-3 space-y-2 border-b border-border">
        <Label
          htmlFor="webmail-mailbox-select"
          className="text-[11px] uppercase tracking-wide text-muted-foreground"
        >
          A ler emails de
        </Label>
        <Select
          value={mailboxValue}
          onValueChange={onMailboxChange}
          disabled={mailboxLocked}
        >
          <SelectTrigger
            id="webmail-mailbox-select"
            className="h-9 text-xs"
            data-testid="webmail-mailbox-select"
          >
            <SelectValue placeholder="Selecionar caixa" />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectLabel className="text-xs text-muted-foreground">Caixas</SelectLabel>
              {mailboxOptions.map((option) => (
                <SelectItem key={option.value || option.label} value={option.value || "personal:"}>
                  {option.label}
                  {option.unread > 0 ? ` (${option.unread})` : ""}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
      </div>

      {/* Nova Mensagem */}
      <div className="p-3 space-y-2">
        <Button
          className="w-full gap-2"
          onClick={onCompose}
        >
          <Plus className="h-4 w-4" />
          Nova Mensagem
        </Button>
        {/* Ponto 8, Fase 3 — o botão "Sincronizar" de largura total que
            vivia aqui saiu. A sincronização é uma operação de FUNDO: o
            que o utilizador precisa de saber é se a caixa está
            actualizada, e isso cabe numa linha no cabeçalho do
            separador da empresa (`WebmailCompanyTabs`). Ocupar uma
            fatia permanente da barra lateral com uma acção que se usa
            uma vez por sessão era o "painel intrusivo". */}
      </div>

      <Separator />

      <div className="flex-1 min-h-0 overflow-y-auto">
      {/* Folders */}
      <nav className="p-2 space-y-0.5">
        {folders.map((folder) => {
          const Icon = folder.icon;
          const isActive = activeFolder === folder.id && !selectedLabel && !activeCustomFolder;
          const folderLabel = folder.label;
          return (
            <button
              key={folder.id}
              onClick={() => onSelectFolder(folder.id)}
              className={`
                w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm
                transition-colors text-left
                ${
                  isActive
                    ? "bg-accent text-accent-foreground font-medium"
                    : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                }
              `}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="flex-1 truncate">{folderLabel}</span>
              {folderCounts[folder.id] > 0 && (
                <Badge
                  variant={folder.id === "inbox" ? "default" : "secondary"}
                  className={`h-5 min-w-[20px] flex items-center justify-center text-[10px] px-1.5 ${
                    folder.id === "inbox" ? "bg-primary text-primary-foreground" : ""
                  }`}
                >
                  {folder.id === "inbox" ? unreadCount || folderCounts[folder.id] : folderCounts[folder.id]}
                </Badge>
              )}
            </button>
          );
        })}
      </nav>

      {/* Marcadores (Labels) */}
      {labels.length > 0 && (
        <>
          <Separator />
          <div className="px-2 pt-2 pb-1">
            <div className="flex items-center gap-2 px-3 py-1.5">
              <Tag className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Marcadores
              </span>
            </div>
            <div className="space-y-0.5">
              {labels.map((label) => {
                const isLabelActive = selectedLabel === label.name;
                return (
                  <button
                    key={label.id}
                    onClick={() => onSelectLabel(isLabelActive ? null : label.name)}
                    className={`
                      w-full flex items-center gap-3 px-3 py-1.5 rounded-md text-sm
                      transition-colors text-left
                      ${
                        isLabelActive
                          ? "bg-accent text-accent-foreground font-medium"
                          : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                      }
                    `}
                  >
                    <span
                      className="w-3 h-3 rounded-full shrink-0 border border-black/10"
                      style={{ backgroundColor: label.color || "#6b7280" }}
                    />
                    <span className="flex-1 truncate">{label.name}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </>
      )}

      {/* Pastas Personalizadas */}
      <div className="px-2 pt-1 pb-1">
        <div className="flex items-center justify-between px-3 py-1.5">
          <div className="flex items-center gap-2">
            <Folder className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Pastas
            </span>
          </div>
          <button
            onClick={onCreateFolder}
            className="p-0.5 rounded hover:bg-accent/50 text-muted-foreground hover:text-foreground transition-colors"
            title="Nova pasta"
          >
            <FolderPlus className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="space-y-0.5">
          {customFolders.map((folder) => {
            const isFolderActive = activeCustomFolder === folder.id;
            return (
              <div key={folder.id} className="relative group">
                <div className="flex items-stretch">
                <button
                  type="button"
                  onClick={() => onSelectCustomFolder(isFolderActive ? null : folder.id)}
                  className={`
                    flex-1 min-w-0 flex items-center gap-3 px-3 py-1.5 rounded-md text-sm
                    transition-colors text-left
                    ${
                      isFolderActive
                        ? "bg-accent text-accent-foreground font-medium"
                        : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                    }
                  `}
                >
                  <FolderOpen className={`h-4 w-4 shrink-0 ${isFolderActive ? "text-foreground" : ""}`}
                    style={isFolderActive ? { color: folder.color } : {}}
                  />
                  <span className="flex-1 truncate">{folder.name}</span>
                  {folder.email_count > 0 && (
                    <Badge
                      variant="secondary"
                      className="h-5 min-w-[20px] flex items-center justify-center text-[10px] px-1.5"
                    >
                      {folder.email_count}
                    </Badge>
                  )}
                </button>
                {/* BUG PRÉ-EXISTENTE corrigido na extracção: este botão vivia
                    DENTRO do botão da pasta. Um `<button>` não pode conter
                    outro — HTML inválido, que cada browser desfaz como
                    entende. Passam a irmãos, como na lista de conversas. */}
                  <button
                  type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      const rect = e.currentTarget.getBoundingClientRect();
                      onOpenFolderMenu(folder, { x: rect.left, y: rect.bottom });
                    }}
                    aria-label={`Opções da pasta ${folder.name}`}
                    className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-accent/70 transition-opacity"
                  >
                    <MoreVertical className="h-3 w-3" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
      </div>

      {/* Footer info */}
      <div className="mt-auto p-3 border-t space-y-1">
        <p className="text-[10px] text-muted-foreground">
          {totalEmails} email{totalEmails !== 1 ? "s" : ""}
        </p>
      </div>
    </div>  );
};

export default FolderNavigation;
