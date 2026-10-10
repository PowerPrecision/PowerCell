/**
 * Etiqueta de PARTILHA (D-25) — `[Partilha: Precision]`.
 *
 * PORQUE É QUE ESTA ETIQUETA NÃO É DECORAÇÃO
 * A partilha é **Via Rápida**: nasce de uma atribuição, sem aprovação
 * manual. Isso significa que uma fronteira de rede se abre sem ninguém
 * a autorizar — e a única coisa que a torna visível a quem trabalha o
 * processo é esta etiqueta. Esconder a partilha num processo partilhado
 * é o oposto de tolerância zero ao cruzamento de dados.
 *
 * Por isso, e ao contrário da `Sub35Badge`, esta nomeia a EMPRESA: saber
 * que «está partilhado» sem saber com quem não responde à pergunta que
 * uma pessoa faz ao ver a linha.
 *
 * UM componente e não quatro: a `Sub35Badge` nasceu de três cópias com
 * as cores escritas à mão em três sítios, duas das quais liam um campo
 * que o servidor nunca escreveu. O campo aqui é calculado ao servir
 * (`services/process_sharing.py`) e lido num ponto só.
 *
 * Tokens semânticos, nunca cores cruas: `bg-amber-50` fica
 * amarelo-claro sobre amarelo-claro no modo escuro (regra ESLint
 * `no-restricted-syntax`, ver FRONTEND_GUIDELINES).
 */
import { Handshake } from "lucide-react";

import { Badge } from "../ui/badge";
import { cn } from "../../lib/utils";

/** O texto vive aqui. Duas cópias é como as da Sub35 divergiram. */
export const ROTULO_PARTILHA = "Partilha";
export const EXPLICACAO_PARTILHA =
  "Processo partilhado: as empresas indicadas vêem esta ficha. A " +
  "fronteira continua fechada nos restantes processos.";

/**
 * @param {object} props
 * @param {object} [props.processo] — documento servido pela API
 * @param {string[]} [props.empresas] — alternativa a `processo`, já resolvida
 * @param {"sm"|"md"} [props.tamanho]
 * @param {string} [props.className]
 */
export default function PartilhaBadge({
  processo,
  empresas,
  tamanho = "md",
  className,
}) {
  const nomes = empresas !== undefined ? normalizar(empresas) : empresasDaPartilha(processo);
  if (!nomes.length) return null;

  return (
    <Badge
      variant="outline"
      title={`${EXPLICACAO_PARTILHA} (${nomes.join(", ")})`}
      className={cn(
        "gap-1 font-medium whitespace-nowrap border-primary/40 text-primary",
        tamanho === "sm"
          ? "text-[9px] px-1.5 py-0 h-4"
          : "text-[10px] px-2 py-0 h-5",
        className,
      )}
      data-testid="etiqueta-partilha"
    >
      <Handshake className={tamanho === "sm" ? "h-2.5 w-2.5" : "h-3 w-3"} />
      {`${ROTULO_PARTILHA}: ${nomes.join(", ")}`}
    </Badge>
  );
}

function normalizar(valor) {
  // `Array.isArray` e nunca `|| []`: um objecto é truthy, logo
  // `valor || []` devolveria o objecto e o `.map` rebentava noutro sítio
  // em vez de aqui (§ 27.38 das FRONTEND_GUIDELINES).
  if (!Array.isArray(valor)) return [];
  return valor.map((n) => String(n ?? "").trim()).filter(Boolean);
}

/**
 * Com que empresas é que este processo está partilhado?
 *
 * `partilha_com` é o campo que o servidor calcula ao servir. O recurso
 * para `partner_companies` existe para o caso de um ecrã receber o
 * documento cru (o detalhe do processo não passa pela serialização das
 * listagens) — e é SÓ aqui que a cascata existe.
 *
 * Nunca se decide a partilha no cliente a partir de `partner_network_ids`:
 * a lista de REDES é a fronteira de segurança e não tem nome legível;
 * mostrar `rede:8a0b6657…` a um consultor não responde a pergunta
 * nenhuma.
 */
export function empresasDaPartilha(processo) {
  if (!processo || typeof processo !== "object") return [];

  const calculadas = normalizar(processo.partilha_com);
  if (calculadas.length) return calculadas;

  const registo = Array.isArray(processo.partner_companies)
    ? processo.partner_companies
    : [];
  const nomes = registo
    .map((e) =>
      e && typeof e === "object"
        ? String(e.company_name || e.company_id || "").trim()
        : "",
    )
    .filter(Boolean);

  return [...new Set(nomes)];
}

/** Está partilhado? (sem precisar dos nomes) */
export function estaPartilhado(processo) {
  if (!processo || typeof processo !== "object") return false;
  if (processo.is_partilhado === true) return true;
  return empresasDaPartilha(processo).length > 0;
}
