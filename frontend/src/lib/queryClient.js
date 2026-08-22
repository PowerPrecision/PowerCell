/**
 * ====================================================================
 * QUERY CLIENT CONFIGURATION - TanStack Query v5
 * ====================================================================
 * Configuração global do QueryClient para gestão de estado de servidor.
 * 
 * BENEFÍCIOS:
 * - Caching automático com staleTime
 * - Auto-refetch on window focus (crítico para CRM)
 * - Deduplicação de requests
 * - Background refetching
 * - Retry inteligente
 * ====================================================================
 */

import { QueryClient } from '@tanstack/react-query';

/**
 * Configuração do QueryClient otimizada para CRM.
 * 
 * PADRÕES DEFINIDOS:
 * - staleTime: 1 minuto (evita fetches excessivos ao navegar rápido)
 * - gcTime: 5 minutos (cache garbage collection)
 * - refetchOnWindowFocus: true (actualiza ao voltar de outra tab)
 * - refetchOnReconnect: true (actualiza ao recuperar ligação)
 * - retry: 2 tentativas para erros de rede
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Tempo até os dados serem considerados "stale" (obsoletos)
      // 1 minuto é ideal para CRM: evita fetches excessivos mas garante
      // dados razoavelmente actualizados
      staleTime: 60 * 1000, // 1 minuto
      
      // Tempo até o cache ser limpo (garbage collection)
      // 5 minutos é suficiente para navegação entre páginas
      gcTime: 5 * 60 * 1000, // 5 minutos
      
      // CRÍTICO: Refetch quando o utilizador volta da tab do email/whatsapp
      // para o CRM. Garante que o Kanban e Filme da Lead actualizam-se.
      refetchOnWindowFocus: true,
      
      // Refetch quando a ligação é recuperada
      refetchOnReconnect: true,
      
      // Não refetch em mount se os dados ainda são fresh
      refetchOnMount: true,
      
      // Retry configurado para erros de rede
      retry: (failureCount, error) => {
        // Não tentar retry para erros 4xx (client errors)
        if (error?.status >= 400 && error?.status < 500) {
          return false;
        }
        // Máximo 2 tentativas para erros de rede
        return failureCount < 2;
      },
      
      // Delay entre retries (exponential backoff)
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
      
      // Estrutura de dados estruturada para debug
      structuralSharing: true,
    },
    mutations: {
      // Retry para mutations (operações de escrita)
      retry: false, // Normalmente não queremos retry para mutations
      
      // Timeout para mutations
      gcTime: 0, // Não guardar cache de mutations
    },
  },
});

/**
 * Query Keys Factory
 * 
 * Centraliza todas as query keys para consistência e type-safety.
 * Segue o padrão de factory functions para criar keys compostas.
 */
