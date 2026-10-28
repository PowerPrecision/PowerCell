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
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Download, ExternalLink, Eye, FileText, Loader2, PenLine, UserPlus } from "lucide-react";

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
import { PedirAlteracaoDeAtribuicao } from "../../components/index/PedirAlteracaoDeAtribuicao";
import { ProfessionalReviewPanel } from "../../components/index/ProfessionalReviewPanel";
import { UploadNaBancada } from "../../components/index/UploadNaBancada";
import VisualizadorDeDocumento from "../../components/index/VisualizadorDeDocumento";
import { useAuthOpcional } from "../../contexts/AuthContext";
import { useIndexWorkstationQuery } from "../../hooks/queries/useIndexQueries";
import { useIndexMutations } from "../../hooks/mutations/useIndexMutations";
import { useDescarregarDocumentos } from "../../hooks/useDescarregarDocumentos";
import { useIniciarTratamento } from "../../hooks/useIniciarTratamento";
import { queryKeys } from "../../lib/queryClient";
import {
  estadoDoFicheiroEmTexto,
  formatarDinheiro,
  haJobActivo,
  quantosPorLimpar,
  rotuloDoEstado,
  rotuloDoTipoDeAnalise,
  totalDeCamposARever,
  trabalhosSemNifConfirmado,
  valorDoCampo,
} from "../../utils/indexRevisao";

/**
 * Atalho para o processo original (QA Index, Out 2026): o nome do cliente e o número abrem o detalhe
 * do processo NUM SEPARADO — quem está a analisar documentos não perde a bancada. `rel` fecha o
 * `window.opener` (um separador aberto por `_blank` sem ele pode mexer na página de origem).
 */
const CLASSE_DA_LIGACAO = "underline-offset-4 hover:underline hover:text-primary focus-visible:underline";

function LigacaoAoProcesso({ processoId, children, ...resto }) {
  return (
    <Link
      to={`/processo/${processoId}`}
      target="_blank"
      rel="noopener noreferrer"
      className={CLASSE_DA_LIGACAO}
      {...resto}
    >
      {children}
      <ExternalLink className="ml-1 inline h-3.5 w-3.5 align-baseline opacity-60" aria-hidden="true" />
      <span className="sr-only"> (abre num novo separador)</span>
    </Link>
  );
}

const ROTULO_DO_TITULAR = { titular1: "1.º titular", titular2: "2.º titular" };

function ListaDeFicheiros({
  ficheiros,
  processoId,
  onVer,
  onDescarregar,
  emCurso,
  titulares = [],
  onMudarTitular,
  motivoSomenteLeitura,
}) {
  // os comprovativos do cliente que o Index já voltou a carregar não contam: escondidos, mas a um clique
  const [verSubstituidos, setVerSubstituidos] = useState(false);
  const substituidos = ficheiros.filter((f) => f.superseded === true).length;
  const visiveis = verSubstituidos ? ficheiros : ficheiros.filter((f) => f.superseded !== true);
  if (ficheiros.length === 0) {
    return <p className="text-sm text-muted-foreground">Este processo ainda não tem documentos.</p>;
  }
  return (
    <div className="space-y-2">
      {substituidos > 0 && (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-8 px-2 text-xs text-muted-foreground"
          aria-pressed={verSubstituidos}
          onClick={() => setVerSubstituidos((v) => !v)}
          data-testid="ver-substituidos"
        >
          {verSubstituidos
            ? "Esconder os documentos do cliente substituídos"
            : `Ver os documentos do cliente substituídos (${substituidos})`}
        </Button>
      )}
    <ul className="divide-y divide-border">
      {visiveis.map((f) => {
        const nome = f.filename || "Documento";
        const documento = { id: f.id, rotulo: nome, processId: processoId };
        const aDescarregar = emCurso?.has(`ficheiro:${f.id}`) === true;
        return (
          <li key={f.id} className="flex flex-wrap items-center gap-2 py-2" data-testid="ficheiro-do-index">
            <FileText className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            <span className={`min-w-[12rem] flex-1 break-words text-sm ${f.superseded ? "text-muted-foreground line-through" : ""}`}>
              {nome}
            </span>
            {f.superseded && (
              <Badge
                variant="secondary"
                data-testid="badge-substituido"
                title="Documento do cliente: já não conta, porque o Index carregou um deste tipo para este titular"
              >
                Substituído
              </Badge>
            )}
            {titulares.length > 0 && f.titular && (
              // o titular do ficheiro manda (não a conta que o enviou): o Index corrige-o aqui
              <select
                value={f.titular}
                onChange={(e) => onMudarTitular?.(f.id, e.target.value)}
                disabled={Boolean(motivoSomenteLeitura)}
                title={motivoSomenteLeitura}
                aria-label={`De quem é — ${nome}`}
                data-testid="ficheiro-titular"
                className="h-7 rounded-md border border-input bg-background px-1.5 text-xs"
              >
                {titulares.map((t) => (
                  <option key={t.id} value={t.id}>
                    {ROTULO_DO_TITULAR[t.id]}
                  </option>
                ))}
              </select>
            )}
            {f.category && <Badge variant="outline">{f.category}</Badge>}
            {rotuloDoTipoDeAnalise(f.analysis_type) &&
              (f.analysed ? (
                <Badge variant="secondary">Analisado</Badge>
              ) : (
                <Badge variant="outline">Por analisar</Badge>
              ))}
            <span className="flex items-center gap-1">
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-8 gap-1"
                onClick={() => onVer([documento], nome)}
                aria-label={`Ver documento — ${nome}`}
                data-testid="ficheiro-ver"
              >
                <Eye className="h-3.5 w-3.5" aria-hidden="true" />
                Ver
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-8 gap-1"
                disabled={aDescarregar}
                onClick={() => onDescarregar(`ficheiro:${f.id}`, [documento])}
                aria-label={`Download — ${nome}`}
                data-testid="ficheiro-download"
              >
                {aDescarregar ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                ) : (
                  <Download className="h-3.5 w-3.5" aria-hidden="true" />
                )}
                Download
              </Button>
            </span>
            {estadoDoFicheiroEmTexto(f) && (
              <span className="basis-full pl-6 text-xs text-muted-foreground" data-testid="estado-do-ficheiro">
                {estadoDoFicheiroEmTexto(f)}
              </span>
            )}
          </li>
        );
      })}
    </ul>
    </div>
  );
}

