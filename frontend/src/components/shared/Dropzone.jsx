/**
 * A zona de arrastar e largar — toda a área útil, não só o botão.
 *
 * Embrulha o conteúdo que já existe e acrescenta-lhe o comportamento: não
 * substitui o botão de upload, convive com ele (o botão continua a ser o
 * caminho acessível por teclado, e é por isso que esta zona NÃO é focável —
 * duplicar o mesmo alvo no tabulador só faz ruído para quem usa leitor de
 * ecrã).
 *
 * TRÊS REGRAS
 * ===========
 * 1. **Só reage a um arrasto de FICHEIROS** (`eArrastoDeFicheiros`). No
 *    separador Documentos, arrastar um ficheiro entre categorias é outro
 *    gesto, com outro significado (mover), e ligar o upload por arrasto sem
 *    esta distinção partia-o.
 * 2. **O realce usa um contador de entradas/saídas**, senão pisca ao passar
 *    sobre o conteúdo.
 * 3. **Aplica o MESMO `accept` do botão** e diz quais recusou. A parede real é
 *    a quarentena de magic bytes do servidor; isto é para o cliente não
 *    descobrir pelo erro, depois de a rede ter transportado o ficheiro.
 */
import React, { useCallback, useState } from "react";
import { UploadCloud } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  ARRASTO_PARADO,
  arrastoEntrou,
  arrastoSaiu,
  arrastoTerminou,
  eArrastoDeFicheiros,
  ficheirosDoEvento,
  mensagemDeRecusa,
  separarPorTipoAceite,
} from "@/utils/dropzone";

const Dropzone = ({
  onFicheiros,
  onRecusados,
  accept = "",
  disabled = false,
  className = "",
  classeActiva = "ring-2 ring-primary ring-offset-2",
  rotulo = "Largue os ficheiros para enviar",
  mostrarSobreposicao = true,
  testId = "dropzone",
  children,
}) => {
  const [arrasto, setArrasto] = useState(ARRASTO_PARADO);

  const relevante = useCallback(
    (evento) => !disabled && eArrastoDeFicheiros(evento),
    [disabled]
  );

  const aoEntrar = (evento) => {
    if (!relevante(evento)) return;
    evento.preventDefault();
    setArrasto((e) => arrastoEntrou(e));
  };

  const aoPassar = (evento) => {
    if (!relevante(evento)) return;
    // Sem `preventDefault` no `dragover` o browser ABRE o ficheiro em vez de
    // o entregar ao `drop` — é a razão mais comum de uma zona "não funcionar".
    evento.preventDefault();
    if (evento.dataTransfer) evento.dataTransfer.dropEffect = "copy";
  };

  const aoSair = (evento) => {
    if (!relevante(evento)) return;
    evento.preventDefault();
    setArrasto((e) => arrastoSaiu(e));
  };

  const aoLargar = (evento) => {
    if (!relevante(evento)) return;
    evento.preventDefault();
    setArrasto(arrastoTerminou());
    const { aceites, recusados } = separarPorTipoAceite(
      ficheirosDoEvento(evento),
      accept
    );
    // A ORDEM importa: envia-se primeiro o que se pode, reporta-se depois o
    // que não se pôde. Ao contrário, um largar MISTO apagava o aviso — quem
    // trata os aceites costuma limpar o estado do envio anterior, e esse
    // "limpar" apagava a recusa que tinha acabado de ser escrita. Com esta
    // ordem, um largar limpo também limpa um aviso antigo.
    if (aceites.length > 0) onFicheiros?.(aceites);
    if (recusados.length > 0) {
      onRecusados?.(recusados, mensagemDeRecusa(recusados, accept));
    }
  };

  return (
    <div
      className={cn("relative", className, arrasto.activo && classeActiva)}
      onDragEnter={aoEntrar}
      onDragOver={aoPassar}
      onDragLeave={aoSair}
      onDrop={aoLargar}
      data-testid={testId}
      data-arrasto-activo={arrasto.activo ? "true" : "false"}
    >
      {children}
      {arrasto.activo && mostrarSobreposicao && (
        <div
          className="absolute inset-0 flex items-center justify-center gap-2 rounded-md bg-primary/10 pointer-events-none text-sm font-medium text-primary"
          aria-hidden="true"
        >
          <UploadCloud className="h-4 w-4" />
          {rotulo}
        </div>
      )}
    </div>
  );
};

export default Dropzone;
