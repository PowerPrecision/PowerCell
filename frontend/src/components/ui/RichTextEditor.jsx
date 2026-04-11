/**
 * RichTextEditor - Componente WYSIWYG para edição de HTML formatado
 * 
 * Wrapper do React Quill com estilos consistentes com Tailwind/Shadcn.
 * Suporta tabelas responsivas, formatação rica e é completamente reutilizável.
 */
import React, { useMemo, useCallback } from 'react';
import ReactQuill from 'react-quill-new';
import 'quill/dist/quill.snow.css';

// Estilos customizados para o editor
const editorStyles = `
  /* Container do editor */
  .rich-text-editor {
    border-radius: 0.5rem;
    overflow: hidden;
  }
  
  .rich-text-editor .ql-toolbar {
    border: 1px solid hsl(var(--border));
    border-bottom: none;
    border-radius: 0.5rem 0.5rem 0 0;
    background: hsl(var(--card));
  }
  
  .rich-text-editor .ql-container {
    border: 1px solid hsl(var(--border));
    border-radius: 0 0 0.5rem 0.5rem;
    font-family: inherit;
    font-size: 14px;
    min-height: 200px;
    background: hsl(var(--background));
    color: hsl(var(--foreground));
  }
  
  .rich-text-editor .ql-editor {
    min-height: 200px;
    padding: 12px 15px;
    line-height: 1.6;
  }
  
  .rich-text-editor .ql-editor.ql-blank::before {
    color: hsl(var(--muted-foreground));
    font-style: normal;
  }
  
  /* Tabelas responsivas no editor */
  .rich-text-editor .ql-editor table {
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
    font-size: 14px;
  }
  
  .rich-text-editor .ql-editor table td,
  .rich-text-editor .ql-editor table th {
    border: 1px solid hsl(var(--border));
    padding: 8px 12px;
    text-align: left;
  }
  
  .rich-text-editor .ql-editor table th {
    background: hsl(var(--muted));
    font-weight: 600;
  }
  
  .rich-text-editor .ql-editor table tr:nth-child(even) td {
    background: hsl(var(--muted) / 0.3);
  }
  
  /* Botões da toolbar */
  .rich-text-editor .ql-toolbar button {
    color: hsl(var(--foreground));
  }
  
  .rich-text-editor .ql-toolbar button:hover,
  .rich-text-editor .ql-toolbar button.ql-active {
    color: hsl(var(--primary));
  }
  
  .rich-text-editor .ql-toolbar button:hover .ql-stroke,
  .rich-text-editor .ql-toolbar button.ql-active .ql-stroke {
    stroke: hsl(var(--primary));
  }
  
  .rich-text-editor .ql-toolbar button:hover .ql-fill,
  .rich-text-editor .ql-toolbar button.ql-active .ql-fill {
    fill: hsl(var(--primary));
  }
  
  /* Pickers (font, size, color, etc) */
  .rich-text-editor .ql-toolbar .ql-picker {
    color: hsl(var(--foreground));
  }
  
  .rich-text-editor .ql-toolbar .ql-picker:hover {
    color: hsl(var(--primary));
  }
  
  .rich-text-editor .ql-toolbar .ql-picker-options {
    background: hsl(var(--popover));
    border-color: hsl(var(--border));
  }
  
  .rich-text-editor .ql-toolbar .ql-picker-item:hover {
    color: hsl(var(--primary));
  }
  
  /* Tooltip */
  .ql-tooltip {
    background: hsl(var(--popover));
    border-color: hsl(var(--border));
    color: hsl(var(--foreground));
    box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
  }
  
  /* Dark mode adjustments */
  .dark .rich-text-editor .ql-toolbar {
    background: hsl(var(--card));
  }
  
  .dark .rich-text-editor .ql-container {
    background: hsl(var(--background));
  }
  
  /* Modo readonly */
  .rich-text-editor.readonly .ql-toolbar {
    display: none;
  }
  
  .rich-text-editor.readonly .ql-container {
    border-radius: 0.5rem;
    border: 1px solid hsl(var(--border));
  }
  
  /* Error state */
  .rich-text-editor.error .ql-toolbar,
  .rich-text-editor.error .ql-container {
    border-color: hsl(var(--destructive));
  }
`;

/**
 * Componente RichTextEditor
 * 
 * @param {string} value - Conteúdo HTML do editor
 * @param {function} onChange - Callback chamado quando o conteúdo muda
 * @param {string} placeholder - Texto placeholder quando vazio
 * @param {boolean} readOnly - Se o editor é apenas leitura (modo preview)
 * @param {string} className - Classes adicionais para o container
 * @param {number} minHeight - Altura mínima do editor em pixels
 * @param {boolean} error - Se deve mostrar estado de erro
 * @param {object} toolbarOptions - Opções customizadas da toolbar
 */
