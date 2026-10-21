/**
 * Um pedido de documentos do CRM, como o parceiro o vê.
 *
 * É o canal de comunicação com a equipa (não há chat): o consultor pede e
 * escreve uma nota, o parceiro vê o mesmo pedido que o cliente vê e responde
 * com o ficheiro. A nota é a que o consultor escreveu PARA o cliente.
 *
 * Hierarquia visual: borda definida e faixa lateral na cor do estado
 * (âmbar = por enviar, verde = recebido), com o estado repetido em texto e
 * ícone — a cor sozinha não distingue para quem não a vê.
 */
import React from "react";
import { CheckCircle2, Clock } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import PartnerUploadBox from "@/components/partner/PartnerUploadBox";
import FicheiroDoCaso from "@/components/partner/FicheiroDoCaso";
import { cn } from "@/lib/utils";
import { progressoDoPedido } from "@/utils/partnerPortal";
import { convidaAJuntarMais, textoDoConvite } from "@/utils/pedidosDeDocumentos";

export default function PedidoDeDocumento({ caseId, pedido, desactivado = false }) {
  const pendente = pedido.estado === "pendente";
  const { enviados, esperados } = progressoDoPedido(pedido);
  // A quantidade é uma recomendação: o 1.º ficheiro cumpre o pedido e o cartão
  // continua a convidar a juntar mais (decisão da direcção, Out 2026).
  const convite = textoDoConvite(pedido);

  return (
    <Card
      data-testid={`pedido-${pedido.id}`}
      data-estado={pendente ? "pendente" : "recebido"}
      className={cn(
        "border-2 border-l-8 shadow-sm",
        pendente ? "border-border border-l-[hsl(var(--warning))]" : "border-border border-l-[hsl(var(--success))]"
      )}
    >
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-base font-semibold">{pedido.label}</p>
            {pedido.notes ? <p className="mt-1 whitespace-pre-line text-sm text-muted-foreground">{pedido.notes}</p> : null}
          </div>
          <div className="flex items-center gap-2">
            {esperados > 1 && (
              <span className="text-xs font-medium text-muted-foreground" aria-label={`${enviados} de ${esperados} ficheiros`}>
                {enviados}/{esperados}
              </span>
            )}
            {pendente ? (
              <Badge variant="outline" className="gap-1 border-2 border-[hsl(var(--warning))]"><Clock className="h-3 w-3" aria-hidden="true" />Pendente</Badge>
            ) : (
              <Badge variant="outline" className="gap-1 border-2 border-[hsl(var(--success))]"><CheckCircle2 className="h-3 w-3" aria-hidden="true" />Recebido</Badge>
            )}
          </div>
        </div>

        {pedido.ficheiros.length > 0 && (
          <ul className="space-y-2">
            {pedido.ficheiros.map((f) => (
              <FicheiroDoCaso key={f.id} caseId={caseId} ficheiro={f} dentroDoPedido />
            ))}
          </ul>
        )}

        {convite && (
          <p className="text-sm text-muted-foreground" data-testid={`convite-${pedido.id}`}>{convite}</p>
        )}

        {pendente && !desactivado && <PartnerUploadBox caseId={caseId} requestId={pedido.id} rotulo="Enviar ficheiro" />}
        {!pendente && !desactivado && convidaAJuntarMais(pedido) && (
          <PartnerUploadBox caseId={caseId} requestId={pedido.id} rotulo="Adicionar mais" />
        )}
      </CardContent>
    </Card>
  );
}
