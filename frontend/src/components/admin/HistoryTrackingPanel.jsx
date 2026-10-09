/**
 * Controlo de histórico (Bloco 1, ponto 4) — só o admin.
 *
 * Liga/desliga se as acções ficam guardadas no histórico, por PERFIL e por
 * PESSOA. Por omissão tudo está ativo. A pessoa vence o perfil; o perfil
 * Indexação é sempre silencioso e aparece bloqueado, com o motivo.
 *
 * Apresentação + pedidos; as regras de tradução vivem em
 * `utils/historyTracking` (puras e testadas). O servidor é a parede.
 */
import { useCallback, useEffect, useState } from "react";
import { Loader2, Lock } from "lucide-react";
import { toast } from "sonner";

import {
  getHistoryTracking,
  listUsersHistoryTracking,
  setRoleHistoryTracking,
  setUserHistoryTracking,
} from "../../services/api";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import {
  OPCOES_DE_PESSOA,
  descricaoDoEstado,
  enabledDoPedido,
  normalizarPerfis,
  normalizarUtilizadores,
  valorDaPessoa,
} from "../../utils/historyTracking";
import { ROLE_LABELS } from "../../utils/roleUtils";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Input } from "../ui/input";
import { Switch } from "../ui/switch";

const TAMANHO_DA_PAGINA = 15;

