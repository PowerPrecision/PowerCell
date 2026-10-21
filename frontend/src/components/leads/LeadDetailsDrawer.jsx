/**
 * «Ver Detalhes da Lead» — gaveta com TUDO o que o parceiro submeteu.
 *
 * Quem vai validar ou criar o processo precisa de ver o que veio antes de decidir: contactos, dados
 * pessoais, 2.º titular, situação financeira, imóvel, notas do parceiro e a lista de ficheiros (com o
 * comprovativo à cabeça). O rodapé tem as MESMAS acções da lista (Validar, Rejeitar, Ver comprovativo,
 * Criar Processo), pela mesma implementação (`useValidacaoFinanceira`) — mas só a quem a lista também
 * as dá.
 *
 * Não usa o TanStack Query: a gaveta pede o seu próprio recurso ao abrir e diz-se quando falha (um erro
 * de leitura nunca se apresenta como «a lead não tem dados»).
 */
import { useEffect, useState } from "react";
import { CheckCircle2, Eye, FileSearch, FileText, Loader2, Paperclip, XCircle } from "lucide-react";

import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "../ui/sheet";
import { getLeadDetails } from "../../services/api";
import { formatDateTime } from "../../lib/utils";
import { safeString } from "../../utils/safeString";
import { ficheirosDaLead, seccoesDaLead } from "../../utils/leadDetalhes";
import { podePrevisualizar } from "../../utils/previsualizacao";
import PreviewDoFicheiro from "./PreviewDoFicheiro";
import { podeDecidir } from "../../utils/validacaoFinanceira";
import { useValidacaoFinanceira } from "../validacao/useValidacaoFinanceira";

function Linha({ rotulo, valor }) {
  return (
    <div className="flex items-start justify-between gap-4 py-1.5 text-sm border-b last:border-b-0">
      <dt className="text-muted-foreground shrink-0">{rotulo}</dt>
      <dd className="text-right font-medium break-words min-w-0">{valor}</dd>
    </div>
  );
}

function Bloco({ titulo, children, testid }) {
  return (
    <section className="space-y-1" data-testid={testid}>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{titulo}</h3>
      <dl>{children}</dl>
    </section>
  );
}

/**
 * @param {Object} props
 * @param {Object|null} props.cliente        — a linha da lista (id, nome, has_process, …)
 * @param {Object|null} props.registo        — `{id, <validação>}` para o motor de decisão (ou null)
 * @param {string} props.papelEfectivo
 * @param {boolean} props.podeCriarProcesso
 * @param {Function} props.onAbertoChange    — (aberto) => void
 * @param {Function} props.onCriarProcesso   — (cliente) => void
 * @param {Function} props.onDecidido        — depois de validar/rejeitar
 */
