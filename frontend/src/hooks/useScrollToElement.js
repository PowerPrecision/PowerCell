/**
 * ====================================================================
 * useScrollToElement - Custom Hook para Scroll Automático
 * ====================================================================
 * 
 * FORNECE:
 * - scrollRef: ref callback para registar elementos
 * - scrollToElement: função para fazer scroll para um elemento registado
 * - containerRef: ref para o container que limita a busca
 * 
 * USA:
 * - useRef em vez de document.querySelector (React way)
 * - Scoped query como fallback para formulários grandes
 * 
 * EXEMPLO:
 * const { scrollRef, scrollToElement } = useScrollToElement();
 * 
 * <input ref={scrollRef('email')} name="email" />
 * <button onClick={() => scrollToElement('email')}>Focus Email</button>
 * 
 * ====================================================================
 */
import { useRef, useCallback } from 'react';

export const useScrollToElement = () => {
  // Map de refs para elementos
  const elementRefs = useRef({});
  // Ref para o container (para scoped queries)
  const containerRef = useRef(null);

  // Callback ref para registar elementos
  const scrollRef = useCallback((name) => (element) => {
    if (element) {
      elementRefs.current[name] = element;
    }
  }, []);

  // Função para fazer scroll e focus num elemento
  const scrollToElement = useCallback((name, options = {}) => {
    const { focus = true, behavior = 'smooth', block = 'center' } = options;

    // Primeiro tenta a ref registada
    let element = elementRefs.current[name];

    // Fallback: scoped query no container
    if (!element && containerRef.current) {
      element = containerRef.current.querySelector(
        `[name="${name}"], [data-testid="${name}"], #${name}`
      );
    }

    if (element) {
      element.scrollIntoView({ behavior, block });
      if (focus && typeof element.focus === 'function') {
        element.focus();
      }
      return true;
    }

    return false;
  }, []);

  // Função para obter uma ref específica
  const getElementRef = useCallback((name) => {
    return elementRefs.current[name] || null;
  }, []);

  return {
    scrollRef,
    scrollToElement,
    getElementRef,
    containerRef,
  };
};

export default useScrollToElement;
