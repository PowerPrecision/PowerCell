/**
 * usePortalTheme — a vista noturna do Portal do Cliente.
 *
 * O Portal foi sempre claro, independentemente do tema do CRM ou do sistema
 * operativo do cliente. Mantém-se: por omissão é claro, e só passa a escuro
 * quando o cliente o pede no botão. A escolha é do Portal (chave própria no
 * `localStorage`), não do CRM: um consultor com o CRM escuro não vê o Portal
 * escuro, e um cliente que escolheu escuro não altera nada no CRM.
 *
 * COMO SE APLICA: o Portal escreve nas cores com classes Tailwind cruas
 * (`bg-white`, `text-gray-700`…), que o `dark:` não alcança. Enquanto o Portal
 * está montado, o `<html>` leva `portal-ativo` e (se escuro) `dark`; o ficheiro
 * `styles/portalEscuro.css` — GERADO das classes que o Portal usa — reescreve-as
 * só sob `html.portal-ativo.dark`, e os componentes de tokens (diálogos,
 * selects) acompanham pela classe `dark`. Ao sair, repõe-se o que lá estava.
 */
import { useCallback, useEffect, useState } from "react";

export const CHAVE_DO_TEMA_DO_PORTAL = "portal-theme";
export const CLASSE_DO_PORTAL = "portal-ativo";

/** Lê a preferência guardada. O armazenamento pode estar bloqueado: nunca é um requisito. */
export function lerTemaDoPortal(armazenamento) {
  try {
    const guardado = (armazenamento ?? window.localStorage).getItem(CHAVE_DO_TEMA_DO_PORTAL);
    return guardado === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function guardarTemaDoPortal(tema, armazenamento) {
  try {
    (armazenamento ?? window.localStorage).setItem(CHAVE_DO_TEMA_DO_PORTAL, tema);
  } catch {
    // Janela privada / armazenamento bloqueado: a escolha vale só nesta sessão.
  }
}

export default function usePortalTheme() {
  const [tema, setTema] = useState(() => lerTemaDoPortal());

  useEffect(() => {
    const raiz = document.documentElement;
    const tinhaDark = raiz.classList.contains("dark");
    const tinhaPortal = raiz.classList.contains(CLASSE_DO_PORTAL);
    raiz.classList.add(CLASSE_DO_PORTAL);
    return () => {
      if (!tinhaPortal) raiz.classList.remove(CLASSE_DO_PORTAL);
      // O CRM volta ao tema em que estava (ex.: staff a sair do «Ver como cliente»).
      raiz.classList.toggle("dark", tinhaDark);
    };
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", tema === "dark");
  }, [tema]);

  const alternar = useCallback(() => {
    setTema((actual) => {
      const seguinte = actual === "dark" ? "light" : "dark";
      guardarTemaDoPortal(seguinte);
      return seguinte;
    });
  }, []);

  return { tema, escuro: tema === "dark", alternar };
}
