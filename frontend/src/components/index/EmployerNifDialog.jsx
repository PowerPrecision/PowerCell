/**
 * EmployerNifDialog — pergunta o NIF das entidades patronais ao marcar como indexado.
 *
 * REGRA: o diálogo NUNCA bloqueia. «Marcar sem confirmar NIF» está sempre activo; um NIF
 * escrito sem forma de NIF é ignorado (o servidor ainda valida o dígito de controlo e, se não
 * passar, deixa o campo a rever). As sugestões vêm do directório GLOBAL de entidades (só NIF
 * e nome — nunca dados de clientes).
 */
import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "../ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { useIndexEmployersQuery } from "../../hooks/queries/useIndexQueries";
import { empregadoresParaMarcar, valorDoCampo } from "../../utils/indexRevisao";

function LinhaDeEntidade({ trabalho, valor, onChange }) {
  const nome = valorDoCampo(trabalho.employer_name) || "";
  const { entidades } = useIndexEmployersQuery(nome);
  const id = `nif-${trabalho.job_id}`;
  return (
    <div className="space-y-1.5" data-testid="entidade-sem-nif">
      <Label htmlFor={id}>{nome || "Entidade por identificar"}</Label>
      <Input id={id} value={valor} inputMode="numeric" placeholder="NIF (9 dígitos)" onChange={(e) => onChange(e.target.value)} />
      {entidades.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {entidades.slice(0, 3).map((e) => (
            <Button key={e.nif} type="button" size="sm" variant="outline" onClick={() => onChange(e.nif)}>
              {`Usar ${e.name} (${e.nif})`}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}

export function EmployerNifDialog({ aberto, onFechar, trabalhos, aMarcar, onMarcar }) {
  const [respostas, setRespostas] = useState({});

  return (
    <Dialog open={aberto} onOpenChange={(v) => !v && !aMarcar && onFechar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Confirmar o NIF das entidades patronais</DialogTitle>
          <DialogDescription>
            É opcional: pode marcar como indexado sem confirmar. O que ficar por confirmar vai para «Revisões Pendentes».
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {trabalhos.map((t) => (
            <LinhaDeEntidade
              key={t.job_id}
              trabalho={t}
              valor={respostas[t.job_id] || ""}
              onChange={(v) => setRespostas((r) => ({ ...r, [t.job_id]: v }))}
            />
          ))}
        </div>
        <DialogFooter className="gap-2 sm:gap-2">
          <Button variant="outline" disabled={aMarcar} onClick={() => onMarcar([])}>
            Marcar sem confirmar NIF
          </Button>
          <Button disabled={aMarcar} onClick={() => onMarcar(empregadoresParaMarcar(respostas))}>
            {aMarcar && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden="true" />}
            Marcar como indexado
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default EmployerNifDialog;
