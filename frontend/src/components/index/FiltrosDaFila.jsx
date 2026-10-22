/**
 * FiltrosDaFila — «Ordenar por», Estado, Empresa e Origem da fila do Index (apresentação pura).
 *
 * Diz o que aconteceu (`onMudar(campo, valor)`, `onLimpar()`); quem escreve no URL e decide o pedido é a página.
 * As opções do Estado dependem do separador (a Fila tem «por indexar» e «em tratamento»; as Revisões só
 * «indexado») e as das Empresas são as que o servidor diz que a fila TEM — nunca uma lista escrita aqui.
 * Um filtro de empresa que já não está nas opções (um link antigo) continua visível: um filtro ligado
 * que não se vê é uma lista «vazia» sem explicação.
 */
import { X } from "lucide-react";

import { Button } from "../ui/button";
import { Label } from "../ui/label";
import {
  ESTADOS_DA_ABA,
  ORIGENS_DA_FILA,
  opcoesDeOrdenacao,
  rotuloDoEstado,
  totalDeFiltrosLigados,
} from "../../utils/indexRevisao";

const CLASSE_DO_SELECT =
  "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

function Seletor({ id, rotulo, valor, onChange, children }) {
  return (
    <div className="min-w-[11rem] flex-1 space-y-1.5 sm:max-w-[16rem]">
      <Label htmlFor={id}>{rotulo}</Label>
      <select id={id} value={valor} onChange={(e) => onChange(e.target.value)} className={CLASSE_DO_SELECT}>
        {children}
      </select>
    </div>
  );
}

/**
 * @param {Object} props
 * @param {"pending"|"reviews"} props.separador
 * @param {string} props.ordem — a ordem em vigor (`client_asc`…)
 * @param {{estado: string, empresa: string, origem: string}} props.filtros
 * @param {Array<{id: string, nome: string, total: number}>} props.empresas
 * @param {(campo: "ordem"|"estado"|"empresa"|"origem", valor: string) => void} props.onMudar
 * @param {() => void} props.onLimpar
 */
export function FiltrosDaFila({ separador, ordem, filtros, empresas, onMudar, onLimpar }) {
  const lista = Array.isArray(empresas) ? empresas : [];
  const empresaFora = filtros.empresa && !lista.some((e) => e.id === filtros.empresa);
  const ligados = totalDeFiltrosLigados(filtros);

  return (
    <div className="flex flex-wrap items-end gap-3" role="group" aria-label="Ordenar e filtrar a fila" data-testid="filtros-da-fila">
      <Seletor id="fila-ordem" rotulo="Ordenar por" valor={ordem} onChange={(v) => onMudar("ordem", v)}>
        {opcoesDeOrdenacao(separador).map((o) => (
          <option key={o.valor} value={o.valor}>{o.rotulo}</option>
        ))}
      </Seletor>
      <Seletor id="fila-estado" rotulo="Estado" valor={filtros.estado} onChange={(v) => onMudar("estado", v)}>
        <option value="">Todos</option>
        {(ESTADOS_DA_ABA[separador] || []).map((e) => (
          <option key={e} value={e}>{rotuloDoEstado(e)}</option>
        ))}
      </Seletor>
      <Seletor id="fila-empresa" rotulo="Empresa" valor={filtros.empresa} onChange={(v) => onMudar("empresa", v)}>
        <option value="">Todas</option>
        {lista.map((e) => (
          <option key={e.id} value={e.id}>{`${e.nome} (${e.total})`}</option>
        ))}
        {empresaFora && <option value={filtros.empresa}>Empresa do filtro activo</option>}
      </Seletor>
      <Seletor id="fila-origem" rotulo="Origem" valor={filtros.origem} onChange={(v) => onMudar("origem", v)}>
        <option value="">Todas</option>
        {ORIGENS_DA_FILA.map((o) => (
          <option key={o.valor} value={o.valor}>{o.rotulo}</option>
        ))}
      </Seletor>
      {ligados > 0 && (
        <Button type="button" variant="ghost" onClick={onLimpar} className="gap-1" data-testid="limpar-filtros-da-fila">
          <X className="h-4 w-4" aria-hidden="true" />
          {ligados === 1 ? "Limpar filtro" : `Limpar ${ligados} filtros`}
        </Button>
      )}
    </div>
  );
}

export default FiltrosDaFila;
