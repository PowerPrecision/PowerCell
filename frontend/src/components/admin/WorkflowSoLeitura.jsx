/**
 * WorkflowSoLeitura — as fases do workflow da rede, só para consulta.
 *
 * O Diretor vê o painel da sua empresa sem gravar (Flavio, Nov 2026, pergunta 3a).
 * O editor (`WorkflowEditor`) pede `/workflow-statuses/editor`, que é de quem edita;
 * aqui lê-se a lista que todos os perfis da equipa já lêem (`/workflow-statuses`).
 */
import { useEffect, useState } from "react";
import { Badge } from "../ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { getWorkflowStatuses } from "../../services/api";
import { extractErrorMessage } from "../../utils/extractErrorMessage";

export default function WorkflowSoLeitura() {
  const [fases, setFases] = useState(null);
  const [erro, setErro] = useState(null);

  useEffect(() => {
    let cancelado = false;
    getWorkflowStatuses()
      .then((res) => {
        if (cancelado) return;
        const lista = Array.isArray(res?.data) ? res.data : res?.data?.statuses || [];
        setFases([...lista].sort((a, b) => (a.order ?? 0) - (b.order ?? 0)));
      })
      .catch((e) => {
        if (!cancelado) setErro(extractErrorMessage(e?.response?.data?.detail, "Não foi possível carregar o workflow."));
      });
    return () => {
      cancelado = true;
    };
  }, []);

  return (
    <Card data-testid="workflow-so-leitura">
      <CardHeader>
        <CardTitle className="text-lg">Fases do workflow</CardTitle>
        <CardDescription>
          Só consulta. O workflow é partilhado pelas empresas da rede e é alterado pelo CEO ou pelo Admin.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {erro && <p className="text-sm text-destructive">{erro}</p>}
        {!erro && fases === null && <p className="text-sm text-muted-foreground">A carregar…</p>}
        {fases && fases.length === 0 && <p className="text-sm text-muted-foreground">Sem fases definidas.</p>}
        {fases && fases.length > 0 && (
          <ol className="space-y-1.5">
            {fases.map((f) => (
              <li
                key={f.id || f.name}
                className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-sm"
              >
                <span className="flex items-center gap-2 min-w-0">
                  <span className="w-6 shrink-0 text-right text-muted-foreground tabular-nums">{f.order}</span>
                  <span className="truncate text-foreground">{f.label || f.name}</span>
                </span>
                {f.macro_phase && <Badge variant="outline">{f.macro_phase}</Badge>}
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
