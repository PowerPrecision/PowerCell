/**
 * SlaThresholdsSection — limiares de SLA por macro-fase.
 *
 * Até aqui `dashboard_slas` só se mudava por `PATCH /api/system-config/
 * dashboard_slas`: a secção existia no backend com omissões (7/15/30 dias) e
 * nunca ninguém lhe construiu ecrã.
 *
 * **ÂMBITO GLOBAL, e isso está escrito no ecrã.** O leitor
 * (`services/stats_sla._limiares`) chama `get_system_config()` SEM argumento,
 * logo lê sempre a configuração `default`. O modelo prometia "por empresa" na
 * docstring, mas a promessa não estava cumprida do lado da leitura. Construir
 * aqui um selector de empresa faria o administrador editar a Power e o painel
 * continuar a usar a global — exactamente o incidente de 2026-09-21 (escrever
 * numa chave e ler de outra). Enquanto o leitor for global, o ecrã é global e
 * diz-o. A diferença está registada em `TECHNICAL_DEBT.md`.
 *
 * Tudo por Axios (`services/api.js`): configuração depende de contexto de
 * empresa/papel e um `fetch` cru perde o `X-Company-Id`.
 */
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Gauge, Loader2, Save } from "lucide-react";
import { toast } from "sonner";

import { getSystemConfig, updateSystemConfigSection } from "../../services/api";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import {
  construirPayload,
  errosDoFormulario,
  hidratarLimiares,
  houveAlteracoes,
  MACROS_COM_SLA,
} from "../../utils/slaThresholds";
import { Button } from "../../components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Switch } from "../../components/ui/switch";
import { Skeleton } from "../../components/ui/skeleton";

export default function SlaThresholdsSection() {
  const [config, setConfig] = useState(null);
  const [formulario, setFormulario] = useState(() => hidratarLimiares(null));
  const [aCarregar, setACarregar] = useState(true);
  const [aGuardar, setAGuardar] = useState(false);
  const [erroDeLeitura, setErroDeLeitura] = useState("");

  const carregar = useCallback(async () => {
    setACarregar(true);
    setErroDeLeitura("");
    try {
      const res = await getSystemConfig();
      const secao = res.data?.dashboard_slas ?? null;
      setConfig(secao);
      setFormulario(hidratarLimiares(secao));
    } catch (err) {
      // Um erro de leitura NÃO pode aparecer como "estão nas omissões": o
      // administrador gravaria por cima de valores que nunca viu.
      setErroDeLeitura(
        extractErrorMessage(
          err.response?.data?.detail || err.response?.data?.error,
          "Não foi possível ler os limiares de SLA.",
        ),
      );
    } finally {
      setACarregar(false);
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const erros = errosDoFormulario(formulario);
  const temErros = Object.keys(erros).length > 0;
  const alterado = houveAlteracoes(formulario, config);

  const guardar = async () => {
    const payload = construirPayload(formulario);
    if (!payload) {
      toast.error("Corrija os limiares antes de guardar.");
      return;
    }
    setAGuardar(true);
    try {
      await updateSystemConfigSection("dashboard_slas", payload);
      // O estado de referência passa a ser o que foi GRAVADO — senão o botão
      // "Guardar" fica activo para sempre depois de um save bem sucedido.
      setConfig(payload);
      setFormulario(hidratarLimiares(payload));
      toast.success("Limiares de SLA actualizados");
    } catch (err) {
      toast.error(
        extractErrorMessage(
          err.response?.data?.detail || err.response?.data?.error,
          "Erro ao guardar os limiares de SLA",
        ),
      );
    } finally {
      setAGuardar(false);
    }
  };

  if (aCarregar) {
    return (
      <Card data-testid="sla-thresholds-section">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Gauge className="h-5 w-5" />
            Limiares de SLA
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card data-testid="sla-thresholds-section">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Gauge className="h-5 w-5" />
          Limiares de SLA
        </CardTitle>
        <CardDescription>
          Quantos dias um processo pode ficar em cada fase antes de contar como
          atrasado nos painéis. Aplica-se a <strong>todas as empresas</strong>.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-6">
        {erroDeLeitura ? (
          <div
            className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm"
            data-testid="sla-erro-leitura"
          >
            <AlertTriangle className="h-4 w-4 mt-0.5 text-destructive shrink-0" />
            <div className="space-y-2">
              <p className="text-destructive">{erroDeLeitura}</p>
              <p className="text-muted-foreground">
                Os valores abaixo são as omissões do sistema, não os que estão
                gravados — guardar agora escreve por cima.
              </p>
              <Button variant="outline" size="sm" onClick={carregar} data-testid="sla-tentar-novamente">
                Tentar novamente
              </Button>
            </div>
          </div>
        ) : null}

        <div className="flex items-center justify-between rounded-md border border-border p-3">
          <div className="space-y-0.5">
            <Label htmlFor="sla-enabled">Assinalar processos atrasados</Label>
            <p className="text-xs text-muted-foreground">
              Desligado, os painéis continuam a mostrar os tempos mas sem a
              coluna de atraso.
            </p>
          </div>
          <Switch
            id="sla-enabled"
            checked={formulario.enabled}
            onCheckedChange={(valor) =>
              setFormulario((antes) => ({ ...antes, enabled: valor }))
            }
            data-testid="sla-enabled"
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          {MACROS_COM_SLA.map(({ chave, etiqueta, ajuda }) => (
            <div key={chave} className="space-y-1.5">
              <Label htmlFor={`sla-${chave}`}>{etiqueta}</Label>
              <div className="relative">
                <Input
                  id={`sla-${chave}`}
                  inputMode="numeric"
                  value={formulario[chave]}
                  onChange={(e) =>
                    setFormulario((antes) => ({ ...antes, [chave]: e.target.value }))
                  }
                  aria-invalid={Boolean(erros[chave])}
                  aria-describedby={erros[chave] ? `sla-${chave}-erro` : undefined}
                  className="pr-12"
                  data-testid={`sla-${chave}`}
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">
                  dias
                </span>
              </div>
              {erros[chave] ? (
                <p
                  id={`sla-${chave}-erro`}
                  className="text-xs text-destructive"
                  data-testid={`sla-${chave}-erro`}
                >
                  {erros[chave]}
                </p>
              ) : (
                <p className="text-xs text-muted-foreground">{ajuda}</p>
              )}
            </div>
          ))}
        </div>

        <p className="text-xs text-muted-foreground">
          As fases terminais (Concluído, Perdido) não têm limiar de propósito —
          um processo concluído não demora em concluído, fica lá.
        </p>

        <div className="flex justify-end">
          <Button
            onClick={guardar}
            disabled={aGuardar || temErros || !alterado}
            className="gap-1.5"
            data-testid="sla-guardar"
          >
            {aGuardar ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {aGuardar ? "A guardar..." : "Guardar limiares"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
