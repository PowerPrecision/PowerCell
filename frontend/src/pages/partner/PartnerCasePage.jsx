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
import { AlertTriangle, ArrowLeft, CheckCircle2, Clock, FileCheck2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import ClientDataForm from "@/components/partner/ClientDataForm";
import PartnerUploadBox from "@/components/partner/PartnerUploadBox";
import PedidoDeDocumento from "@/components/partner/PedidoDeDocumento";
import FicheiroDoCaso from "@/components/partner/FicheiroDoCaso";
import { queryKeys } from "@/lib/queryClient";
import { obterCaso } from "@/services/partnerApi";
import {
  CATEGORIA_DO_COMPROVATIVO,
  ETAPA_DEVOLVIDA,
  formatarData,
  leadExpirada,
  leadRetida,
  mensagemDeErro,
  normalizarCaso,
  separarDocumentos,
  variantDaEtapa,
} from "@/utils/partnerPortal";

/** O aviso do estado da lead — o que o parceiro tem de fazer a seguir. */
function AvisoDaLead({ caso }) {
  if (caso.kind !== "lead") return null;

  if (leadExpirada(caso)) {
    return (
      <p role="status" className="flex items-start gap-2 rounded-md border border-border bg-secondary p-3 text-sm text-muted-foreground" data-testid="aviso-expirada">
        <Clock className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        Esta lead expirou por inactividade (60 dias sem edições nem envios). Já não pode ser trabalhada — submeta uma nova lead.
      </p>
    );
  }
  if (leadRetida(caso)) {
    const devolvida = caso.etapa === ETAPA_DEVOLVIDA;
    return (
      <div role="status" className="space-y-1 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm" data-testid={devolvida ? "aviso-devolvida" : "aviso-pendente"}>
        <p className="flex items-start gap-2 font-medium text-destructive">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          {devolvida ? "A nossa equipa devolveu esta lead." : "Esta lead está retida do seu lado."}
        </p>
        {devolvida && caso.motivo_da_devolucao ? <p>Motivo: {caso.motivo_da_devolucao}</p> : null}
        <p className="text-muted-foreground">
          {devolvida
            ? "Corrija o que for preciso e envie um novo Comprovativo de Pagamento."
            : "Só segue para a nossa equipa depois de enviar o Comprovativo de Pagamento."}
        </p>
      </div>
    );
  }
  return (
    <p className="rounded-md border border-border bg-secondary p-3 text-sm text-muted-foreground">
      Esta lead está a ser analisada pela nossa equipa. Pode já enviar os documentos que souber que vão ser pedidos.
    </p>
  );
}

/** O Comprovativo de Pagamento: a única coisa que liberta uma lead retida. */
function ComprovativoObrigatorio({ caseId }) {
  return (
    <Card data-testid="comprovativo-obrigatorio" className="border-destructive/40">
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="font-medium">Comprovativo de Pagamento</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Obrigatório. Enquanto não o enviar, a lead fica retida e a nossa equipa não a vê.
            </p>
          </div>
          <Badge variant="destructive" className="gap-1"><Clock className="h-3 w-3" aria-hidden="true" />Obrigatório</Badge>
        </div>
        <PartnerUploadBox
          caseId={caseId}
          categoria={CATEGORIA_DO_COMPROVATIVO}
          rotulo="Enviar comprovativo"
          testId="comprovativo"
        />
      </CardContent>
    </Card>
  );
}

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
  const { pendentes, pedidosSubmetidos, ficheirosSubmetidos } = separarDocumentos(caso);
  const eLead = caso.kind === "lead";
  const expirada = leadExpirada(caso);
  const retida = leadRetida(caso);
  const nadaPendente = pendentes.length === 0 && !retida;
  const nadaSubmetido = pedidosSubmetidos.length === 0 && ficheirosSubmetidos.length === 0;

  const documentos = (
    <div className="space-y-8">
      <section aria-label="Documentos pendentes" className="space-y-3">
        <h2 className="text-lg font-semibold">Pendentes</h2>
        {retida && <ComprovativoObrigatorio caseId={caso.id} />}
        {pendentes.map((p) => <PedidoDeDocumento key={p.id} caseId={caso.id} pedido={p} desactivado={expirada} />)}
        {nadaPendente && <p className="text-sm text-muted-foreground">Sem documentos pendentes neste momento.</p>}
      </section>

      <section aria-label="Documentos submetidos" className="space-y-3">
        <h2 className="text-lg font-semibold">Submetidos</h2>
        {pedidosSubmetidos.map((p) => <PedidoDeDocumento key={p.id} caseId={caso.id} pedido={p} desactivado={expirada} />)}
        {ficheirosSubmetidos.length > 0 && (
          <ul className="space-y-1">
            {ficheirosSubmetidos.map((f) => <FicheiroDoCaso key={f.id} caseId={caso.id} ficheiro={f} />)}
          </ul>
        )}
        {nadaSubmetido && <p className="text-sm text-muted-foreground">Ainda não submeteu nenhum documento.</p>}
      </section>

      {!expirada && (
        <section aria-label="Enviar outro documento" className="space-y-3">
          <h2 className="text-lg font-semibold">Enviar outro documento</h2>
          <PartnerUploadBox caseId={caso.id} rotulo="Enviar ficheiros" categorias={caso.categorias} />
        </section>
      )}
    </div>
  );

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

      <AvisoDaLead caso={caso} />

      {eLead ? (
        <Tabs defaultValue="documentos" className="space-y-4">
          <TabsList>
            <TabsTrigger value="documentos"><FileCheck2 className="mr-2 h-4 w-4" aria-hidden="true" />Documentos</TabsTrigger>
            <TabsTrigger value="dados"><CheckCircle2 className="mr-2 h-4 w-4" aria-hidden="true" />Dados do cliente</TabsTrigger>
          </TabsList>
          <TabsContent value="documentos">{documentos}</TabsContent>
          <TabsContent value="dados"><ClientDataForm caseId={caso.id} /></TabsContent>
        </Tabs>
      ) : (
        documentos
      )}
    </div>
  );
}
