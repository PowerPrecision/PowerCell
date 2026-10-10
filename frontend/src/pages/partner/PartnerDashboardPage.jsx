/**
 * O painel do parceiro: o funil (leads → em aprovação → escriturados), as
 * métricas simples e a lista dos SEUS casos.
 *
 * Tudo o que aqui aparece é calculado pelo servidor sobre os casos que lhe
 * foram atribuídos — o ecrã não filtra nada do que recebe. Sem dados
 * financeiros: o parceiro paga-nos o serviço, não recebe comissões.
 */
import React, { useEffect, useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight, Inbox, Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { queryKeys } from "@/lib/queryClient";
import { listarCasos, obterPainel } from "@/services/partnerApi";
import {
  caminhoDoCaso,
  formatarConversao,
  formatarData,
  mensagemDeErro,
  normalizarCasos,
  normalizarPainel,
  variantDaEtapa,
} from "@/utils/partnerPortal";

const TAMANHO_DA_PAGINA = 15;

function Metrica({ rotulo, valor, destaque = false }) {
  return (
    <Card className={cn(destaque && "border-primary")}>
      <CardContent className="p-4">
        <p className="text-xs uppercase tracking-wide text-muted-foreground">{rotulo}</p>
        <p className="mt-1 text-2xl font-semibold">{valor}</p>
      </CardContent>
    </Card>
  );
}

export default function PartnerDashboardPage() {
  const [etapa, setEtapa] = useState("");
  const [texto, setTexto] = useState("");
  const [pesquisa, setPesquisa] = useState("");
  const [pagina, setPagina] = useState(1);

  // A pesquisa só parte 300 ms depois da última tecla.
  useEffect(() => {
    const t = setTimeout(() => {
      setPesquisa(texto.trim());
      setPagina(1);
    }, 300);
    return () => clearTimeout(t);
  }, [texto]);

  const painelQ = useQuery({ queryKey: queryKeys.partner.painel(), queryFn: obterPainel });
  const filtros = { etapa, q: pesquisa, page: pagina, size: TAMANHO_DA_PAGINA };
  const casosQ = useQuery({
    queryKey: queryKeys.partner.casos(filtros),
    queryFn: () => listarCasos(filtros),
    placeholderData: keepPreviousData,
  });

  const painel = normalizarPainel(painelQ.data);
  const casos = normalizarCasos(casosQ.data);
  const funilPorEtapa = Object.fromEntries(painel.funil.map((e) => [e.etapa, e.total]));

  return (
    <div className="space-y-6">
      <section aria-label="Resumo" className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {painelQ.isPending ? (
          Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-20" />)
        ) : (
          <>
            <Metrica rotulo="Leads" valor={painel.leads} />
            <Metrica rotulo="Em aprovação" valor={funilPorEtapa.aprovado ?? 0} />
            <Metrica rotulo="Escriturados" valor={painel.escriturados} />
            <Metrica rotulo="Conversão" valor={formatarConversao(painel.taxaDeConversao)} />
            <Metrica rotulo="Pedidos pendentes" valor={painel.pedidosPendentes} destaque={painel.pedidosPendentes > 0} />
          </>
        )}
      </section>
      {painelQ.isError && (
        <p role="alert" className="text-sm text-destructive">{mensagemDeErro(painelQ.error, "Não foi possível carregar o resumo.")}</p>
      )}

      <section aria-label="Os meus casos" className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[12rem] flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input
              type="search" className="pl-9" placeholder="Pesquisar por nome ou número"
              aria-label="Pesquisar casos" value={texto} onChange={(e) => setTexto(e.target.value)}
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-2" role="group" aria-label="Filtrar por etapa">
          <Button type="button" size="sm" variant={etapa === "" ? "default" : "outline"} aria-pressed={etapa === ""} onClick={() => { setEtapa(""); setPagina(1); }}>
            Todos ({painel.totalDeCasos})
          </Button>
          {painel.funil.map((e) => (
            <Button
              key={e.etapa} type="button" size="sm"
              variant={etapa === e.etapa ? "default" : "outline"} aria-pressed={etapa === e.etapa}
              onClick={() => { setEtapa(e.etapa); setPagina(1); }}
            >
              {e.label} ({e.total})
            </Button>
          ))}
        </div>

        {casosQ.isPending ? (
          <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-16" />)}</div>
        ) : casosQ.isError ? (
          <p role="alert" className="text-sm text-destructive">{mensagemDeErro(casosQ.error, "Não foi possível carregar os casos.")}</p>
        ) : casos.items.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center gap-3 p-8 text-center">
              <Inbox className="h-8 w-8 text-muted-foreground" aria-hidden="true" />
              <p className="text-sm text-muted-foreground">
                {etapa || pesquisa ? "Nenhum caso corresponde ao filtro." : "Ainda não tem casos. Submeta a sua primeira lead."}
              </p>
              {!etapa && !pesquisa && (
                <Button asChild size="sm"><Link to="/parceiro/novo-lead">Submeter lead</Link></Button>
              )}
            </CardContent>
          </Card>
        ) : (
          <ul className="space-y-2">
            {casos.items.map((c) => (
              <li key={c.id}>
                <Link
                  to={caminhoDoCaso(c.id)}
                  className="block rounded-lg border border-border bg-card p-4 transition-colors hover:bg-secondary"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate font-medium">{c.client_name || "Sem nome"}</p>
                      <p className="text-xs text-muted-foreground">
                        {[c.process_number, c.consultor_name && `Consultor: ${c.consultor_name}`, formatarData(c.updated_at)]
                          .filter(Boolean).join(" · ")}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {c.pedidos_pendentes > 0 && (
                        <Badge variant="destructive" aria-label={`${c.pedidos_pendentes} pedidos pendentes`}>
                          {c.pedidos_pendentes} pendente{c.pedidos_pendentes > 1 ? "s" : ""}
                        </Badge>
                      )}
                      <Badge variant={variantDaEtapa(c.etapa)}>{c.etapa_label}</Badge>
                    </div>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}

        {casos.pages > 1 && (
          <nav aria-label="Paginação" className="flex items-center justify-between">
            <Button type="button" size="sm" variant="outline" disabled={casos.page <= 1} onClick={() => setPagina((p) => Math.max(1, p - 1))}>
              <ChevronLeft className="mr-1 h-4 w-4" aria-hidden="true" />Anterior
            </Button>
            <span className="text-sm text-muted-foreground">Página {casos.page} de {casos.pages}</span>
            <Button type="button" size="sm" variant="outline" disabled={casos.page >= casos.pages} onClick={() => setPagina((p) => p + 1)}>
              Seguinte<ChevronRight className="ml-1 h-4 w-4" aria-hidden="true" />
            </Button>
          </nav>
        )}
      </section>
    </div>
  );
}
