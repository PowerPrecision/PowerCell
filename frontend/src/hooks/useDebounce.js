import { useState, useEffect } from "react";

/**
 * useDebounce — devolve uma versão "atrasada" de um valor, que só actualiza
 * depois de `delay` ms sem novas alterações.
 *
 * PORQUÊ: o padrão `setTimeout`/`clearTimeout` guardado numa ref para debounce
 * de pesquisa estava copiado quase byte-a-byte em `SmartClientSearch.jsx`,
 * `SecondTitularCard.jsx` e `admin/ClientSearchTab.js`. Este hook centraliza
 * essa lógica.
 *
 * @param {*} value - Valor a atrasar (ex: texto de um campo de pesquisa)
 * @param {number} [delay=300] - Atraso em milissegundos
 * @returns {*} O valor, actualizado apenas após `delay` ms de inactividade
 */
export function useDebounce(value, delay = 300) {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}

export default useDebounce;
