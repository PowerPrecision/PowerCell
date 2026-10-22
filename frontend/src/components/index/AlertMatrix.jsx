/**
 * AlertMatrix — a Matriz de Verificação do processo: avisos que NUNCA bloqueiam a indexação.
 *
 * A mensagem e a severidade vêm do servidor (tabela fechada no código); o ecrã não interpreta
 * códigos nem mostra texto de modelos. A JUSTIFICAÇÃO (`detail`: o valor, a data, a diferença) vem
 * do servidor também — calculada pelo código a partir dos factos — e aparece debaixo da mensagem:
 * sem ela «há movimentos que merecem confirmação» não diz o que confirmar. Dispensar um alerta não o apaga — fica registado e não
 * ressuscita quando a matriz volta a correr.
 */
import { AlertTriangle, CheckCircle2, Info, ShieldAlert } from "lucide-react";

import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { alertasAbertos, ordenarAlertas, rotuloDaSeveridade } from "../../utils/indexRevisao";

const ICONE = {
  alerta: { Icone: ShieldAlert, classe: "text-destructive" },
  aviso: { Icone: AlertTriangle, classe: "text-[hsl(var(--warning))]" },
  info: { Icone: Info, classe: "text-muted-foreground" },
};

export function AlertMatrix({ alertas, onDispensar, aDispensar = null, podeDispensar = true }) {
  const ordenados = ordenarAlertas(alertas);
  const abertos = alertasAbertos(alertas).length;

  return (
    <Card data-testid="alert-matrix">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          Matriz de verificação
          <Badge variant={abertos ? "secondary" : "outline"}>{abertos} aberto(s)</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {ordenados.length === 0 ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <CheckCircle2 className="h-4 w-4 text-[hsl(var(--success))]" aria-hidden="true" />
            Sem avisos. Estes avisos nunca impedem de marcar como indexado.
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {ordenados.map((a) => {
              const { Icone, classe } = ICONE[a.severity] || ICONE.info;
              return (
                <li
                  key={a.id}
                  className={`flex items-start gap-3 py-2.5 ${a.dismissed ? "opacity-60" : ""}`}
                  data-testid="alerta-do-index"
                >
                  <Icone className={`mt-0.5 h-4 w-4 shrink-0 ${classe}`} aria-hidden="true" />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline">{rotuloDaSeveridade(a.severity)}</Badge>
                      {a.period && <span className="text-xs text-muted-foreground">{a.period}</span>}
                      {a.dismissed && <span className="text-xs text-muted-foreground">Dispensado</span>}
                    </div>
                    <p className="mt-1 text-sm">{a.message}</p>
                    {a.detail && (
                      <p className="mt-1 text-sm text-muted-foreground" data-testid="alerta-detalhe">
                        {a.detail}
                      </p>
                    )}
                  </div>
                  {podeDispensar && !a.dismissed && (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={aDispensar === a.id}
                      onClick={() => onDispensar(a.id)}
                      aria-label={`Dispensar alerta: ${a.message}`}
                    >
                      Dispensar
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export default AlertMatrix;