export default function IndexWorkstationPage() {
  const { processId } = useParams();
  const navigate = useNavigate();
  const { bancada, isLoading, isError, error, refetch } = useIndexWorkstationQuery(processId);
  const m = useIndexMutations(processId);
  const queryClient = useQueryClient();
  const auth = useAuthOpcional();
  const { descarregar, emCurso } = useDescarregarDocumentos();

  const [painelAberto, setPainelAberto] = useState(false);
  const [dialogoAberto, setDialogoAberto] = useState(false);
  const [aVer, setAVer] = useState({ documentos: [], titulo: "" });

  // Abrir a bancada é começar a trabalhar (já não há «Reivindicar»): só o indexador a quem o processo está
  // atribuído e enquanto está por começar; o servidor volta a decidir.
  useIniciarTratamento(
    processId,
    bancada?.processo?.assigned_to_me === true && bancada?.processo?.index_status === "pending",
  );

  // A equipa do Index trabalha a partir de «Os Meus Processos»; a gestão supervisiona a partir da fila.
  const papel = auth?.effectiveRole || auth?.user?.role;
  const daEquipa = papel === "indexacao";
  // «Voltar à fila» foi extinto com a fila-pool: quem trabalha como Index regressa a «Os meus processos»;
  // os outros perfis voltam pelo menu (ou pelo «Voltar» do browser, que devolve a lista como estava).
  const irParaOsMeus = () => navigate("/processos");
  const aoAdicionar = () => queryClient.invalidateQueries({ queryKey: queryKeys.index.workstation(processId) });

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
              {daEquipa && (
                <Button size="sm" variant="outline" onClick={irParaOsMeus}>
                  Os meus processos
                </Button>
              )}
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
  // «Atribuir a mim» (Out 2026): só o Index, só o que é de outro (ou de ninguém) e ainda está «Por indexar».
  const podeAssumir = daEquipa && processo.assigned_to_me !== true && processo.index_status === "pending";
  // Sem acções cruzadas (decisão do cliente, Out 2026): no processo de um colega o Index só consulta; para
  // agir assume-o primeiro. A gestão não é tocada e o servidor volta a decidir (403).
  const deOutro = daEquipa && processo.assigned_to_other === true;
  // a leitura é total e o ecrã não muda: só as acções ficam desligadas, com o motivo em tooltip
  const motivoDeOutro = deOutro
    ? `Processo atribuído a ${processo.assigned_indexacao_name || "outro indexador"}. ${
        podeAssumir
          ? "Para o analisar ou marcar como indexado, use primeiro «Atribuir a mim»."
          : "Já está em tratamento: só o indexador atribuído o pode alterar."
      }`
    : undefined;

  const marcar = (employers) =>
    m.marcarIndexado.mutate({ employers }, { onSuccess: () => setDialogoAberto(false) });
  // com NIFs por confirmar pergunta-se (opcional); sem eles marca-se logo
  const aoMarcar = () => (semNif.length > 0 ? setDialogoAberto(true) : marcar([]));

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <PageHeader
          icon={FileText}
          title={
            <LigacaoAoProcesso processoId={processo.id} data-testid="ligacao-cliente">
              {processo.client_name || "Processo"}
            </LigacaoAoProcesso>
          }
          titleBadge={
            <span className="flex flex-wrap items-center gap-1.5">
              <Badge variant="outline">{rotuloDoEstado(processo.index_status, processo.index_skipped)}</Badge>
              {processo.stagnant === true && (
                <Badge variant="secondary" data-testid="badge-estagnado" title="Sem actividade há vários dias — a chefia foi avisada">
                  Sem actividade
                </Badge>
              )}
            </span>
          }
          description={
            processo.process_number ? (
              <span>
                Processo{" "}
                <LigacaoAoProcesso processoId={processo.id} data-testid="ligacao-numero">
                  #{processo.process_number}
                </LigacaoAoProcesso>
              </span>
            ) : undefined
          }
          actions={
            daEquipa ? (
              <span className="flex flex-wrap items-center gap-2">
                {podeAssumir && (
                  <Button
                    onClick={() => m.assumir.mutate()}
                    disabled={m.assumir.isPending}
                    data-testid="botao-atribuir-a-mim"
                    title="Só processos «Por indexar» que ainda ninguém começou"
                  >
                    <UserPlus className="mr-1.5 h-4 w-4" aria-hidden="true" />
                    Atribuir a mim
                  </Button>
                )}
                {/* o Index não muda atribuições: pede à chefia (motivo opcional) */}
                <PedirAlteracaoDeAtribuicao processId={processo.id} />
                <Button variant="ghost" onClick={irParaOsMeus}>
                  <ArrowLeft className="mr-1.5 h-4 w-4" aria-hidden="true" />
                  Os meus processos
                </Button>
              </span>
            ) : undefined
          }
        />

        <IndexActionsBar
          somenteLeitura={deOutro}
          motivoSomenteLeitura={motivoDeOutro}
          processo={processo}
          jobsActivos={jobsActivos}
          aAnalisar={m.analisar.isPending}
          aExtrair={m.extrair.isPending}
          aSanitizar={m.sanitizar.isPending}
          aMarcar={m.marcarIndexado.isPending}
          porLimpar={quantosPorLimpar(ficheiros)}
          onAnalisar={() => m.analisar.mutate({ force: false })}
          onExtrair={() => m.extrair.mutate()}
          onSanitizar={() => m.sanitizar.mutate()}
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
            <CardContent className="space-y-4">
              <UploadNaBancada
                processId={processo.id}
                nomesExistentes={ficheiros.map((f) => f.filename)}
                titulares={processo.titulares || []}
                onConcluido={aoAdicionar}
              />
              <ListaDeFicheiros
                ficheiros={ficheiros}
                processoId={processo.id}
                onVer={(documentos, titulo) => setAVer({ documentos, titulo })}
                onDescarregar={descarregar}
                emCurso={emCurso}
                titulares={processo.titulares || []}
                onMudarTitular={(documentId, titular) => m.mudarTitular.mutate({ documentId, titular })}
                motivoSomenteLeitura={motivoDeOutro}
              />
            </CardContent>
          </Card>

          <Card data-testid="metadados-profissionais">
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                Metadados profissionais
                {aRever > 0 && <Badge variant="secondary">{aRever} campo(s) a rever</Badge>}
              </CardTitle>
              <span title={motivoDeOutro}>
                <Button size="sm" variant="outline" disabled={deOutro} onClick={() => setPainelAberto(true)} title={motivoDeOutro}>
                  <PenLine className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                  Rever
                </Button>
              </span>
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
                      {ROTULO_DO_TITULAR[t.titular] && (
                        <Badge variant="outline" className="ml-2" data-testid="emprego-titular">
                          {ROTULO_DO_TITULAR[t.titular]}
                        </Badge>
                      )}
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
          ficheiros={ficheiros}
          onVerDocumento={(documentos, titulo) =>
            setAVer({ documentos: documentos.map((d) => ({ ...d, processId: processo.id })), titulo })
          }
          podeDispensar={!deOutro}
          aDispensar={m.dispensar.isPending ? m.dispensar.variables : null}
          onDispensar={(id) => m.dispensar.mutate(id)}
        />
      </div>

      <VisualizadorDeDocumento
        documentos={aVer.documentos}
        titulo={aVer.titulo}
        onFechar={() => setAVer({ documentos: [], titulo: "" })}
        onDescarregar={descarregar}
        emCurso={emCurso}
      />
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