const RichTextEditor = ({
  value = '',
  onChange,
  placeholder = 'Escreva aqui...',
  readOnly = false,
  className = '',
  minHeight = 200,
  error = false,
  toolbarOptions = null,
}) => {
  
  // Configuração padrão da toolbar
  const defaultToolbar = useMemo(() => [
    [{ 'header': [1, 2, 3, 4, 5, 6, false] }],
    ['bold', 'italic', 'underline', 'strike'],
    [{ 'color': [] }, { 'background': [] }],
    [{ 'list': 'ordered' }, { 'list': 'bullet' }],
    [{ 'indent': '-1' }, { 'indent': '+1' }],
    [{ 'align': [] }],
    ['link'],
    ['clean'],
  ], []);

  // Handlers
  const handleChange = useCallback((content) => {
    if (onChange) {
      onChange(content);
    }
  }, [onChange]);

  // Módulos do Quill
  const modules = useMemo(() => ({
    toolbar: toolbarOptions || defaultToolbar,
    clipboard: {
      // Permitir colagem de HTML formatado
      matchVisual: false,
    },
  }), [toolbarOptions, defaultToolbar]);

  // Formatos permitidos
  const formats = useMemo(() => [
    'header', 'font', 'size',
    'bold', 'italic', 'underline', 'strike',
    'color', 'background',
    'list', 'indent',
    'align',
    'link',
    'image',
  ], []);

  // Classes do container
  const containerClasses = `
    rich-text-editor
    ${readOnly ? 'readonly' : ''}
    ${error ? 'error' : ''}
    ${className}
  `.trim();

  return (
    <>
      {/* Inject styles */}
      <style>{editorStyles}</style>
      
      <div className={containerClasses}>
        <ReactQuill
          theme="snow"
          value={value}
          onChange={handleChange}
          modules={modules}
          formats={formats}
          placeholder={placeholder}
          readOnly={readOnly}
          style={{ minHeight: `${minHeight}px` }}
        />
      </div>
    </>
  );
};

/**
 * RichTextViewer - Componente para exibir HTML formatado sem edição
 * Útil para previews de emails recebidos
 * 
 * @param {string} html - Conteúdo HTML a exibir
 * @param {string} className - Classes adicionais
 */
export const RichTextViewer = ({ html = '', className = '' }) => {
  // Sanitizar HTML para segurança (básico - usar DOMPurify em produção)
  const sanitizeHtml = (htmlString) => {
    // Remover scripts e eventos inline perigosos
    return htmlString
      .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
      .replace(/on\w+="[^"]*"/gi, '')
      .replace(/on\w+='[^']*'/gi, '');
  };

  const viewerStyles = `
    .rich-text-viewer {
      font-family: 'Segoe UI', Arial, sans-serif;
      line-height: 1.6;
      color: hsl(var(--foreground));
      padding: 16px;
      background: hsl(var(--background));
      border-radius: 0.5rem;
      border: 1px solid hsl(var(--border));
    }
    
    .rich-text-viewer table {
      width: 100%;
      border-collapse: collapse;
      margin: 16px 0;
      font-size: 14px;
    }
    
    .rich-text-viewer table td,
    .rich-text-viewer table th {
      border: 1px solid hsl(var(--border));
      padding: 8px 12px;
      text-align: left;
    }
    
    .rich-text-viewer table th {
      background: hsl(var(--muted));
      font-weight: 600;
    }
    
    .rich-text-viewer table tr:nth-child(even) td {
      background: hsl(var(--muted) / 0.3);
    }
    
    .rich-text-viewer h1, .rich-text-viewer h2, .rich-text-viewer h3 {
      margin-top: 1em;
      margin-bottom: 0.5em;
    }
    
    .rich-text-viewer p {
      margin: 0.5em 0;
    }
    
    .rich-text-viewer a {
      color: hsl(var(--primary));
      text-decoration: underline;
    }
    
    .rich-text-viewer img {
      max-width: 100%;
      height: auto;
    }
  `;

  return (
    <>
      <style>{viewerStyles}</style>
      <div 
        className={`rich-text-viewer ${className}`}
        dangerouslySetInnerHTML={{ __html: sanitizeHtml(html) }}
      />
    </>
  );
};

export default RichTextEditor;
