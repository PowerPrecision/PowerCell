/**
 * ProfessionalReviewPanel — painel LATERAL de revisão dos metadados profissionais.
 *
 * Um cartão por trabalho (entidade patronal). Só se envia o que a pessoa MUDOU
 * (`edicoesDoTrabalho`): reenviar o que não tocou repunha o valor antigo por cima de uma
 * reanálise. «Confirmar como está» marca como revistos os campos em dúvida sem os alterar.
 * Guardar nunca bloqueia nada: é uma edição, não uma condição de indexação.
 */
import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "../ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "../ui/sheet";
import { RevisavelField } from "./RevisavelField";
import {
  CAMPOS_DO_TRABALHO,
  camposARever,
  edicoesDeConfirmacao,
  edicoesDoTrabalho,
  formularioDoTrabalho,
} from "../../utils/indexRevisao";

function CartaoDoTrabalho({ trabalho, aGuardar, onGuardar }) {
  const [formulario, setFormulario] = useState(() => formularioDoTrabalho(trabalho));
  // reanálise ou edição noutro sítio: o formulário volta a partir do que o servidor diz
  useEffect(() => setFormulario(formularioDoTrabalho(trabalho)), [trabalho]);

  const alteracoes = edicoesDoTrabalho(trabalho, formulario);
  const emDuvida = camposARever(trabalho);
  const aGuardarEste = aGuardar === trabalho.job_id;

  return (
    <section className="space-y-3 rounded-lg border border-border p-4" data-testid="trabalho-do-index">
      <h3 className="text-sm font-semibold">
        {formulario.employer_name || "Entidade por identificar"}
        {trabalho.period ? <span className="ml-2 font-normal text-muted-foreground">({trabalho.period})</span> : null}
      </h3>
      {CAMPOS_DO_TRABALHO.map(({ chave, rotulo, tipo }) => (
        <RevisavelField
          key={chave}
          id={`${trabalho.job_id}-${chave}`}
          rotulo={rotulo}
          tipo={tipo}
          campo={trabalho[chave]}
          valor={formulario[chave]}
          disabled={aGuardarEste}
          onChange={(v) => setFormulario((f) => ({ ...f, [chave]: v }))}
        />
      ))}
      <div className="flex flex-wrap justify-end gap-2 pt-1">
        {emDuvida.length > 0 && Object.keys(alteracoes).length === 0 && (
          <Button
            variant="outline"
            size="sm"
            disabled={aGuardarEste}
            onClick={() => onGuardar(trabalho.job_id, edicoesDeConfirmacao(trabalho, emDuvida))}
          >
            Confirmar como está
          </Button>
        )}
        <Button
          size="sm"
          disabled={aGuardarEste || Object.keys(alteracoes).length === 0}
          onClick={() => onGuardar(trabalho.job_id, alteracoes)}
        >
          {aGuardarEste && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
          Guardar alterações
        </Button>
      </div>
    </section>
  );
}

export function ProfessionalReviewPanel({ aberto, onFechar, trabalhos, aGuardar = null, onGuardar }) {
  return (
    <Sheet open={aberto} onOpenChange={(v) => !v && onFechar()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-lg" data-testid="painel-de-revisao">
        <SheetHeader>
          <SheetTitle>Revisão dos metadados profissionais</SheetTitle>
          <SheetDescription>
            A IA propõe, a pessoa dispõe. O que corrigir aqui não é substituído por uma nova análise.
          </SheetDescription>
        </SheetHeader>
        <div className="mt-4 space-y-4">
          {trabalhos.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Ainda não há dados extraídos. Use «Analisar» para ler os recibos de vencimento.
            </p>
          ) : (
            trabalhos.map((t) => <CartaoDoTrabalho key={t.job_id} trabalho={t} aGuardar={aGuardar} onGuardar={onGuardar} />)
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

export default ProfessionalReviewPanel;
