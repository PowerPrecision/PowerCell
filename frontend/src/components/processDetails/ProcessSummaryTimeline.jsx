/**
 * PACOTE DO.1 — Timeline compacta no Resumo (Progressive Disclosure).
 * Histórico cronológico com linha vertical + nós; o filme completo
 * continua no separador Histórico.
 */
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { ScrollArea } from "../ui/scroll-area";
import { EmptyState } from "../ui/EmptyState";
import { GitBranch, History } from "lucide-react";
import { formatDateTime } from "../../lib/utils";
import { buildSummaryTimeline } from "../../utils/summaryTimeline";

const KIND_LABEL = {
  created: "Criação",
  status: "Fase",
  comment: "Nota",
  event: "Evento",
};

export default function ProcessSummaryTimeline({
  process,
  history,
  onOpenFullHistory,
  limit = 8,
}) {
  const events = buildSummaryTimeline(process, history, { limit });

  return (
    <Card className="border-border" data-testid="process-summary-timeline">
      <CardHeader className="pb-2 py-3 flex flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle className="text-sm flex items-center gap-2">
          <GitBranch className="h-4 w-4 text-muted-foreground" />
          Timeline
        </CardTitle>
        {typeof onOpenFullHistory === "function" && (
          <Button
            size="sm"
            variant="ghost"
            className="gap-1.5"
            onClick={onOpenFullHistory}
            data-testid="process-summary-timeline-full"
          >
            <History className="h-3.5 w-3.5" />
            Completo
          </Button>
        )}
      </CardHeader>
      <CardContent>
        {events.length === 0 ? (
          <EmptyState
            icon={GitBranch}
            title="Sem histórico"
            message="Ainda não há eventos registados neste processo."
            className="py-8"
          />
        ) : (
          <ScrollArea className="h-[240px] pr-3">
            <ol className="relative space-y-4 border-l border-border ml-2 pl-4">
              {events.map((item) => (
                <li key={item.id || `${item.kind}-${item.at}`} className="relative">
                  <span
                    className={`absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full border border-background ${
                      item.kind === "status"
                        ? "bg-primary"
                        : item.kind === "created"
                          ? "bg-accent-foreground"
                          : item.kind === "comment"
                            ? "bg-primary/70"
                            : "bg-muted-foreground"
                    }`}
                    aria-hidden
                  />
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium leading-tight">{item.title}</p>
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                      {KIND_LABEL[item.kind] || "Evento"}
                    </Badge>
                  </div>
                  {item.description && (
                    <p className="text-xs text-muted-foreground mt-0.5">{item.description}</p>
                  )}
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    {formatDateTime(item.at)}
                    {item.actor ? ` · ${item.actor}` : ""}
                  </p>
                </li>
              ))}
            </ol>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}
