/**
 * NovidadesDoCrm — a lista das últimas atualizações do CRM.
 *
 * As atualizações são GLOBAIS (todas as redes e empresas veem as mesmas) e só
 * existem no CRM: nunca nos portais do Cliente e do Parceiro. Uma novidade
 * `is_premium` é destacada com «Módulo Premium» e um convite a pedir o módulo —
 * é isso que leva quem ainda não o tem a pedir para o comprar.
 *
 * COMPONENTE DE APRESENTAÇÃO: recebe as entradas já carregadas.
 */
import { Megaphone } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Badge } from "../ui/badge";
import PremiumBadge from "./PremiumBadge";
import { cn } from "../../lib/utils";
import { safeString } from "../../utils/safeString";
import { sanitizeHtml } from "../../utils/sanitize";

/**
 * @param {Object} props
 * @param {Array<{id?: string, version?: string, published_at?: string, content_markdown?: string, is_premium?: boolean}>} props.entradas
 * @param {(markdown: string) => string} props.markdownParaHtml
 * @param {(data: string) => string} [props.formatarData]
 */
export default function NovidadesDoCrm({ entradas, markdownParaHtml, formatarData = (d) => d }) {
  // `Array.isArray` e não `|| []`: um objecto é truthy e o `.map` rebentava.
  const lista = Array.isArray(entradas) ? entradas.filter((e) => e && e.content_markdown) : [];
  if (lista.length === 0) return null;

  return (
    <div className="space-y-4" data-testid="novidades-do-crm">
      {lista.map((entrada, i) => {
        const premium = entrada.is_premium === true;
        return (
          <Card
            key={entrada.id ?? `${entrada.version}-${i}`}
            data-testid="novidade"
            data-premium={premium ? "true" : "false"}
            className={cn("border-border bg-secondary/40", premium && "border-amber-500/50 bg-amber-500/5")}
          >
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex flex-wrap items-center gap-2">
                <Megaphone className="h-5 w-5 text-primary" aria-hidden="true" />
                {i === 0 ? "Novidades do CRM" : "Novidade anterior"}
                {entrada.version && (
                  <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                    {safeString(entrada.version)}
                  </Badge>
                )}
                {premium && <PremiumBadge />}
              </CardTitle>
              <CardDescription className="text-xs">
                {entrada.published_at && formatarData(entrada.published_at)}
              </CardDescription>
            </CardHeader>
            <CardContent className="pt-0">
              <div
                className="prose prose-sm dark:prose-invert max-w-none text-sm leading-relaxed changelog-content"
                dangerouslySetInnerHTML={{ __html: sanitizeHtml(markdownParaHtml(entrada.content_markdown)) }}
              />
              {premium && (
                <p
                  className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-200"
                  data-testid="convite-premium"
                >
                  Esta novidade faz parte de um módulo Premium. Se a sua empresa ainda não o tem,
                  peça ao seu administrador para o contratar.
                </p>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
