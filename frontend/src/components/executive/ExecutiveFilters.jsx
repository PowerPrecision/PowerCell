/**
 * Filtros do Dashboard Executivo (Bloco 4, ponto 16): período (predefinido ou
 * intervalo de datas), colaborador e perfil. Controlado: o estado vive na
 * página; as escolhas só estreitam o âmbito (o servidor é a parede).
 */
import { CalendarDays, FileDown, Loader2, RefreshCw, Users } from "lucide-react";

import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { PAPEIS_FILTRAVEIS, PREDEFINICOES, ROTULOS_DOS_PAPEIS } from "../../utils/executivo";

const TODOS = "__todos__";

/**
 * @param {Object} props
 * @param {string} props.predefinicao
 * @param {string} props.inicio / props.fim - `AAAA-MM-DD`.
 * @param {string} props.utilizador - `""` = toda a equipa.
 * @param {string} props.papel - `""` = todos os perfis.
 * @param {Array<{id: string, nome: string}>} props.opcoesDeUtilizadores
 * @param {string|null} props.erroDoIntervalo
 * @param {boolean} props.aCarregar / props.aGerarPdf
 */
export default function ExecutiveFilters({
  predefinicao, inicio, fim, utilizador, papel, opcoesDeUtilizadores, erroDoIntervalo,
  aCarregar, aGerarPdf, onPredefinicao, onInicio, onFim, onUtilizador, onPapel, onActualizar, onGerarPdf,
}) {
  return (
    <div className="space-y-3" data-testid="filtros-executivos">
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <Label className="text-xs" htmlFor="filtro-periodo">Período</Label>
          <Select value={predefinicao} onValueChange={onPredefinicao}>
            <SelectTrigger id="filtro-periodo" className="w-[200px]" aria-label="Período">
              <CalendarDays className="h-4 w-4 mr-2 text-muted-foreground" aria-hidden="true" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PREDEFINICOES.map((p) => <SelectItem key={p.chave} value={p.chave}>{p.rotulo}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        {predefinicao === "custom" && (
          <>
            <div className="space-y-1">
              <Label className="text-xs" htmlFor="filtro-inicio">De</Label>
              <Input id="filtro-inicio" type="date" value={inicio} max={fim || undefined}
                onChange={(e) => onInicio(e.target.value)} className="w-[160px]" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs" htmlFor="filtro-fim">Até</Label>
              <Input id="filtro-fim" type="date" value={fim} min={inicio || undefined}
                onChange={(e) => onFim(e.target.value)} className="w-[160px]" />
            </div>
          </>
        )}

        <div className="space-y-1">
          <Label className="text-xs" htmlFor="filtro-utilizador">Colaborador</Label>
          <Select value={utilizador || TODOS} onValueChange={(v) => onUtilizador(v === TODOS ? "" : v)}>
            <SelectTrigger id="filtro-utilizador" className="w-[200px]" aria-label="Colaborador">
              <Users className="h-4 w-4 mr-2 text-muted-foreground" aria-hidden="true" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={TODOS}>Toda a equipa</SelectItem>
              {opcoesDeUtilizadores.map((u) => <SelectItem key={u.id} value={u.id}>{u.nome}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <Label className="text-xs" htmlFor="filtro-perfil">Perfil</Label>
          <Select value={papel || TODOS} onValueChange={(v) => onPapel(v === TODOS ? "" : v)}>
            <SelectTrigger id="filtro-perfil" className="w-[170px]" aria-label="Perfil">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={TODOS}>Todos os perfis</SelectItem>
              {PAPEIS_FILTRAVEIS.map((p) => <SelectItem key={p} value={p}>{ROTULOS_DOS_PAPEIS[p]}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        <Button type="button" size="sm" variant="outline" onClick={onActualizar} disabled={aCarregar || Boolean(erroDoIntervalo)} className="gap-1.5">
          {aCarregar ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <RefreshCw className="h-4 w-4" aria-hidden="true" />}
          Actualizar
        </Button>
        <Button type="button" size="sm" onClick={onGerarPdf} disabled={aGerarPdf || aCarregar || Boolean(erroDoIntervalo)} className="gap-1.5">
          {aGerarPdf ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <FileDown className="h-4 w-4" aria-hidden="true" />}
          Gerar PDF
        </Button>
      </div>
      {erroDoIntervalo && <p className="text-sm text-destructive" role="alert">{erroDoIntervalo}</p>}
    </div>
  );
}
