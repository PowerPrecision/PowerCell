/**
 * O detalhe de um caso: o estado, os pedidos da equipa e os ficheiros.
 *
 * A comunicação com o consultor são os PEDIDOS DE DOCUMENTOS — exactamente
 * os que o cliente vê no seu portal. Não há chat e nada das notas internas
 * chega aqui: o servidor devolve um DTO por lista positiva.
 */
import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import PartnerUploadBox from "@/components/partner/PartnerUploadBox";
import PedidoDeDocumento from "@/components/partner/PedidoDeDocumento";
import FicheiroDoCaso from "@/components/partner/FicheiroDoCaso";
import { queryKeys } from "@/lib/queryClient";
import { obterCaso } from "@/services/partnerApi";
import {
  formatarData,
  mensagemDeErro,
  normalizarCaso,
  pedidosPendentes,
  pedidosRecebidos,
  variantDaEtapa,
} from "@/utils/partnerPortal";

export default function PartnerCasePage() {
  const { caseId } = useParams();
  const consulta = useQuery({
    queryKey: queryKeys.partner.caso(caseId),
    queryFn: () => obterCaso(caseId),
    retry: (tentativas, erro) => erro?.response?.status !== 404 && tentativas < 2,
  });

  const voltar = (
    <Link to="/parceiro" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft className="h-4 w-4" aria-hidden="true" />Voltar ao painel
    </Link>
  );

  if (consulta.isPending) {
    return (
      <div className="space-y-4">
        {voltar}
        <Skeleton className="h-20" /><Skeleton className="h-32" />
      </div>
    );
  }

  if (consulta.isError) {
    const naoExiste = consulta.error?.response?.status === 404;
    return (
      <div className="space-y-4">
        {voltar}
        <p role="alert" className="text-sm text-destructive">
          {naoExiste ? "Este caso não existe ou já não está disponível." : mensagemDeErro(consulta.error, "Não foi possível carregar o caso.")}
        </p>
      </div>
    );
  }

  const caso = normalizarCaso(consulta.data);
  const pendentes = pedidosPendentes(caso);
  const recebidos = pedidosRecebidos(caso);
  const eLead = caso.kind === "lead";

  return (
    <div className="space-y-6">
      {voltar}

      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-bold">{caso.client_name || "Sem nome"}</h1>
          <p className="text-sm text-muted-foreground">
            {[caso.process_number, caso.consultor_name && `Consultor: ${caso.consultor_name}`, `Actualizado em ${formatarData(caso.updated_at)}`]
              .filter(Boolean).join(" · ")}
          </p>
        </div>
        <Badge variant={variantDaEtapa(caso.etapa)}>{caso.etapa_label}</Badge>
      </header>

      {eLead && (
        <p className="rounded-md border border-border bg-secondary p-3 text-sm text-muted-foreground">
          Esta lead está a ser analisada pela nossa equipa. Pode já enviar os documentos que souber que vão ser pedidos.
        </p>
      )}

      <section aria-label="Pedidos de documentos" className="space-y-3">
        <h2 className="text-lg font-semibold">Pedidos de documentos</h2>
        {caso.pedidos.length === 0 ? (
          <p className="text-sm text-muted-foreground">Sem pedidos de documentos neste momento.</p>
        ) : (
          <>
            {pendentes.map((p) => <PedidoDeDocumento key={p.id} caseId={caso.id} pedido={p} />)}
            {recebidos.map((p) => <PedidoDeDocumento key={p.id} caseId={caso.id} pedido={p} />)}
          </>
        )}
      </section>

      <section aria-label="Outros ficheiros" className="space-y-3">
        <h2 className="text-lg font-semibold">Outros ficheiros</h2>
        <PartnerUploadBox caseId={caso.id} rotulo="Enviar ficheiros" />
        {caso.ficheiros.length > 0 && (
          <ul className="space-y-1">
            {caso.ficheiros.map((f) => <FicheiroDoCaso key={f.id} caseId={caso.id} ficheiro={f} />)}
          </ul>
        )}
      </section>
    </div>
  );
}
