/**
 * IndexWorkstationPage — a bancada de um processo no Index (Lote 12, Fase 4).
 *
 * Ficheiros, metadados profissionais, matriz de verificação e as acções. O estado vem TODO do
 * servidor (`useIndexWorkstationQuery`); a página só o apresenta e traduz cliques em pedidos.
 *
 * REGRA: nada aqui bloqueia «Marcar como Indexado». O diálogo dos NIFs é opcional e a sua saída
 * «Marcar sem confirmar NIF» está sempre à mão.
 */
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, FileText, Loader2, PenLine } from "lucide-react";

import DashboardLayout from "../../layouts/DashboardLayout";
import { Alert, AlertDescription, AlertTitle } from "../../components/ui/alert";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Skeleton } from "../../components/ui/skeleton";
import { PageHeader } from "../../components/shared/PageHeader";
import { AlertMatrix } from "../../components/index/AlertMatrix";
import { EmployerNifDialog } from "../../components/index/EmployerNifDialog";
import { IndexActionsBar } from "../../components/index/IndexActionsBar";
import { ProfessionalReviewPanel } from "../../components/index/ProfessionalReviewPanel";
import { useIndexWorkstationQuery } from "../../hooks/queries/useIndexQueries";
import { useIndexMutations } from "../../hooks/mutations/useIndexMutations";
import {
  formatarDinheiro,
  haJobActivo,
  rotuloDoEstado,
  rotuloDoTipoDeAnalise,
  totalDeCamposARever,
  trabalhosSemNifConfirmado,
  valorDoCampo,
} from "../../utils/indexRevisao";

function ListaDeFicheiros({ ficheiros }) {
  if (ficheiros.length === 0) {
    return <p className="text-sm text-muted-foreground">Este processo ainda não tem documentos.</p>;
  }
  return (
    <ul className="divide-y divide-border">
      {ficheiros.map((f) => (
        <li key={f.id} className="flex flex-wrap items-center gap-2 py-2" data-testid="ficheiro-do-index">
          <FileText className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <span className="min-w-0 flex-1 break-words text-sm">{f.filename || "Documento"}</span>
          {f.category && <Badge variant="outline">{f.category}</Badge>}
          {rotuloDoTipoDeAnalise(f.analysis_type) &&
            (f.analysed ? (
              <Badge variant="secondary">Analisado</Badge>
            ) : (
              <Badge variant="outline">Por analisar</Badge>
            ))}
        </li>
      ))}
    </ul>
  );
}

