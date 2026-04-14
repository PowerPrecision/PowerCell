/**
 * SmartRichEditor — Editor de texto rico com abstração de complexidade HTML.
 *
 * PORQUÊ: O PowerCell utiliza templates de email com variáveis Handlebars ({{var}})
 * que podem ser corrompidas por editores WYSIWYG ao transitar entre modos visual/HTML.
 * Este componente resolve esse problema mantendo uma camada de abstração: o modo
 * visual (WYSIWYG) é o padrão para utilizadores comuns, enquanto o modo HTML bruto
 * fica acessível apenas a administradores para edições avançadas.
 *
 * DECISÕES ARQUITECTURAIS:
 * - Dois modos de edição: Visual (WYSIWYG via ReactQuill) e HTML (textarea mono).
 * - O botão de alternância para HTML é invisível para não-admins, evitando que
 *   utilizadores inadvertidamente corrompam templates com variáveis.
 * - Controlo de estado separado (htmlDraft) para evitar que o Quill re-analise
 *   o HTML em cada tecla quando em modo de edição bruta.
 * - Sincronização bidireccional: alterações no modo visual propagam-se para o
 *   modo HTML e vice-versa.
 *
 * @param {Object} props
 * @param {string}   [props.value='']        — Conteúdo HTML (componente controlado)
 * @param {Function} [props.onChange]          — Callback (html: string) => void
 * @param {boolean}  [props.readOnly=false]   — Editor completamente em modo de leitura
 * @param {string}   [props.placeholder]      — Texto quando o editor está vazio
 * @param {number}   [props.minHeight=250]    — Altura mínima em pixéis
 * @param {boolean}  [props.advanced=false]   — Mostra toolbar avançada do Quill
 * @param {boolean}  [props.allowHtmlAdmin=true] — Permite toggle HTML mesmo com role check
 * @param {string}   [props.className='']     — Classes CSS adicionais no wrapper
 * @param {string}   [props.label]            — Rótulo opcional acima do editor
 *
 * @context {AuthContext} — Consome user.role para decidir visibilidade do modo HTML
 *
 * @example
 * <SmartRichEditor
 *   value={emailHtml}
 *   onChange={setEmailHtml}
 *   placeholder="Edite o conteúdo do email..."
 *   minHeight={300}
 *   advanced
 * />
 */
import { useState, useEffect, useCallback, useMemo } from "react";
import { Code2, Eye } from "lucide-react";
import { Button } from "./button";
import { useAuth } from "../../contexts/AuthContext";
import RichTextEditor from "./RichTextEditor";

const SmartRichEditor = ({
  value = "",
  onChange,
  readOnly = false,
  placeholder = "Escreva aqui...",
  minHeight = 250,
  advanced = false,
  allowHtmlAdmin = true,
  className = "",
  label,
}) => {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  // Only admins can toggle to HTML mode (unless readOnly or explicitly disabled)
  const showHtmlToggle = allowHtmlAdmin && isAdmin && !readOnly;

  const [viewMode, setViewMode] = useState("visual"); // "visual" | "html"

  // Internal HTML state when in HTML edit mode (to avoid Quill re-parsing on every keystroke)
  const [htmlDraft, setHtmlDraft] = useState(value);

  // Sync external value changes into htmlDraft when not actively editing HTML
  useEffect(() => {
    if (viewMode === "visual") {
      // In visual mode, value is managed by Quill directly via onChange
    } else {
      setHtmlDraft(value);
    }
  }, [value, viewMode]);

  const handleHtmlChange = useCallback(
    (newHtml) => {
      setHtmlDraft(newHtml);
      if (onChange) onChange(newHtml);
    },
    [onChange]
  );

  const handleVisualChange = useCallback(
    (html) => {
      if (onChange) onChange(html);
    },
    [onChange]
  );

  const toggleMode = useCallback(() => {
    if (viewMode === "visual") {
      // Entering HTML mode — freeze current value as draft
      setHtmlDraft(value);
    }
    setViewMode((m) => (m === "visual" ? "html" : "visual"));
  }, [viewMode, value]);

  const toggleLabel = useMemo(
    () =>
      viewMode === "visual" ? (
        <>
          <Code2 className="h-3.5 w-3.5 mr-1" />
          Editar HTML
        </>
      ) : (
        <>
          <Eye className="h-3.5 w-3.5 mr-1" />
          Modo Visual
        </>
      ),
    [viewMode]
  );

  return (
    <div className={`smart-rich-editor ${className}`}>
      {/* Label + HTML toggle */}
      <div className="flex items-center justify-between mb-1.5">
        {label && (
          <span className="text-sm font-medium text-foreground">{label}</span>
        )}
        {!label && <span />}

        {showHtmlToggle && (
          <Button
            type="button"
            variant={viewMode === "html" ? "default" : "outline"}
            size="sm"
            className="text-xs h-7 px-2.5 font-mono"
            onClick={toggleMode}
          >
            {toggleLabel}
          </Button>
        )}
      </div>

      {/* Visual mode — Rich Text (WYSIWYG) */}
      {viewMode === "visual" && (
        <RichTextEditor
          value={value}
          onChange={handleVisualChange}
          placeholder={placeholder}
          readOnly={readOnly}
          minHeight={minHeight}
          advanced={advanced}
        />
      )}

      {/* HTML mode — raw code textarea */}
      {viewMode === "html" && (
        <div className="relative">
          <textarea
            value={htmlDraft}
            onChange={(e) => handleHtmlChange(e.target.value)}
            placeholder="<!-- HTML do conteúdo -->"
            spellCheck={false}
            className="w-full rounded-md border border-input bg-muted/50 p-3 font-mono text-sm leading-relaxed resize-y focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1 text-foreground placeholder:text-muted-foreground"
            style={{ minHeight: `${minHeight}px` }}
          />
          <span className="absolute bottom-2 right-3 text-[10px] text-muted-foreground select-none pointer-events-none">
            Modo HTML — edições afectam o conteúdo final
          </span>
        </div>
      )}
    </div>
  );
};

export default SmartRichEditor;
