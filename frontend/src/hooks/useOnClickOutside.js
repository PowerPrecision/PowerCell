/**
 * ====================================================================
 * useOnClickOutside - Custom Hook para Detetar Cliques Fora
 * ====================================================================
 * 
 * FORNECE:
 * - Detecção de cliques fora de um elemento
 * - Cleanup automático do event listener
 * - Suporte para múltiplos elementos (refs array)
 * 
 * USA:
 * - useEffect com cleanup (React way)
 * - document.addEventListener com remoção no unmount
 * 
 * EXEMPLO:
 * const dropdownRef = useRef(null);
 * useOnClickOutside(dropdownRef, () => setIsOpen(false));
 * 
 * // Ou com múltiplos elementos:
 * useOnClickOutside([dropdownRef, buttonRef], () => setIsOpen(false));
 * 
 * ====================================================================
 */
import { useEffect, useRef } from 'react';

export const useOnClickOutside = (refs, handler) => {
  // Normalizar refs para array
  const refsArray = Array.isArray(refs) ? refs : [refs];
  const handlerRef = useRef(handler);

  // Manter handler actualizado
  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);

  useEffect(() => {
    const listener = (event) => {
      // Verificar se o clique foi dentro de algum dos elementos
      const isInside = refsArray.some(
        (ref) => ref.current && ref.current.contains(event.target)
      );

      // Se foi fora, chamar o handler
      if (!isInside) {
        handlerRef.current(event);
      }
    };

    // Usar mousedown para melhor UX (antes do click)
    document.addEventListener('mousedown', listener);
    // Também ouvir touchstart para mobile
    document.addEventListener('touchstart', listener);

    // CLEANUP: Remover listeners no unmount
    return () => {
      document.removeEventListener('mousedown', listener);
      document.removeEventListener('touchstart', listener);
    };
  }, [refsArray]); // refsArray é estável (definido fora do effect)
};

export default useOnClickOutside;
