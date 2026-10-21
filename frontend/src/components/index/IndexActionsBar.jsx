/**
 * IndexActionsBar — as acções da bancada do Index.
 *
 * «Marcar como Indexado» está SEMPRE activo: só o seu próprio pedido a decorrer ou o processo
 * já indexado o desligam (`podeMarcarComoIndexado`) — nunca a IA, os campos em dúvida ou os
 * alertas. Analisar/Extrair são cada um uma chamada paga ao modelo e correm em segundo plano;
 * enquanto há um job activo ficam desligados (o servidor também só deixa correr um).
 */
import { Bot, CheckCircle2, Loader2, ScanText } from "lucide-react";

import { Button } from "../ui/button";
import { haJobActivo, podeMarcarComoIndexado } from "../../utils/indexRevisao";

export function IndexActionsBar({
  processo,
  jobsActivos,
  aAnalisar,
  aExtrair,
  aMarcar,
  onAnalisar,
  onExtrair,
  onMarcar,
  somenteLeitura = false,
}) {
  const ocupado = haJobActivo(jobsActivos);
  const indexado = processo?.index_status === "indexed";

  return (
    <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label="Acções do Index">
      <Button variant="outline" disabled={somenteLeitura || ocupado || aAnalisar} onClick={onAnalisar}>
        {aAnalisar ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden="true" /> : <Bot className="mr-1.5 h-4 w-4" aria-hidden="true" />}
        Analisar
      </Button>
      <Button variant="outline" disabled={somenteLeitura || ocupado || aExtrair} onClick={onExtrair}>
        {aExtrair ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden="true" /> : <ScanText className="mr-1.5 h-4 w-4" aria-hidden="true" />}
        Extrair dados
      </Button>
      <Button
        disabled={somenteLeitura || !podeMarcarComoIndexado({ processo, aMarcar })}
        onClick={onMarcar}
        title={indexado ? "Este processo já está indexado" : undefined}
      >
        {aMarcar ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden="true" /> : <CheckCircle2 className="mr-1.5 h-4 w-4" aria-hidden="true" />}
        {indexado ? "Indexado" : "Marcar como Indexado"}
      </Button>
    </div>
  );
}

export default IndexActionsBar;
