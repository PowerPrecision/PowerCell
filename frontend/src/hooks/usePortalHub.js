/**
 * usePortalHub — o estado do Hub do Portal, lido do armazenamento.
 *
 * O login, a escolha de um processo e o logout escrevem no armazenamento e avisam com
 * `EVENTO_DA_SESSAO_DO_PORTAL`; este hook relê. Existe porque o ecrã de login vive DENTRO da
 * página do Portal e quem decide mostrar o Hub (ou a página) é o invólucro por cima dela.
 */
import { useEffect, useState } from "react";

import { EVENTO_DA_SESSAO_DO_PORTAL, lerHub } from "../utils/portalHub";

export default function usePortalHub() {
  const [hub, setHub] = useState(() => lerHub());

  useEffect(() => {
    const reler = () => setHub(lerHub());
    window.addEventListener(EVENTO_DA_SESSAO_DO_PORTAL, reler);
    // Outro separador do mesmo browser: a sessão é partilhada pelo armazenamento.
    window.addEventListener("storage", reler);
    reler();
    return () => {
      window.removeEventListener(EVENTO_DA_SESSAO_DO_PORTAL, reler);
      window.removeEventListener("storage", reler);
    };
  }, []);

  return hub;
}
