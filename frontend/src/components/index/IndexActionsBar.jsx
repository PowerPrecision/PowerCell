/**
 * IndexActionsBar — as acções da bancada do Index.
 *
 * «Marcar como Indexado» está SEMPRE activo: só o seu próprio pedido a decorrer ou o processo
 * já indexado o desligam (`podeMarcarComoIndexado`) — nunca a IA, os campos em dúvida ou os
 * alertas. Analisar/Extrair são cada um uma chamada paga ao modelo e correm em segundo plano;
 * enquanto há um job activo ficam desligados (o servidor também só deixa correr um).
 * «Apagar metadados» gera o PDF limpo dos ficheiros que o Index carregou; o original só é
 * eliminado passada a margem de segurança, e só se houver algo por limpar o botão está activo.
 */
import { Bot, CheckCircle2, Eraser, Loader2, ScanText } from "lucide-react";

import { Button } from "../ui/button";
import { haJobActivo, podeMarcarComoIndexado } from "../../utils/indexRevisao";

export function IndexActionsBar({
  processo,
  jobsActivos,
  aAnalisar,
  aExtrair,
  aSanitizar = false,
  aMarcar,
  porLimpar = 0,
  onAnalisar,
  onExtrair,
  onSanitizar,
  onMarcar,
  somenteLeitura = false,
  motivoSomenteLeitura,
}) {
  const ocupado = haJobActivo(jobsActivos);
  const indexado = processo?.index_status === "indexed";
  // só-leitura (ex.: processo de outro indexador): o motivo vai como tooltip; num botão desligado o
  // browser pode não mostrar o `title`, por isso também vai no contentor da barra
  const motivo = somenteLeitura ? motivoSomenteLeitura : undefined;

  return (
    <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label="Acções do Index" title={motivo}>
      <Button variant="outline" disabled={somenteLeitura || ocupado || aAnalisar} onClick={onAnalisar} title={motivo}>
        {aAnalisar ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden="true" /> : <Bot className="mr-1.5 h-4 w-4" aria-hidden="true" />}
        Analisar
      </Button>
      <Button variant="outline" disabled={somenteLeitura || ocupado || aExtrair} onClick={onExtrair} title={motivo}>
        {aExtrair ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden="true" /> : <ScanText className="mr-1.5 h-4 w-4" aria-hidden="true" />}
        Extrair dados
      </Button>
      <Button
        variant="outline"
        disabled={somenteLeitura || ocupado || aSanitizar || porLimpar === 0}
        onClick={onSanitizar}
        title={motivo || (porLimpar === 0 ? "Nenhum ficheiro carregado pelo Index está por limpar" : undefined)}
      >
        {aSanitizar ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden="true" /> : <Eraser className="mr-1.5 h-4 w-4" aria-hidden="true" />}
        Apagar metadados
      </Button>
      <Button
        disabled={somenteLeitura || !podeMarcarComoIndexado({ processo, aMarcar })}
        onClick={onMarcar}
        title={motivo || (indexado ? "Este processo já está indexado" : undefined)}
      >
        {aMarcar ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden="true" /> : <CheckCircle2 className="mr-1.5 h-4 w-4" aria-hidden="true" />}
        {indexado ? "Indexado" : "Marcar como Indexado"}
      </Button>
    </div>
  );
}

export default IndexActionsBar;
