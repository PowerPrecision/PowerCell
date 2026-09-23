/**
 * ProcessDomainTabsList — os oito domínios de dados do processo
 * (Épico 8, Eixo 1).
 *
 * É a barra de separadores do cartão "Dados do Processo": Cliente,
 * Financeiros, Imóvel/CPCV, Crédito, Agenda, Emails, Visitas e Mensagens.
 *
 * COMPONENTE DE APRESENTAÇÃO E SEM ESTADO. Tem de ser renderizado dentro
 * do `<Tabs>` do contentor — é ele que detém o separador activo; os
 * `TabsTrigger` do Radix falam com esse contexto, não com props.
 *
 * A única coisa que vem de fora é a contagem de mensagens por ler, que
 * pinta o sinal vermelho.
 */
import {
  Briefcase,
  Building2,
  CalendarClock,
  CreditCard,
  Home,
  MessageSquare,
  Send,
  User,
} from "lucide-react";

import { TabsList, TabsTrigger } from "../ui/tabs";

const CLASSE_BASE = "gap-1 text-xs sm:text-sm py-1.5 sm:py-2";

/**
 * @param {Object} props
 * @param {number} [props.unreadMessagesCount] - Mensagens do portal por ler.
 */
export default function ProcessDomainTabsList({ unreadMessagesCount = 0 }) {
  return (
    <TabsList className="grid w-full grid-cols-3 sm:grid-cols-8 gap-1 h-auto p-1">
      {/* ── DADOS DO CLIENTE ── */}
      <TabsTrigger
        value="personal"
        className={`${CLASSE_BASE} bg-teal-50 dark:bg-teal-900/20 data-[state=active]:bg-teal-100 dark:data-[state=active]:bg-teal-900/40`}
      >
        <User className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
        <span className="hidden sm:inline">Cliente</span>
      </TabsTrigger>

      {/* ── DADOS DO PROCESSO/NEGÓCIO ── */}
      <TabsTrigger value="financial" className={CLASSE_BASE}>
        <Briefcase className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
        <span className="hidden sm:inline">Financeiros</span>
      </TabsTrigger>
      <TabsTrigger value="realestate" className={CLASSE_BASE}>
        <Building2 className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
        <span className="hidden sm:inline">Imóvel / CPCV</span>
      </TabsTrigger>
      <TabsTrigger value="credit" className={CLASSE_BASE}>
        <CreditCard className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
        <span className="hidden sm:inline">Crédito</span>
      </TabsTrigger>
      <TabsTrigger value="prazos" className={CLASSE_BASE}>
        <CalendarClock className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
        {/* PACOTE DH — rótulo evoluído de "Prazos" para "Agenda" */}
        <span className="hidden sm:inline">Agenda</span>
      </TabsTrigger>
      <TabsTrigger
        value="emails"
        className={`${CLASSE_BASE} bg-blue-50 dark:bg-blue-900/20 data-[state=active]:bg-blue-100 dark:data-[state=active]:bg-blue-900/40`}
      >
        <Send className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
        <span className="hidden sm:inline">Emails</span>
      </TabsTrigger>
      <TabsTrigger
        value="visitas"
        className={`${CLASSE_BASE} bg-emerald-50 dark:bg-emerald-900/20 data-[state=active]:bg-emerald-100 dark:data-[state=active]:bg-emerald-900/40`}
      >
        <Home className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
        <span className="hidden sm:inline">Visitas</span>
      </TabsTrigger>
      <TabsTrigger
        value="mensagens"
        className={`${CLASSE_BASE} bg-violet-50 dark:bg-violet-900/20 data-[state=active]:bg-violet-100 dark:data-[state=active]:bg-violet-900/40 relative`}
      >
        <MessageSquare className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
        <span className="hidden sm:inline">Mensagens</span>
        {unreadMessagesCount > 0 && (
          <span
            className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center"
            aria-label={`${unreadMessagesCount} mensagens por ler`}
          >
            {unreadMessagesCount > 9 ? "9+" : unreadMessagesCount}
          </span>
        )}
      </TabsTrigger>
    </TabsList>
  );
}
