/**
 * ThemeContext - Gestão de tema (Dark/Light Mode)
 * Detecta preferência do sistema e persiste escolha do utilizador
 */
import { createContext, useContext, useState, useEffect } from "react";

const ThemeContext = createContext({
  theme: "light",
  setTheme: () => {},
  toggleTheme: () => {},
  isDark: false,
});

export const useTheme = () => useContext(ThemeContext);

export const ThemeProvider = ({ children }) => {
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

  const setTheme = (newTheme) => {
    setThemeState(newTheme);
  };

  const toggleTheme = () => {
    setThemeState(prev => prev === "dark" ? "light" : "dark");
  };

  return (
    <ThemeContext.Provider value={{ 
      theme, 
      setTheme, 
      toggleTheme,
      isDark: theme === "dark"
    }}>
      {children}
    </ThemeContext.Provider>
  );
};

export default ThemeContext;
