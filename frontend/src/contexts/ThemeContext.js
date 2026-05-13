/**
 * ThemeContext — Contexto de gestão de tema (Dark/Light Mode) com detecção automática.
 *
 * PORQUÊ: O PowerCell suporta modo escuro para conforto visual em sessões longas,
 * especialmente útil para consultores que trabalham muitas horas no CRM. A detecção
 * automática da preferência do sistema evita configuração manual no primeiro acesso.
 *
 * DECISÕES ARQUITECTURAIS:
 * - Persistência em localStorage: a escolha do utilizador sobrevive a recarregamentos.
 * - Detecção de preferência do sistema via matchMedia: o tema inicial segue a
 *   configuração do SO do utilizador (prefers-color-scheme: dark).
 * - Estratégia Tailwind "class": o tema aplica a classe "dark" no elemento <html>
 *   porque é a forma recomendada pelo Tailwind CSS — não é uma violação do paradigma React.
 * - O tema só muda automaticamente se o utilizador não tiver uma preferência guardada
 *   em localStorage (prioridade: escolha manual > preferência do sistema > light).
 *
 * @context {ThemeContext} — Fornecido via ThemeProvider em App.js
 * @hook {useTheme} — Hook para consumir o contexto em componentes React
 *
 * @returns {Object} Estado e funções do tema:
 *   - theme {string} — "light" ou "dark"
 *   - setTheme {Function} — Define o tema explicitamente
 *   - toggleTheme {Function} — Alterna entre light e dark
 *   - isDark {boolean} — true se o tema activo é "dark"
 */
import { createContext, useContext, useState, useEffect, useMemo, useCallback } from "react";

const ThemeContext = createContext({
  theme: "light",
  setTheme: () => {},
  toggleTheme: () => {},
  isDark: false,
});

export const useTheme = () => useContext(ThemeContext);

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => {
    // Verificar localStorage primeiro
    const stored = localStorage.getItem("theme");
    if (stored) return stored;
    
    // Detectar preferência do sistema
    if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
      return "dark";
    }
    
    return "light";
  });

  useEffect(() => {
    // Aplicar tema ao documento
    // NOTA: Esta é a forma CORRETA de implementar dark mode com Tailwind CSS 'class' strategy.
    // O Tailwind espera a classe 'dark' no elemento <html> (document.documentElement).
    // Isto NÃO é uma violação do paradigma React - é a API recomendada pelo Tailwind.
    const root = document.documentElement;
    
    if (theme === "dark") {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
    
    // Guardar preferência
    localStorage.setItem("theme", theme);
  }, [theme]);

  useEffect(() => {
    // Escutar mudanças na preferência do sistema
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    
    const handleChange = (e) => {
      // Só mudar se não houver preferência guardada
      if (!localStorage.getItem("theme")) {
        setThemeState(e.matches ? "dark" : "light");
      }
    };
    
    mediaQuery.addEventListener("change", handleChange);
    return () => mediaQuery.removeEventListener("change", handleChange);
  }, []);

  const setTheme = useCallback((newTheme) => {
    setThemeState(newTheme);
  }, []);

  const toggleTheme = useCallback(() => {
    setThemeState(prev => prev === "dark" ? "light" : "dark");
  }, []);

  // ── FIX: memoize context value to prevent all consumers re-rendering
  // when ThemeProvider re-renders but theme hasn't changed ──
  const value = useMemo(() => ({ 
    theme, 
    setTheme, 
    toggleTheme,
    isDark: theme === "dark"
  }), [theme, setTheme, toggleTheme]);

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
}

export default ThemeContext;
