/**
 * useKeyboardShortcuts - Hook para atalhos de teclado
 * Suporta combinações com Ctrl, Alt, Shift
 */
import { useEffect, useCallback, useState } from "react";

// Mapa de atalhos padrão
const DEFAULT_SHORTCUTS = {
  "ctrl+k": { action: "search", description: "Abrir pesquisa" },
  "ctrl+n": { action: "new", description: "Novo processo/tarefa" },
  "ctrl+/": { action: "help", description: "Mostrar atalhos" },
  "escape": { action: "close", description: "Fechar modal" },
};

export const useKeyboardShortcuts = (customHandlers = {}) => {
  const [showHelpModal, setShowHelpModal] = useState(false);
  const [showSearchModal, setShowSearchModal] = useState(false);

  const handleKeyDown = useCallback((event) => {
    // Ignorar se estiver a escrever num input
    const isTyping = ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName);
    const isEditable = event.target.isContentEditable;
    
    if (isTyping || isEditable) {
      // Permitir Escape em qualquer contexto
      if (event.key !== "Escape") return;
    }

    // Construir key string
    const key = [];
    if (event.ctrlKey || event.metaKey) key.push("ctrl");
    if (event.altKey) key.push("alt");
    if (event.shiftKey) key.push("shift");
    key.push(event.key.toLowerCase());
    const keyString = key.join("+");

    // Verificar atalhos padrão
    const shortcut = DEFAULT_SHORTCUTS[keyString];
    
    if (shortcut) {
      event.preventDefault();
      
      switch (shortcut.action) {
        case "search":
          setShowSearchModal(true);
          if (customHandlers.onSearch) customHandlers.onSearch();
          break;
        case "new":
          if (customHandlers.onNew) customHandlers.onNew();
          break;
        case "help":
          setShowHelpModal(prev => !prev);
          break;
        case "close":
          setShowHelpModal(false);
          setShowSearchModal(false);
          if (customHandlers.onClose) customHandlers.onClose();
          break;
        default:
          break;
      }
    }

    // Verificar handlers customizados
    if (customHandlers[keyString]) {
      event.preventDefault();
      customHandlers[keyString](event);
    }
  }, [customHandlers]);

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  return {
    showHelpModal,
    setShowHelpModal,
    showSearchModal,
    setShowSearchModal,
    shortcuts: DEFAULT_SHORTCUTS,
  };
};

// Componente de ajuda com atalhos
export const KeyboardShortcutsHelp = ({ shortcuts = DEFAULT_SHORTCUTS }) => {
  return (
    <div className="space-y-2">
      <h3 className="font-semibold text-lg mb-4">Atalhos de Teclado</h3>
      <div className="space-y-2">
        {Object.entries(shortcuts).map(([key, { description }]) => (
          <div key={key} className="flex justify-between items-center py-2 border-b">
            <span className="text-muted-foreground">{description}</span>
            <kbd className="px-2 py-1 bg-muted rounded text-sm font-mono">
              {key.replace("ctrl", "Ctrl").replace("+", " + ").toUpperCase()}
            </kbd>
          </div>
        ))}
      </div>
    </div>
  );
};

export default useKeyboardShortcuts;
