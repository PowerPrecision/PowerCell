/**
 * Um pedido de documentos do CRM, como o parceiro o vê.
 *
 * É o canal de comunicação com a equipa (não há chat): o consultor pede e
 * escreve uma nota, o parceiro vê o mesmo pedido que o cliente vê e responde
 * com o ficheiro. A nota é a que o consultor escreveu PARA o cliente.
 */
import React from "react";
import { CheckCircle2, Clock } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import PartnerUploadBox from "@/components/partner/PartnerUploadBox";
import FicheiroDoCaso from "@/components/partner/FicheiroDoCaso";
import { progressoDoPedido } from "@/utils/partnerPortal";

export default function PedidoDeDocumento({ caseId, pedido, desactivado = false }) {
  const pendente = pedido.estado === "pendente";
  const { enviados, esperados } = progressoDoPedido(pedido);

  return (
    <Card data-testid={`pedido-${pedido.id}`}>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="font-medium">{pedido.label}</p>
            {pedido.notes ? <p className="mt-1 whitespace-pre-line text-sm text-muted-foreground">{pedido.notes}</p> : null}
          </div>
          <div className="flex items-center gap-2">
            {esperados > 1 && (
              <span className="text-xs text-muted-foreground" aria-label={`${enviados} de ${esperados} ficheiros`}>
                {enviados}/{esperados}
              </span>
            )}
            {pendente ? (
              <Badge variant="outline" className="gap-1"><Clock className="h-3 w-3" aria-hidden="true" />Pendente</Badge>
            ) : (
              <Badge variant="secondary" className="gap-1"><CheckCircle2 className="h-3 w-3" aria-hidden="true" />Recebido</Badge>
            )}
          </div>
        </div>

        {pedido.ficheiros.length > 0 && (
          <ul className="space-y-1">
            {pedido.ficheiros.map((f) => (
              <FicheiroDoCaso key={f.id} caseId={caseId} ficheiro={f} />
            ))}
          </ul>
        )}

        {pendente && !desactivado && <PartnerUploadBox caseId={caseId} requestId={pedido.id} rotulo="Enviar ficheiro" />}
      </CardContent>
    </Card>
  );
}
