/**
 * AiLogTab — separador «Log da IA» da página de detalhes do processo.
 *
 * A IA deixa de ser uma caixa preta: este separador lista, do mais recente para o mais
 * antigo, o que o motor fez sobre os documentos do processo — quando leu um documento, o que
 * concluiu (categoria e NOMES dos campos, nunca valores), e porque falhou ou nem chegou a correr.
 *
 * REGRAS
 *   * É uma TRILHA, só de leitura. A única acção é «Reanalisar», que repete a revisão com IA de
 *     UM documento — uma chamada paga. O botão aparece a quem o SERVIDOR autoriza
 *     (`pode_reanalisar`: a mesma função que recusa nas rotas) E cujo perfil activo é de gestão
 *     (`podeUsarFerramentasDeIA`); o consultor atribuído vê o log mas não o botão (decisão da
 *     direcção, QA-5). Num processo fechado o botão não existe (o servidor recusaria).
 *   * Um erro de LEITURA nunca se apresenta como «sem actividade»: diz-se, com «Tentar de novo».
 *   * O ecrã mostra a mensagem do servidor (`motivo_mensagem`), nunca o texto de uma excepção.
 *   * Pede os dados só quando o separador está aberto (o Radix só monta o separador activo).
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleSlash,
  Loader2,
  RefreshCw,
} from "lucide-react";

import { Badge } from "../../ui/badge";
import { Button } from "../../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../ui/card";
import { analyzeDocumentForReview, getProcessAiLog } from "../../../services/api";
import { queryKeys } from "../../../lib/queryClient";
import { podeUsarFerramentasDeIA } from "../../../utils/permissaoDeIA";
import {
  FILTROS,
  conclusaoDaLinha,
  formatarQuando,
  gatilhoDaLinha,
  linhaPodeSerReanalisada,
  mensagemDaReanalise,
  normalizarPagina,
  notaDaLinha,
  rotuloDoEstado,
  tituloDaLinha,
} from "../../../utils/logDaIA";

const TAMANHO_DA_PAGINA = 30;

const ICONE_DO_ESTADO = {
  sucesso: { Icone: CheckCircle2, classe: "text-[hsl(var(--success))]" },
  falha: { Icone: AlertTriangle, classe: "text-destructive" },
  saltado: { Icone: CircleSlash, classe: "text-muted-foreground" },
};

function LinhaDoLog({ linha, podeReanalisar, aReanalisar, onReanalisar }) {
  const { Icone, classe } = ICONE_DO_ESTADO[linha.estado] || ICONE_DO_ESTADO.saltado;
  const conclusao = conclusaoDaLinha(linha);
  const nota = notaDaLinha(linha);
  const campos = Array.isArray(linha.campos) ? linha.campos : [];

  return (
    <li className="flex gap-3 border-b border-border py-3 last:border-b-0" data-testid="linha-do-log">
      <Icone className={`mt-0.5 h-4 w-4 shrink-0 ${classe}`} aria-hidden="true" />
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium break-words">{tituloDaLinha(linha)}</span>
          <Badge variant={linha.estado === "falha" ? "destructive" : "outline"}>{rotuloDoEstado(linha.estado)}</Badge>
        </div>
        {conclusao && <p className="text-sm text-foreground">{conclusao}</p>}
        {nota && (
          <p className={`text-xs ${linha.estado === "falha" ? "text-destructive" : "text-muted-foreground"}`}>{nota}</p>
        )}
        {campos.length > 0 && (
          <p className="text-xs text-muted-foreground">
            Campos lidos: {campos.join(", ")}
          </p>
        )}
        <p className="text-xs text-muted-foreground">
          {formatarQuando(linha.created_at)} · {gatilhoDaLinha(linha)}
        </p>
      </div>
      {podeReanalisar && linhaPodeSerReanalisada(linha) && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-8 shrink-0 gap-1"
          disabled={aReanalisar}
          onClick={() => onReanalisar(linha)}
          aria-label={`Reanalisar ${linha.ficheiro || "documento"} com IA`}
        >
          {aReanalisar ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />}
          Reanalisar
        </Button>
      )}
    </li>
  );
}

/**
 * @param {Object} props
 * @param {string} props.processId
 * @param {string} [props.effectiveRole] perfil activo.
 * @param {boolean} [props.processoFechado] processo em fase terminal: sem acções.
 * @param {Function} [props.onReanalisado] chamado depois de uma reanálise (refresca os Documentos).
 */
