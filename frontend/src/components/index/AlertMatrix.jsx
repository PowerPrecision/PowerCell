/**
 * AlertMatrix — a Matriz de Verificação do processo: avisos que NUNCA bloqueiam a indexação.
 *
 * A mensagem e a severidade vêm do servidor (tabela fechada no código); o ecrã não interpreta
 * códigos nem mostra texto de modelos. A JUSTIFICAÇÃO (`detail`: o valor, a data, a diferença) vem
 * do servidor também — calculada pelo código a partir dos factos — e aparece debaixo da mensagem:
 * sem ela «há movimentos que merecem confirmação» não diz o que confirmar. Dispensar um alerta não o apaga — fica registado e não
 * ressuscita quando a matriz volta a correr.
 *
 * DE QUE FICHEIRO: cada alerta traz `refs` (`{document_id, page}`) e o ecrã mostra-os — o nome do ficheiro
 * (da lista do próprio processo; o servidor nunca o repete no alerta), as páginas e um «Ver» que abre o
 * documento. Sem isto, «O saldo de um extrato não bate certo» não dizia de QUAL dos extratos.
 */
import { AlertTriangle, CheckCircle2, Eye, FileText, Info, ShieldAlert } from "lucide-react";

import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { alertasAbertos, ordenarAlertas, rotuloDaSeveridade } from "../../utils/indexRevisao";

const ICONE = {
  alerta: { Icone: ShieldAlert, classe: "text-destructive" },
  aviso: { Icone: AlertTriangle, classe: "text-[hsl(var(--warning))]" },
  info: { Icone: Info, classe: "text-muted-foreground" },
};

/** Os ficheiros a que um alerta se refere, sem repetições: `[{id, nome, paginas: [2, 3]}]`. */
export function ficheirosDoAlerta(alerta, ficheiros = []) {
  const refs = Array.isArray(alerta?.refs) ? alerta.refs : [];
  const porId = new Map();
  for (const r of refs) {
    if (!r || typeof r.document_id !== "string" || !r.document_id) continue;
    const actual = porId.get(r.document_id) || { id: r.document_id, paginas: [] };
    if (Number.isInteger(r.page) && !actual.paginas.includes(r.page)) actual.paginas.push(r.page);
    porId.set(r.document_id, actual);
  }
  const lista = Array.isArray(ficheiros) ? ficheiros : [];
  return [...porId.values()].map((f) => ({
    ...f,
    nome: lista.find((x) => x?.id === f.id)?.filename || "Documento",
    paginas: [...f.paginas].sort((a, b) => a - b),
  }));
}

export function AlertMatrix({ alertas, onDispensar, aDispensar = null, podeDispensar = true, ficheiros = [], onVerDocumento = null }) {
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
                    {ficheirosDoAlerta(a, ficheiros).map((f) => (
                      <p key={f.id} className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground" data-testid="alerta-ficheiro">
                        <FileText className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                        <span className="break-all">
                          Ficheiro: {f.nome}
                          {f.paginas.length > 0 && ` · pág. ${f.paginas.join(", ")}`}
                        </span>
                        {onVerDocumento && (
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            className="h-6 gap-1 px-2 text-xs"
                            onClick={() => onVerDocumento([{ id: f.id, rotulo: f.nome }], f.nome)}
                            aria-label={`Ver ficheiro do alerta — ${f.nome}`}
                          >
                            <Eye className="h-3 w-3" aria-hidden="true" />
                            Ver
                          </Button>
                        )}
                      </p>
                    ))}
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