export default function LeadDetailsDrawer({
  cliente,
  registo,
  papelEfectivo,
  podeCriarProcesso = false,
  onAbertoChange,
  onCriarProcesso,
  onDecidido,
}) {
  const id = cliente?.id || null;
  const [detalhes, setDetalhes] = useState(null);
  const [erro, setErro] = useState("");
  const [aCarregar, setACarregar] = useState(false);
  // O ficheiro aberto na pré-visualização (um de cada vez: duas áreas de scroll na mesma gaveta
  // tornavam-na impossível de percorrer).
  const [aVisualizar, setAVisualizar] = useState(null);

  useEffect(() => {
    if (!id) return undefined;
    let activo = true;
    setDetalhes(null);
    setErro("");
    setAVisualizar(null);
    setACarregar(true);
    getLeadDetails(id)
      .then((d) => { if (activo) setDetalhes(d); })
      .catch((e) => {
        if (!activo) return;
        const detail = e?.response?.data?.detail;
        setErro(typeof detail === "string" && detail ? detail : "Não foi possível carregar os detalhes da lead.");
      })
      .finally(() => { if (activo) setACarregar(false); });
    return () => { activo = false; };
  }, [id]);

  const decisao = useValidacaoFinanceira({
    registo: registo || { id },
    tipo: "lead",
    onDecidido: async (r) => {
      onAbertoChange?.(false);
      await onDecidido?.(r);
    },
  });

  const decide = podeDecidir(papelEfectivo) && decisao.porValidar;
  const seccoes = seccoesDaLead(detalhes);
  const ficheiros = ficheirosDaLead(detalhes);
  const contacto = detalhes?.contacto || {};

  return (
    <Sheet open={Boolean(id)} onOpenChange={onAbertoChange}>
      <SheetContent side="right" className="w-full sm:max-w-xl overflow-y-auto" data-testid="lead-details-drawer">
        <SheetHeader className="pr-6">
          <SheetTitle className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-primary" aria-hidden="true" />
            Detalhes da Lead
          </SheetTitle>
          <SheetDescription>
            {safeString(cliente?.nome) || "Lead"} — o que o parceiro submeteu, para analisar antes de decidir.
          </SheetDescription>
        </SheetHeader>

        <div className="mt-4 space-y-5">
          {aCarregar && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />A carregar…
            </p>
          )}
          {erro && <p role="alert" className="text-sm text-destructive" data-testid="lead-details-erro">{erro}</p>}

          {detalhes && (
            <>
              <Bloco titulo="Origem" testid="lead-bloco-origem">
                {detalhes.parceiro?.nome && <Linha rotulo="Parceiro" valor={safeString(detalhes.parceiro.nome)} />}
                {detalhes.empresa_destino && <Linha rotulo="Empresa de destino" valor={safeString(detalhes.empresa_destino)} />}
                {detalhes.tipo_de_pedido && <Linha rotulo="Tipo de pedido" valor={safeString(detalhes.tipo_de_pedido)} />}
                {detalhes.tem_imovel != null && <Linha rotulo="Tem imóvel" valor={detalhes.tem_imovel ? "Sim" : "Não"} />}
                {detalhes.created_at && <Linha rotulo="Submetida em" valor={formatDateTime(detalhes.created_at)} />}
                {detalhes.validacao?.estado && (
                  <Linha
                    rotulo="Validação"
                    valor={
                      <span data-testid="lead-validacao-estado">
                        {detalhes.validacao.estado}
                        {detalhes.validacao.motivo ? ` — ${safeString(detalhes.validacao.motivo)}` : ""}
                      </span>
                    }
                  />
                )}
              </Bloco>

              <Bloco titulo="Contactos" testid="lead-bloco-contactos">
                <Linha rotulo="Email" valor={safeString(contacto.email) || "—"} />
                <Linha rotulo="Telemóvel" valor={safeString(contacto.telefone) || "—"} />
              </Bloco>

              {seccoes.map((s) => (
                <Bloco key={s.chave} titulo={s.titulo} testid={`lead-bloco-${s.chave}`}>
                  {s.linhas.map((l) => <Linha key={l.campo} rotulo={l.rotulo} valor={l.valor} />)}
                </Bloco>
              ))}

              {detalhes.notas_do_parceiro && (
                <section className="space-y-1" data-testid="lead-bloco-notas">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Notas do parceiro</h3>
                  <p className="text-sm whitespace-pre-wrap rounded-md bg-muted/40 p-3">{safeString(detalhes.notas_do_parceiro)}</p>
                </section>
              )}

              <section className="space-y-1" data-testid="lead-bloco-ficheiros">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Ficheiros enviados ({ficheiros.length})
                </h3>
                {ficheiros.length === 0 ? (
                  <p className="text-sm text-muted-foreground">O parceiro ainda não enviou ficheiros.</p>
                ) : (
                  <ul className="space-y-1.5">
                    {ficheiros.map((f) => {
                      const chave = f.file_id || f.filename;
                      const aberto = Boolean(f.file_id) && aVisualizar === f.file_id;
                      return (
                        <li key={chave} className="rounded-md border px-3 py-2 text-sm" data-testid={`lead-ficheiro-${chave}`}>
                          <div className="flex items-center gap-2">
                            <Paperclip className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                            <span className="min-w-0 flex-1 truncate" title={safeString(f.filename)}>{safeString(f.filename)}</span>
                            {f.category && <span className="text-xs text-muted-foreground shrink-0">{safeString(f.category)}</span>}
                            {f.comprovativo && <Badge variant="secondary" className="shrink-0">Comprovativo</Badge>}
                            {podePrevisualizar(f) ? (
                              <Button
                                type="button"
                                variant={aberto ? "secondary" : "outline"}
                                size="sm"
                                className="h-7 shrink-0 gap-1 px-2"
                                aria-pressed={aberto}
                                aria-label={`Visualizar ${safeString(f.filename)}`}
                                onClick={() => setAVisualizar(aberto ? null : f.file_id)}
                                data-testid={`visualizar-${f.file_id}`}
                              >
                                <Eye className="h-3.5 w-3.5" aria-hidden="true" />Visualizar
                              </Button>
                            ) : (
                              <span className="shrink-0 text-xs text-muted-foreground" title="Este tipo de ficheiro não tem pré-visualização.">
                                Sem pré-visualização
                              </span>
                            )}
                          </div>
                          {aberto && (
                            <PreviewDoFicheiro leadId={id} ficheiro={f} onFechar={() => setAVisualizar(null)} />
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </section>
            </>
          )}
        </div>

        {cliente && (decide || (podeCriarProcesso && !cliente.has_process)) && (
          <SheetFooter className="mt-6 gap-2 sm:justify-start flex-wrap" data-testid="lead-details-accoes">
            {decide && (
              <>
                <Button type="button" size="sm" variant="outline" onClick={decisao.verComprovativo} disabled={decisao.aAbrirComprovativo} data-testid="drawer-ver-comprovativo">
                  {decisao.aAbrirComprovativo ? <Loader2 className="mr-1 h-4 w-4 animate-spin" aria-hidden="true" /> : <FileSearch className="mr-1 h-4 w-4" aria-hidden="true" />}
                  Ver comprovativo
                </Button>
                <Button type="button" size="sm" onClick={decisao.validar} disabled={decisao.aDecidir} data-testid="drawer-validar">
                  <CheckCircle2 className="mr-1 h-4 w-4" aria-hidden="true" />Validar
                </Button>
                {!decisao.rejeitado && (
                  <Button type="button" size="sm" variant="destructive" onClick={decisao.pedirRejeicao} disabled={decisao.aDecidir} data-testid="drawer-rejeitar">
                    <XCircle className="mr-1 h-4 w-4" aria-hidden="true" />Rejeitar
                  </Button>
                )}
              </>
            )}
            {podeCriarProcesso && !cliente.has_process && (
              <Button type="button" size="sm" onClick={() => onCriarProcesso?.(cliente)} data-testid="drawer-criar-processo">
                <FileText className="mr-1 h-4 w-4" aria-hidden="true" />Criar Processo
              </Button>
            )}
          </SheetFooter>
        )}
        {decisao.dialogo}
      </SheetContent>
    </Sheet>
  );
}