export default function AiLogTab({ processId, effectiveRole, processoFechado = false, onReanalisado }) {
  const queryClient = useQueryClient();
  const [pagina, setPagina] = useState(1);
  const [estado, setEstado] = useState("");
  const [documentoEmCurso, setDocumentoEmCurso] = useState(null);

  const consulta = useQuery({
    queryKey: queryKeys.processes.aiLog(processId, pagina, estado),
    queryFn: async () => {
      const { data } = await getProcessAiLog(processId, {
        page: pagina,
        size: TAMANHO_DA_PAGINA,
        ...(estado ? { estado } : {}),
      });
      return data;
    },
    enabled: Boolean(processId),
    placeholderData: (anterior) => anterior,
  });

  const dados = normalizarPagina(consulta.data);
  const podeReanalisar = podeUsarFerramentasDeIA({
    effectiveRole,
    permissaoDoServidor: consulta.data ? consulta.data.pode_reanalisar : undefined,
    somenteLeitura: processoFechado,
  }) && dados.podeReanalisar;

  const reanalisar = useMutation({
    mutationFn: (linha) => analyzeDocumentForReview(linha.documento_id).then((r) => r.data),
    onMutate: (linha) => setDocumentoEmCurso(linha.documento_id),
    onSuccess: (resposta) => {
      const { tipo, texto } = mensagemDaReanalise(resposta);
      toast[tipo === "erro" ? "error" : tipo](texto);
      onReanalisado?.();
    },
    onError: () => {
      toast.error("A reanálise falhou. Tente de novo dentro de instantes.");
    },
    onSettled: () => {
      setDocumentoEmCurso(null);
      // A reanálise escreveu uma linha nova (sucesso OU falha): refaz todas as páginas/filtros.
      queryClient.invalidateQueries({ queryKey: queryKeys.processes.aiLogAll(processId) });
    },
  });

  const mudarFiltro = (valor) => {
    setEstado(valor);
    setPagina(1);
  };

  return (
    <Card className="border-border" data-testid="log-da-ia">
      <CardHeader className="space-y-3 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Bot className="h-4 w-4 text-primary" aria-hidden="true" />
          Log da IA
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Registo do que a IA fez neste processo: quando leu cada documento, o que concluiu e porque
          falhou. Só mostra os nomes dos campos lidos, nunca os valores.
        </p>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filtrar por estado">
          {FILTROS.map((f) => (
            <Button
              key={f.valor || "todas"}
              type="button"
              size="sm"
              variant={estado === f.valor ? "default" : "outline"}
              className="h-7 px-2.5 text-xs"
              aria-pressed={estado === f.valor}
              onClick={() => mudarFiltro(f.valor)}
            >
              {f.rotulo}
            </Button>
          ))}
        </div>
      </CardHeader>

      <CardContent>
        {consulta.isLoading && (
          <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground" role="status">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />A carregar o Log da IA…
          </p>
        )}

        {consulta.isError && !consulta.data && (
          <div role="alert" className="space-y-2 py-4">
            <p className="text-sm text-destructive">Não foi possível carregar o Log da IA.</p>
            <Button type="button" variant="outline" size="sm" onClick={() => consulta.refetch()}>
              Tentar de novo
            </Button>
          </div>
        )}

        {!consulta.isLoading && !consulta.isError && dados.items.length === 0 && (
          <p className="py-6 text-sm text-muted-foreground" data-testid="log-da-ia-vazio">
            {estado
              ? "Nenhuma acção da IA com este estado."
              : "A IA ainda não registou nenhuma acção neste processo. Os documentos que entrarem a partir de agora aparecem aqui."}
          </p>
        )}

        {dados.items.length > 0 && (
          <ul aria-label="Acções da IA">
            {dados.items.map((linha) => (
              <LinhaDoLog
                key={linha.id}
                linha={linha}
                podeReanalisar={podeReanalisar}
                aReanalisar={reanalisar.isPending && documentoEmCurso === linha.documento_id}
                onReanalisar={(l) => reanalisar.mutate(l)}
              />
            ))}
          </ul>
        )}

        {dados.paginas > 1 && (
          <div className="flex items-center justify-between pt-3">
            <Button type="button" variant="outline" size="sm" disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)}>
              <ChevronLeft className="h-4 w-4" aria-hidden="true" />Anterior
            </Button>
            <span className="text-xs text-muted-foreground">
              Página {dados.page} de {dados.paginas} · {dados.total} acções
            </span>
            <Button type="button" variant="outline" size="sm" disabled={pagina >= dados.paginas} onClick={() => setPagina((p) => p + 1)}>
              Seguinte<ChevronRight className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>
        )}

        {podeReanalisar === false && !processoFechado && dados.items.some(linhaPodeSerReanalisada) && (
          <p className="pt-3 text-xs text-muted-foreground">
            A reanálise com IA é uma chamada paga e está reservada à gestão (Master, Admin, CEO e Diretor).
          </p>
        )}
      </CardContent>
    </Card>
  );
}
