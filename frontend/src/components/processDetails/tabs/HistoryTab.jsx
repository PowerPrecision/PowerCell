/**
 * HistoryTab — separador "Histórico" da página de detalhes do processo.
 *
 * PONTO 9: O HISTÓRICO É SÓ DE LEITURA
 * ====================================
 * Este separador é uma **linha temporal gerada pelo sistema** — uma
 * trilha de auditoria. Não tem, e não pode voltar a ter, UI de adição de
 * notas ou atividades.
 *
 * O que saiu daqui e para onde foi:
 *
 *   * o diálogo "Registar Atividade / Nota" foi **removido**. O local
 *     oficial das notas do consultor passou a ser, exclusivamente, o
 *     campo Observações do separador **Resumo** — que é também o que a
 *     coluna "Notas do Consultor" da listagem espelha;
 *   * o botão "Nota de voz" **mudou-se** para o cartão de Observações,
 *     ao lado das notas escritas. Não foi apagado: uma nota ditada é
 *     uma nota, e o sítio das notas é o Resumo.
 *
 * O que FICA: a eliminação de um comentário no `UnifiedAuditTrail`.
 * Depois desta mudança já ninguém consegue criar comentários por aqui,
 * pelo que esse botão só alcança registos antigos e notas de voz — é a
 * única forma de limpar uma entrada errada, e tirá-lo deixaria a
 * trilha sem maneira de a corrigir. Se a regra for "nem apagar", é uma
 * decisão a tomar de propósito, não um resto desta.
 *
 * PACOTE DS (histórico): timeline de fases + tabela rica de auditoria
 * (quem / o quê / quando / detalhes).
 */
import { Card, CardContent, CardHeader, CardTitle } from "../../ui/card";
import { History, Lock } from "lucide-react";
import ProcessTimeline from "../../ProcessTimeline";
import UnifiedAuditTrail from "../../UnifiedAuditTrail";

export default function HistoryTab({
  processId,
  process,
  history,
  workflowStatuses,
  activities,
  handleDeleteComment,
  user,
}) {
  return (
    <div className="space-y-6">
      <ProcessTimeline
        processId={processId}
        currentStatus={process?.status}
        history={history}
        workflowStatuses={workflowStatuses}
      />

      <Card className="border-border">
        <CardHeader className="pb-2 py-3 flex flex-row items-center justify-between gap-2 space-y-0">
          <CardTitle className="text-sm flex items-center gap-2">
            <History className="h-4 w-4 text-primary" />
            Histórico de Auditoria
          </CardTitle>
          {/* A ausência do botão explica-se. Sem isto, quem procurar o
              "Registar Atividade" conclui que a página está partida —
              e o Resumo continua a ser o sítio certo sem ninguém o
              dizer. */}
          <span
            className="flex items-center gap-1.5 text-[11px] text-muted-foreground"
            data-testid="historico-so-leitura"
          >
            <Lock className="h-3 w-3" aria-hidden="true" />
            Registo automático — as notas escrevem-se no Resumo
          </span>
        </CardHeader>
        <CardContent className="pt-0 pb-3">
          {/* BUGFIX (visual): maxHeight alinhado com o contentor de scroll
              nativo do UnifiedAuditTrail (overflow-x-auto + overflow-y-auto). */}
          <UnifiedAuditTrail
            history={history}
            activities={activities}
            maxHeight="600px"
            currentUser={user}
            onDeleteComment={handleDeleteComment}
          />
        </CardContent>
      </Card>
    </div>
  );
}