export default function IndexWorkstationPage() {
  const { processId } = useParams();
  const navigate = useNavigate();
  const { bancada, isLoading, isError, error, refetch } = useIndexWorkstationQuery(processId);
  const m = useIndexMutations(processId);

  const [painelAberto, setPainelAberto] = useState(false);
  const [dialogoAberto, setDialogoAberto] = useState(false);

  const voltar = () => navigate("/index");

  if (isLoading) {
    return (
      <DashboardLayout>
        <div className="space-y-3" data-testid="index-bancada-a-carregar">
          <Skeleton className="h-10 w-1/2" />
          <Skeleton className="h-40 w-full" />
        </div>
      </DashboardLayout>
    );
  }

  if (isError || !bancada?.processo) {
    const naoExiste = error?.response?.status === 404;
    return (
      <DashboardLayout>
        <Alert variant="destructive" data-testid="index-bancada-erro">
          <AlertTitle>{naoExiste ? "Processo não encontrado" : "Não foi possível carregar o processo"}</AlertTitle>
          <AlertDescription className="flex items-center justify-between gap-3">
            <span>{naoExiste ? "Já não existe ou não tem acesso." : "Os dados não foram alterados. Tente de novo."}</span>
            <span className="flex gap-2">
              {!naoExiste && (
                <Button size="sm" variant="outline" onClick={() => refetch()}>
                  Tentar de novo
                </Button>
              )}
              <Button size="sm" variant="outline" onClick={voltar}>
                Voltar à fila
              </Button>
            </span>
          </AlertDescription>
        </Alert>
      </DashboardLayout>
    );
  }

  const { processo, ficheiros, trabalhos, alertas, jobsActivos } = bancada;
  const aRever = totalDeCamposARever(trabalhos);
  const semNif = trabalhosSemNifConfirmado(trabalhos);
  const ocupado = haJobActivo(jobsActivos);

  const marcar = (employers) =>
    m.marcarIndexado.mutate({ employers }, { onSuccess: () => setDialogoAberto(false) });
  // com NIFs por confirmar pergunta-se (opcional); sem eles marca-se logo
  const aoMarcar = () => (semNif.length > 0 ? setDialogoAberto(true) : marcar([]));

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <PageHeader
          icon={FileText}
          title={processo.client_name || "Processo"}
          titleBadge={<Badge variant="outline">{rotuloDoEstado(processo.index_status, processo.index_skipped)}</Badge>}
          description={processo.process_number ? `Processo #${processo.process_number}` : undefined}
          actions={
            <>
              <Button variant="ghost" onClick={voltar}>
                <ArrowLeft className="mr-1.5 h-4 w-4" aria-hidden="true" />
                Voltar à fila
              </Button>
              {processo.index_status === "pending" && (
                <Button variant="outline" disabled={m.claim.isPending} onClick={() => m.claim.mutate()}>
                  Reivindicar
                </Button>
              )}
              {processo.index_status === "in_review" && (
                <Button variant="outline" disabled={m.release.isPending} onClick={() => m.release.mutate()}>
                  Devolver à fila
                </Button>
              )}
            </>
          }
        />

        <IndexActionsBar
          processo={processo}
          jobsActivos={jobsActivos}
          aAnalisar={m.analisar.isPending}
          aExtrair={m.extrair.isPending}
          aMarcar={m.marcarIndexado.isPending}
          onAnalisar={() => m.analisar.mutate({ force: false })}
          onExtrair={() => m.extrair.mutate()}
          onMarcar={aoMarcar}
        />

        {ocupado && (
          <Alert data-testid="index-job-activo">
            <AlertTitle className="flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />A tratar os documentos
            </AlertTitle>
            <AlertDescription>
              Isto corre em segundo plano; recebe uma notificação no fim. Pode continuar a trabalhar.
            </AlertDescription>
          </Alert>
        )}

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Documentos</CardTitle>
            </CardHeader>
            <CardContent>
              <ListaDeFicheiros ficheiros={ficheiros} />
            </CardContent>
          </Card>

          <Card data-testid="metadados-profissionais">
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                Metadados profissionais
                {aRever > 0 && <Badge variant="secondary">{aRever} campo(s) a rever</Badge>}
              </CardTitle>
              <Button size="sm" variant="outline" onClick={() => setPainelAberto(true)}>
                <PenLine className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                Rever
              </Button>
            </CardHeader>
            <CardContent>
              {trabalhos.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Ainda sem dados extraídos. Use «Analisar» para ler os recibos de vencimento.
                </p>
              ) : (
                <ul className="divide-y divide-border">
                  {trabalhos.map((t) => (
                    <li key={t.job_id} className="py-2 text-sm">
                      <span className="font-medium">{valorDoCampo(t.employer_name) || "Entidade por identificar"}</span>
                      <span className="ml-2 text-muted-foreground">
                        {formatarDinheiro(valorDoCampo(t.net_salary))}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>

        <AlertMatrix
          alertas={alertas}
          aDispensar={m.dispensar.isPending ? m.dispensar.variables : null}
          onDispensar={(id) => m.dispensar.mutate(id)}
        />
      </div>

      <ProfessionalReviewPanel
        aberto={painelAberto}
        onFechar={() => setPainelAberto(false)}
        trabalhos={trabalhos}
        aGuardar={m.editar.isPending ? m.editar.variables?.jobId : null}
        onGuardar={(jobId, fields) => m.editar.mutate({ jobId, fields })}
      />
      <EmployerNifDialog
        aberto={dialogoAberto}
        onFechar={() => setDialogoAberto(false)}
        trabalhos={semNif}
        aMarcar={m.marcarIndexado.isPending}
        onMarcar={marcar}
      />
    </DashboardLayout>
  );
}