export default function HistoryTrackingPanel() {
  const [perfis, setPerfis] = useState([]);
  const [aCarregarPerfis, setACarregarPerfis] = useState(true);
  const [erroDePerfis, setErroDePerfis] = useState(false);

  const [pesquisa, setPesquisa] = useState("");
  const [pagina, setPagina] = useState(1);
  const [pessoas, setPessoas] = useState({ utilizadores: [], total: 0 });
  const [aCarregarPessoas, setACarregarPessoas] = useState(true);
  const [aGuardar, setAGuardar] = useState(null);

  const carregarPerfis = useCallback(async () => {
    setACarregarPerfis(true);
    try {
      const res = await getHistoryTracking();
      setPerfis(normalizarPerfis(res?.data));
      setErroDePerfis(false);
    } catch (error) {
      setErroDePerfis(true);
      toast.error(extractErrorMessage(error?.response?.data?.detail, "Erro ao carregar os perfis"));
    } finally {
      setACarregarPerfis(false);
    }
  }, []);

  const carregarPessoas = useCallback(async () => {
    setACarregarPessoas(true);
    try {
      const res = await listUsersHistoryTracking({
        search: pesquisa.trim() || undefined,
        page: pagina,
        size: TAMANHO_DA_PAGINA,
      });
      setPessoas(normalizarUtilizadores(res?.data));
    } catch (error) {
      toast.error(extractErrorMessage(error?.response?.data?.detail, "Erro ao carregar os utilizadores"));
    } finally {
      setACarregarPessoas(false);
    }
  }, [pesquisa, pagina]);

  useEffect(() => {
    carregarPerfis();
  }, [carregarPerfis]);

  useEffect(() => {
    carregarPessoas();
  }, [carregarPessoas]);

  const mudarPerfil = async (perfil, enabled) => {
    setAGuardar(`role:${perfil.role}`);
    try {
      await setRoleHistoryTracking(perfil.role, enabled);
      toast.success(
        enabled
          ? `O histórico do perfil ${ROLE_LABELS[perfil.role] || perfil.role} está ativo`
          : `O histórico do perfil ${ROLE_LABELS[perfil.role] || perfil.role} foi desligado`,
      );
      // O estado efectivo das pessoas depende do perfil: recarrega as duas.
      await Promise.all([carregarPerfis(), carregarPessoas()]);
    } catch (error) {
      toast.error(extractErrorMessage(error?.response?.data?.detail, "Não foi possível alterar o perfil"));
    } finally {
      setAGuardar(null);
    }
  };

  const mudarPessoa = async (pessoa, valor) => {
    setAGuardar(`user:${pessoa.id}`);
    try {
      await setUserHistoryTracking(pessoa.id, enabledDoPedido(valor));
      toast.success(`Histórico de ${pessoa.name} atualizado`);
      await carregarPessoas();
    } catch (error) {
      toast.error(extractErrorMessage(error?.response?.data?.detail, "Não foi possível alterar a pessoa"));
    } finally {
      setAGuardar(null);
    }
  };

  const totalDePaginas = Math.max(1, Math.ceil(pessoas.total / TAMANHO_DA_PAGINA));

  return (
    <div className="space-y-6" data-testid="history-tracking-panel">
      <Card>
        <CardHeader>
          <CardTitle>Registo no histórico</CardTitle>
          <CardDescription>
            Decide se as acções ficam guardadas no histórico dos processos. Por omissão
            está tudo ativo. A decisão sobre uma <strong>pessoa</strong> vence a do seu
            perfil. Uma alteração pode demorar até 30 segundos a chegar a todos os
            servidores. A Auditoria (conformidade) não é afetada.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <h3 className="text-sm font-medium">Por perfil</h3>
          {aCarregarPerfis && perfis.length === 0 ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-label="A carregar perfis" />
          ) : erroDePerfis ? (
            <p className="text-sm text-destructive">Não foi possível carregar os perfis.</p>
          ) : (
            <ul className="divide-y rounded-md border" data-testid="history-roles">
              {perfis.map((perfil) => {
                const rotulo = ROLE_LABELS[perfil.role] || perfil.role;
                return (
                  <li key={perfil.role} className="flex items-center justify-between gap-3 px-3 py-2">
                    <div className="min-w-0">
                      <p className="text-sm font-medium flex items-center gap-1.5">
                        {rotulo}
                        {perfil.locked && <Lock className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />}
                      </p>
                      {perfil.locked && perfil.motivo && (
                        <p className="text-xs text-muted-foreground">{perfil.motivo}</p>
                      )}
                    </div>
                    <Switch
                      aria-label={`Registar no histórico — ${rotulo}`}
                      checked={perfil.enabled}
                      disabled={perfil.locked || aGuardar === `role:${perfil.role}`}
                      onCheckedChange={(valor) => mudarPerfil(perfil, valor)}
                    />
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Por pessoa</CardTitle>
          <CardDescription>
            «Segue o perfil» é o estado normal. Só se escolhe «Sempre ativo» ou
            «Desligado» para abrir uma excepção.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Input
            type="search"
            value={pesquisa}
            onChange={(evento) => {
              setPesquisa(evento.target.value);
              setPagina(1);
            }}
            placeholder="Pesquisar por nome ou email"
            aria-label="Pesquisar utilizadores"
          />
          {aCarregarPessoas && pessoas.utilizadores.length === 0 ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-label="A carregar utilizadores" />
          ) : pessoas.utilizadores.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhum utilizador encontrado.</p>
          ) : (
            <ul className="divide-y rounded-md border" data-testid="history-users">
              {pessoas.utilizadores.map((pessoa) => (
                <li key={pessoa.id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 px-3 py-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{pessoa.name}</p>
                    <p className="text-xs text-muted-foreground truncate">
                      {pessoa.email} · {ROLE_LABELS[pessoa.role] || pessoa.role}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Badge variant={pessoa.efectivo ? "secondary" : "outline"}>
                      {descricaoDoEstado(pessoa)}
                    </Badge>
                    <select
                      aria-label={`Histórico de ${pessoa.name}`}
                      value={valorDaPessoa(pessoa.track_history)}
                      disabled={pessoa.bloqueado || aGuardar === `user:${pessoa.id}`}
                      onChange={(evento) => mudarPessoa(pessoa, evento.target.value)}
                      className="h-9 rounded-md border border-input bg-background px-2 text-sm disabled:opacity-60"
                    >
                      {OPCOES_DE_PESSOA.map((opcao) => (
                        <option key={opcao.value} value={opcao.value}>
                          {opcao.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {totalDePaginas > 1 && (
            <div className="flex items-center justify-between text-sm">
              <Button variant="outline" size="sm" disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)}>
                Anterior
              </Button>
              <span className="text-muted-foreground">
                Página {pagina} de {totalDePaginas}
              </span>
              <Button variant="outline" size="sm" disabled={pagina >= totalDePaginas} onClick={() => setPagina((p) => p + 1)}>
                Seguinte
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
