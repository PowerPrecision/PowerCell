/**
 * SmartRichEditor - Editor de texto rico com abstração de complexidade HTML
 *
 * - Modo Visual (default): Editor WYSIWYG — o utilizador vê o texto formatado normalmente.
 * - Modo HTML (admin-only): Textarea com código-fonte HTML puro para edição avançada.
 *
 * O botão para alternar para HTML é INVISÍVEL para utilizadores não-admin.
 * Protege variáveis tipo {{HANDLEBARS}} de corrupção ao transitar entre modos.
 */
import React, { useState, useCallback, useMemo } from "react";
import { useAuth } from "../../contexts/AuthContext";
import RichTextEditor, { RichTextViewer } from "./RichTextEditor";
import { Button } from "./button";
import { Code2, Eye } from "lucide-react";

/**
 * @param {string}      value          - HTML content (controlled)
 * @param {function}    onChange        - (html: string) => void
 * @param {boolean}     readOnly        - Entire editor is read-only
 * @param {string}      placeholder    - Placeholder text for empty editor
 * @param {number}      minHeight      - Min height in px
 * @param {boolean}     advanced       - Show advanced Quill toolbar
 * @param {boolean}     allowHtmlAdmin - Allow admin toggle even if role check (prop override)
 * @param {string}      className      - Extra classes on outer wrapper
 * @param {string}      label          - Optional label above the editor
 */
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
  React.useEffect(() => {
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
