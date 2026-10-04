/**
 * VisitasTable — a listagem de visitas como tabela (Lote 9, Fase B).
 *
 * COMPONENTE DE APRESENTAÇÃO: sem `useState` e sem `fetch`. Diz o que
 * aconteceu (`onAgendar(visita)`) e o contentor decide o que isso implica
 * — a regra do Épico 6 (`FRONTEND_GUIDELINES.md` § 20).
 *
 * Porque é uma TABELA e não cartões: o consultor precisa de COMPARAR os
 * imóveis que o cliente pediu — preço, tipologia, área, estado — e uma
 * grelha de cartões obriga a ler em zigue-zague. O quadro por estado
 * continua a existir para quem gere o fluxo (uma funcionalidade que
 * estorva uma regra nova muda-se de sítio, não se apaga).
 */
import {
  AlertTriangle,
  ExternalLink,
  EyeOff,
  Loader2,
  Mail,
  Phone,
} from "lucide-react";
import { Link } from "react-router-dom";

import EmptyState from "@/components/ui/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  contactoDoAnunciante,
  dadosDaIA,
  estadoDaExtraccao,
  ligacaoTelefonica,
  linhasDaTabela,
  rotaDaFicha,
  telefoneLegivel,
  temContactoDoAnunciante,
  textoDaFicha,
  tituloDoImovel,
} from "@/utils/visitasDashboard";

const ESTADO_DA_VISITA = {
  solicitada: { texto: "Pedido do cliente", variante: "secondary" },
  agendada: { texto: "Agendada", variante: "default" },
  concluida: { texto: "Concluída", variante: "outline" },
  cancelada: { texto: "Cancelada", variante: "destructive" },
  recusada: { texto: "Recusada", variante: "destructive" },
};

/** O estado da EXTRACÇÃO, que é diferente do estado da visita. */
function SeloDaExtraccao({ visita }) {
  const estado = estadoDaExtraccao(visita);
  if (estado === "sem_url") return null;
  if (estado === "pendente") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
        A ler o anúncio
      </span>
    );
  }
  if (estado === "erro") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-destructive">
        <AlertTriangle className="h-3 w-3" aria-hidden="true" />
        Não consegui ler
      </span>
    );
  }
  if (estado === "sem_dados") {
    // O terceiro veredicto: o anúncio respondeu e não trouxe nada. Antes
    // contava como sucesso e a linha ficava vazia sem explicação.
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
        <EyeOff className="h-3 w-3" aria-hidden="true" />
        Anúncio sem dados
      </span>
    );
  }
  return null;
}

function formatarEuros(valor) {
  if (valor === null || valor === undefined || valor === "") return "—";
  const numero = Number(valor);
  if (!Number.isFinite(numero)) return "—";
  return numero.toLocaleString("pt-PT", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  });
}

