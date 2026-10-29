/**
 * TelegramSettings — ligar a conta ao bot do Telegram e escolher que avisos recebe.
 *
 * A ligação faz-se com um link de uso único (10 minutos) para o bot; no Telegram
 * a pessoa carrega em «Iniciar». Enquanto espera, o cartão pergunta ao backend
 * de 3 em 3 segundos se a ligação já ficou feita.
 *
 * As mensagens são mínimas (sem dados de clientes) e os avisos do mesmo processo
 * chegam juntos numa só mensagem.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Label } from "./ui/label";
import { Switch } from "./ui/switch";
import { Loader2, Send, Unlink, ExternalLink } from "lucide-react";
import { toast } from "sonner";
import {
  getTelegramEstado,
  ligarTelegram,
  desligarTelegram,
  atualizarPreferenciasTelegram,
} from "../services/api";
import { extractErrorMessage } from "../utils/extractErrorMessage";

const INTERVALO_DE_ESPERA_MS = 3000;
const ESPERA_MAXIMA_MS = 10 * 60 * 1000;

export default function TelegramSettings() {
  const [estado, setEstado] = useState(null);
  const [aCarregar, setACarregar] = useState(true);
  const [aLigar, setALigar] = useState(false);
  const [linkDeLigacao, setLinkDeLigacao] = useState("");
  const temporizador = useRef(null);
  const inicioDaEspera = useRef(0);

  const carregar = useCallback(async () => {
    try {
      const { data } = await getTelegramEstado();
      setEstado(data);
      return data;
    } catch (error) {
      toast.error(extractErrorMessage(error?.response?.data?.detail, "Erro ao carregar o estado do Telegram"));
      return null;
    } finally {
      setACarregar(false);
    }
  }, []);

  const pararEspera = () => {
    if (temporizador.current) {
      clearInterval(temporizador.current);
      temporizador.current = null;
    }
  };

  useEffect(() => {
    carregar();
    return pararEspera;
  }, [carregar]);

  const esperarLigacao = () => {
    pararEspera();
    inicioDaEspera.current = Date.now();
    temporizador.current = setInterval(async () => {
      if (Date.now() - inicioDaEspera.current > ESPERA_MAXIMA_MS) {
        pararEspera();
        setLinkDeLigacao("");
        return;
      }
      try {
        const { data } = await getTelegramEstado();
        if (data?.ligado) {
          pararEspera();
          setEstado(data);
          setLinkDeLigacao("");
          toast.success("Telegram ligado");
        }
      } catch {
        // Tenta outra vez no próximo intervalo.
      }
    }, INTERVALO_DE_ESPERA_MS);
  };

  const handleLigar = async () => {
    setALigar(true);
    try {
      const { data } = await ligarTelegram();
      if (!data?.ok) {
        toast.error(data?.motivo || "Não foi possível gerar o link do Telegram");
        return;
      }
      setLinkDeLigacao(data.url);
      esperarLigacao();
    } catch (error) {
      toast.error(extractErrorMessage(error?.response?.data?.detail, "Erro ao ligar o Telegram"));
    } finally {
      setALigar(false);
    }
  };

  const handleDesligar = async () => {
    try {
      await desligarTelegram();
      await carregar();
      toast.info("Telegram desligado");
    } catch (error) {
      toast.error(extractErrorMessage(error?.response?.data?.detail, "Erro ao desligar o Telegram"));
    }
  };

  const guardar = async (alteracao) => {
    const anterior = estado;
    setEstado((atual) => ({
      ...atual,
      ...(alteracao.so_fora_da_app !== undefined ? { so_fora_da_app: alteracao.so_fora_da_app } : {}),
      preferencias: { ...atual.preferencias, ...(alteracao.preferencias || {}) },
    }));
    try {
      const { data } = await atualizarPreferenciasTelegram({ preferencias: {}, ...alteracao });
      setEstado(data);
    } catch (error) {
      setEstado(anterior);
      toast.error(extractErrorMessage(error?.response?.data?.detail, "Erro ao guardar a preferência"));
    }
  };

  if (aCarregar) {
    return (
      <Card className="border-border">
        <CardContent className="py-6 flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> A carregar o Telegram…
        </CardContent>
      </Card>
    );
  }

  if (!estado) return null;

  return (
    <Card className="border-border">
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <Send className="h-5 w-5" />
          Notificações no Telegram
          <Badge variant={estado.ligado ? "default" : "outline"} className="ml-auto">
            {estado.ligado ? "Ligado" : "Desligado"}
          </Badge>
        </CardTitle>
        <CardDescription>
          Receba os avisos do PowerCell no telemóvel. As mensagens dizem só o tipo de aviso e o número
          do processo; os avisos do mesmo processo chegam juntos numa só mensagem.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!estado.configurado && (
          <p className="text-sm text-muted-foreground">
            O Telegram ainda não está configurado no servidor. Fale com o administrador.
          </p>
        )}

        {estado.configurado && !estado.ligado && (
          <div className="space-y-3">
            {!linkDeLigacao ? (
              <Button onClick={handleLigar} disabled={aLigar}>
                {aLigar ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Send className="h-4 w-4 mr-2" />}
                Ligar Telegram
              </Button>
            ) : (
              <div className="space-y-2 rounded-lg border border-border bg-muted/30 p-4">
                <p className="text-sm">
                  Abra o Telegram e carregue em <strong>Iniciar</strong>. Esta página actualiza sozinha
                  quando a ligação ficar feita. O link vale 10 minutos.
                </p>
                <Button asChild>
                  <a href={linkDeLigacao} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="h-4 w-4 mr-2" />
                    Abrir o Telegram
                  </a>
                </Button>
              </div>
            )}
          </div>
        )}

        {estado.ligado && (
          <>
            <div className="space-y-1">
              {estado.categorias.map(({ chave, label }) => (
                <div key={chave} className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-muted/50">
                  <Label htmlFor={`telegram-${chave}`} className="cursor-pointer">{label}</Label>
                  <Switch
                    id={`telegram-${chave}`}
                    checked={Boolean(estado.preferencias?.[chave])}
                    onCheckedChange={(valor) => guardar({ preferencias: { [chave]: valor } })}
                  />
                </div>
              ))}
              <div className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-muted/50">
                <div>
                  <Label htmlFor="telegram-so-fora" className="cursor-pointer">Só quando não estou na aplicação</Label>
                  <p className="text-xs text-muted-foreground">Enquanto tiver o PowerCell aberto, os avisos ficam só na app.</p>
                </div>
                <Switch
                  id="telegram-so-fora"
                  checked={Boolean(estado.so_fora_da_app)}
                  onCheckedChange={(valor) => guardar({ so_fora_da_app: valor })}
                />
              </div>
            </div>
            <Button variant="outline" onClick={handleDesligar}>
              <Unlink className="h-4 w-4 mr-2" />
              Desligar Telegram
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}