export const queryKeys = {
  // Processos
  processes: {
    all: ['processes'],
    lists: () => [...queryKeys.processes.all, 'list'],
    list: (filters) => [...queryKeys.processes.lists(), filters],
    details: () => [...queryKeys.processes.all, 'detail'],
    detail: (id) => [...queryKeys.processes.details(), id],
    // Prefixo de todas as queries Kanban (sem filters) — invalidar só o Kanban,
    // nunca ['processes'] inteiro (detalhe/listas/my-clients).
    kanbanAll: () => [...queryKeys.processes.all, 'kanban'],
    kanban: (filters) => [...queryKeys.processes.all, 'kanban', filters],
    // Query key INDEPENDENTE para Concluídos — quando completedDays muda,
    // só esta query é invalidada, não a query das colunas activas
    kanbanCompleted: (filters) => [...queryKeys.processes.all, 'kanban-completed', filters],
    myClients: (filters) => [...queryKeys.processes.all, 'my-clients', filters],
  },
  
  // Histórico/Timeline
  history: {
    all: ['history'],
    byProcess: (processId) => [...queryKeys.history.all, 'process', processId],
  },
  
  // Atividades/Comentários
  activities: {
    all: ['activities'],
    byProcess: (processId) => [...queryKeys.activities.all, 'process', processId],
  },
  
  // Prazos/Deadlines
  deadlines: {
    all: ['deadlines'],
    lists: () => [...queryKeys.deadlines.all, 'list'],
    byProcess: (processId) => [...queryKeys.deadlines.all, 'process', processId],
    myDeadlines: () => [...queryKeys.deadlines.all, 'my'],
    calendar: (consultorId, mediadorId) => [...queryKeys.deadlines.all, 'calendar', { consultorId, mediadorId }],
  },
  
  // Documentos
  documents: {
    all: ['documents'],
    byProcess: (processId) => [...queryKeys.documents.all, 'process', processId],
    expiries: (processId) => [...queryKeys.documents.all, 'expiries', processId],
    upcomingExpiries: (days) => [...queryKeys.documents.all, 'upcoming', days],
  },
  
  // Notificações
  notifications: {
    all: ['notifications'],
    list: (unreadOnly) => [...queryKeys.notifications.all, { unreadOnly }],
  },
  
  // Tarefas
  tasks: {
    all: ['tasks'],
    list: (filters) => [...queryKeys.tasks.all, 'list', filters],
    myTasks: (includeCompleted) => [...queryKeys.tasks.all, 'my', { includeCompleted }],
    byProcess: (processId) => [...queryKeys.tasks.all, 'process', processId],
  },
  
  // Emails
  emails: {
    all: ['emails'],
    // Prefixo só da lista Webmail — new_email / refresh NÃO devem invalidar
    // emails de processo, drafts, stats ou monitored.
    webmailAll: () => [...queryKeys.emails.all, 'webmail'],
    webmail: (filters) => [...queryKeys.emails.all, 'webmail', filters],
    byProcess: (processId, direction) => [...queryKeys.emails.all, 'process', processId, { direction }],
    stats: (processId) => [...queryKeys.emails.all, 'stats', processId],
    monitored: (processId) => [...queryKeys.emails.all, 'monitored', processId],
    drafts: (limit) => [...queryKeys.emails.all, 'drafts', { limit }],
  },
  
  // Anotações
  annotations: {
    all: ['annotations'],
    byProcess: (processId, includeResolved) => [...queryKeys.annotations.all, 'process', processId, { includeResolved }],
    byDocument: (documentPath, processId) => [...queryKeys.annotations.all, 'document', documentPath, processId],
  },
  
  // Utilizadores
  users: {
    all: ['users'],
    list: (role) => [...queryKeys.users.all, 'list', { role }],
  },
  
  // Leads
  leads: {
    all: ['leads'],
    list: (filters) => [...queryKeys.leads.all, 'list', filters],
    byStatus: () => [...queryKeys.leads.all, 'by-status'],
    detail: (id) => [...queryKeys.leads.all, 'detail', id],
  },
  
  // Imóveis
  properties: {
    all: ['properties'],
    list: (filters) => [...queryKeys.properties.all, 'list', filters],
    detail: (id) => [...queryKeys.properties.all, 'detail', id],
  },
  
  // Clientes
  clients: {
    all: ['clients'],
    list: (filters) => [...queryKeys.clients.all, 'list', filters],
    detail: (id) => [...queryKeys.clients.all, 'detail', id],
  },
  
  // Workflow Statuses
  workflowStatuses: {
    all: ['workflow-statuses'],
    list: () => [...queryKeys.workflowStatuses.all, 'list'],
  },
  
  // Estatísticas
  stats: {
    all: ['stats'],
    dashboard: () => [...queryKeys.stats.all, 'dashboard'],
  },

  // Desempenho da Equipa (Admin/CEO)
  teamPerformance: {
    all: ['team-performance'],
    range: (startDate, endDate) => [...queryKeys.teamPerformance.all, 'range', { startDate, endDate }],
  },

  // Auditoria (RGPD — trilha de alterações)
  audit: {
    all: ['audit'],
    trail: (params) => [...queryKeys.audit.all, 'trail', params],
    stats: () => [...queryKeys.audit.all, 'stats'],
  },
  
  // Financeiro
  finance: {
    all: ['finance'],
    summary: (params) => [...queryKeys.finance.all, 'summary', params],
    monthly: (params) => [...queryKeys.finance.all, 'monthly', params],
    commissions: (params) => [...queryKeys.finance.all, 'commissions', params],
    performance: (params) => [...queryKeys.finance.all, 'performance', params],
  },

  // Registos de Clientes (Admin — formulário público)
  clientRegistrations: {
    all: ['client-registrations'],
    list: (params) => [...queryKeys.clientRegistrations.all, 'list', params],
    stats: () => [...queryKeys.clientRegistrations.all, 'stats'],
  },

  // Background Jobs (Centro de Operações — importações/análises em massa)
  backgroundJobs: {
    all: ['background-jobs'],
    list: (statusFilter) => [...queryKeys.backgroundJobs.all, 'list', { statusFilter }],
    notifications: () => [...queryKeys.backgroundJobs.all, 'notifications'],
    metrics: (days) => [...queryKeys.backgroundJobs.all, 'metrics', { days }],
  },
};

/**
 * Invalida o bundle ProcessDetails (processo + side panels + kanban + cliente).
 * Usar após saves/assigns/comentários/prazos em ProcessDetails.
 */
export async function invalidateProcessDetailsQueries(
  queryClient,
  processId,
  { clientId } = {},
) {
  const tasks = [
    queryClient.invalidateQueries({ queryKey: queryKeys.processes.detail(processId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.history.byProcess(processId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.activities.byProcess(processId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.deadlines.byProcess(processId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.processes.kanbanAll() }),
    queryClient.invalidateQueries({ queryKey: queryKeys.processes.lists() }),
  ];
  if (clientId) {
    tasks.push(
      queryClient.invalidateQueries({ queryKey: queryKeys.clients.detail(clientId) }),
    );
  }
  await Promise.all(tasks);
}

export default queryClient;