function formatarData(iso) {
  if (!iso) return "—";
  const data = new Date(iso);
  if (Number.isNaN(data.getTime())) return "—";
  return data.toLocaleString("pt-PT", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function CelulaDoCliente({ visita }) {
  const nome = String(visita?.client_name || "").trim();
  const rota = rotaDaFicha(visita);
  if (!nome) return <span className="text-muted-foreground">—</span>;
  // Sem destino NÃO se desenha a ligação: um link que não leva a lado
  // nenhum é pior do que texto (regra do `calendarioIdentidade`).
  if (!rota) return <span>{nome}</span>;
  return (
    <Link
      to={rota}
      className="font-medium text-primary hover:underline"
      title={textoDaFicha(visita)}
    >
      {nome}
    </Link>
  );
}

function CelulaDoImovel({ visita }) {
  const titulo = tituloDoImovel(visita);
  const url = String(visita?.scraped_url || "").trim();
  const foto = String(visita?.property_photo || "").trim();
  return (
    <div className="flex items-start gap-3">
      {foto ? (
        <img
          src={foto}
          alt=""
          aria-hidden="true"
          className="h-10 w-14 rounded object-cover border border-border shrink-0"
        />
      ) : null}
      <div className="min-w-0">
        <p className="font-medium truncate max-w-[22rem]">{titulo}</p>
        <div className="flex items-center gap-2">
          {url ? (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
              Ver anúncio
            </a>
          ) : null}
          <SeloDaExtraccao visita={visita} />
        </div>
      </div>
    </div>
  );
}

/**
 * A quem ligar: a agência e o comercial (LOTE 10).
 *
 * É a coluna que o consultor lê para marcar a partilha, e os dados já
 * existiam no sistema sem nunca chegarem ao ecrã. Três decisões:
 *
 * 1. a **agência** vem primeiro e em destaque: é o que identifica quem
 *    tem a chave do imóvel, mesmo quando não há nome de pessoa;
 * 2. o telefone é uma **ligação `tel:`** — num portátil abre o softphone,
 *    no telemóvel marca. Sem número, texto nenhum (`ligacaoTelefonica`
 *    devolve `null` e aqui não se desenha nada);
 * 3. a central da agência aparece **rotulada** e nunca no lugar do
 *    directo: sem o rótulo, o consultor liga à recepção convencido de
 *    que fala com quem vende.
 */
function CelulaDoAnunciante({ visita }) {
  const contacto = contactoDoAnunciante(visita);
  if (!temContactoDoAnunciante(visita)) {
    return <span className="text-muted-foreground">—</span>;
  }

  const directo = ligacaoTelefonica(contacto.telefone);
  const central = ligacaoTelefonica(contacto.telefoneDaAgencia);

  return (
    <div className="min-w-0 space-y-0.5 text-sm">
      {contacto.agencia ? (
        <p className="font-medium truncate max-w-[14rem]" title={contacto.agencia}>
          {contacto.agencia}
        </p>
      ) : null}
      {contacto.nome ? (
        <p className="text-muted-foreground truncate max-w-[14rem]">
          {contacto.nome}
        </p>
      ) : null}
      {directo ? (
        <a
          href={directo}
          className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
        >
          <Phone className="h-3 w-3" aria-hidden="true" />
          {telefoneLegivel(contacto.telefone)}
        </a>
      ) : null}
      {!directo && central ? (
        <a
          href={central}
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          title="Telefone geral da agência — não é o directo do comercial"
        >
          <Phone className="h-3 w-3" aria-hidden="true" />
          {telefoneLegivel(contacto.telefoneDaAgencia)} (central)
        </a>
      ) : null}
      {contacto.email ? (
        <a
          href={`mailto:${contacto.email}`}
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground truncate max-w-[14rem]"
        >
          <Mail className="h-3 w-3" aria-hidden="true" />
          {contacto.email}
        </a>
      ) : null}
    </div>
  );
}

function CelulaDosDados({ visita }) {
  const dados = dadosDaIA(visita);
  const partes = [
    dados.tipologia,
    dados.area !== null && dados.area !== undefined ? `${dados.area} m²` : "",
    dados.estado,
    dados.localizacao,
  ].filter(Boolean);
  if (!partes.length) return <span className="text-muted-foreground">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {partes.map((parte) => (
        <Badge key={parte} variant="outline" className="font-normal">
          {parte}
        </Badge>
      ))}
    </div>
  );
}

export default function VisitasTable({
  quadro,
  onAgendar,
  onMudarEstado,
  podeAgendar = true,
}) {
  const linhas = linhasDaTabela(quadro);

  if (!linhas.length) {
    return (
      <EmptyState
        title="Sem visitas"
        message="Os pedidos que os clientes fizerem no Portal aparecem aqui, já com os dados do anúncio lidos pela IA."
      />
    );
  }

  return (
    <div className="rounded-lg border border-border overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Imóvel</TableHead>
            <TableHead>Cliente</TableHead>
            <TableHead className="text-right">Preço</TableHead>
            <TableHead>Dados do anúncio</TableHead>
            <TableHead>Agência / Comercial</TableHead>
            <TableHead>Estado</TableHead>
            <TableHead>Agendamento</TableHead>
            <TableHead className="text-right">Acções</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {linhas.map((visita) => {
            const selo =
              ESTADO_DA_VISITA[String(visita?.status || "").toLowerCase()] || {
                texto: visita?.status || "—",
                variante: "outline",
              };
            return (
              <TableRow key={visita.id}>
                <TableCell>
                  <CelulaDoImovel visita={visita} />
                </TableCell>
                <TableCell>
                  <CelulaDoCliente visita={visita} />
                </TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  {formatarEuros(dadosDaIA(visita).preco)}
                </TableCell>
                <TableCell>
                  <CelulaDosDados visita={visita} />
                </TableCell>
                <TableCell>
                  <CelulaDoAnunciante visita={visita} />
                </TableCell>
                <TableCell>
                  <Badge variant={selo.variante}>{selo.texto}</Badge>
                </TableCell>
                <TableCell className="whitespace-nowrap text-sm">
                  {formatarData(visita?.scheduled_date)}
                </TableCell>
                <TableCell className="text-right">
                  {visita?.status === "solicitada" && podeAgendar ? (
                    <Button size="sm" onClick={() => onAgendar?.(visita)}>
                      Agendar
                    </Button>
                  ) : null}
                  {visita?.status === "agendada" ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => onMudarEstado?.(visita.id, "concluida")}
                    >
                      Concluir
                    </Button>
                  ) : null}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
