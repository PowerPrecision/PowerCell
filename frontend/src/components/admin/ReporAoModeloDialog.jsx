/**
 * ReporAoModeloDialog — «Repor ao Modelo» (workflow ou formulário de uma rede) com PASSWORD.
 *
 * É o `ConfirmarComPasswordDialog` com o texto, o ícone, os `data-testid` (`repor-modelo-*`) e a
 * leitura de erros desta acção. Descarta a configuração própria da rede e volta ao modelo; o
 * SERVIDOR valida a password.
 */
import { RotateCcw } from "lucide-react";

import ConfirmarComPasswordDialog from "./ConfirmarComPasswordDialog";
import { lerErroDeReposicao } from "../../utils/reporAoModelo";

export default function ReporAoModeloDialog(props) {
  return (
    <ConfirmarComPasswordDialog
      {...props}
      rotuloConfirmar="Repor ao Modelo"
      Icone={RotateCcw}
      testIdBase="repor-modelo"
      lerErro={lerErroDeReposicao}
    />
  );
}
