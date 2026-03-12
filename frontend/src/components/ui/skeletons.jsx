/**
 * Skeleton Loaders - Componentes de loading elegantes
 * Para melhor UX durante carregamento de dados
 */
import { Skeleton } from "./skeleton";

// Skeleton para cards de processo/cliente
export const ProcessCardSkeleton = () => (
  <div className="bg-card border rounded-lg p-4 space-y-3">
    <div className="flex items-start justify-between">
      <Skeleton className="h-5 w-[200px]" />
      <Skeleton className="h-5 w-[60px]" />
    </div>
    <div className="space-y-2">
      <Skeleton className="h-4 w-[150px]" />
      <Skeleton className="h-4 w-[180px]" />
    </div>
    <div className="flex gap-2">
      <Skeleton className="h-6 w-[80px]" />
      <Skeleton className="h-6 w-[60px]" />
    </div>
  </div>
);

// Skeleton para linhas de tabela
export const TableRowSkeleton = ({ columns = 5 }) => (
  <tr className="border-b">
    {Array.from({ length: columns }).map((_, i) => (
      <td key={i} className="p-4">
        <Skeleton className="h-4 w-full max-w-[150px]" />
      </td>
    ))}
  </tr>
);

// Skeleton para tabela completa
export const TableSkeleton = ({ rows = 5, columns = 5 }) => (
  <div className="rounded-md border">
    <table className="w-full">
      <thead>
        <tr className="border-b bg-muted/50">
          {Array.from({ length: columns }).map((_, i) => (
            <th key={i} className="p-4 text-left">
              <Skeleton className="h-4 w-[100px]" />
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {Array.from({ length: rows }).map((_, i) => (
          <TableRowSkeleton key={i} columns={columns} />
        ))}
      </tbody>
    </table>
  </div>
);

// Skeleton para dashboard stats
export const StatsCardSkeleton = () => (
  <div className="bg-card border rounded-lg p-4 space-y-2">
    <Skeleton className="h-4 w-[100px]" />
    <Skeleton className="h-8 w-[60px]" />
    <Skeleton className="h-3 w-[80px]" />
  </div>
);

// Skeleton para grid de stats
export const StatsGridSkeleton = ({ count = 4 }) => (
  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
    {Array.from({ length: count }).map((_, i) => (
      <StatsCardSkeleton key={i} />
    ))}
  </div>
);

// Skeleton para lista de processos
export const ProcessListSkeleton = ({ count = 6 }) => (
  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
    {Array.from({ length: count }).map((_, i) => (
      <ProcessCardSkeleton key={i} />
    ))}
  </div>
);

// Skeleton para detalhes de processo
export const ProcessDetailsSkeleton = () => (
  <div className="space-y-6">
    {/* Header */}
    <div className="flex items-start justify-between">
      <div className="space-y-2">
        <Skeleton className="h-8 w-[250px]" />
        <Skeleton className="h-4 w-[180px]" />
      </div>
      <div className="flex gap-2">
        <Skeleton className="h-10 w-[100px]" />
        <Skeleton className="h-10 w-[100px]" />
      </div>
    </div>
    
    {/* Stats */}
    <StatsGridSkeleton count={4} />
    
    {/* Content */}
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 space-y-4">
        <Skeleton className="h-[300px] w-full rounded-lg" />
      </div>
      <div className="space-y-4">
        <Skeleton className="h-[150px] w-full rounded-lg" />
        <Skeleton className="h-[150px] w-full rounded-lg" />
      </div>
    </div>
  </div>
);

// Skeleton para sidebar/navigation
export const SidebarSkeleton = () => (
  <div className="w-64 p-4 space-y-4">
    <Skeleton className="h-10 w-full" />
    <div className="space-y-2">
      {Array.from({ length: 6 }).map((_, i) => (
        <Skeleton key={i} className="h-8 w-full" />
      ))}
    </div>
  </div>
);

// Skeleton para form fields
export const FormFieldSkeleton = () => (
  <div className="space-y-2">
    <Skeleton className="h-4 w-[100px]" />
    <Skeleton className="h-10 w-full" />
  </div>
);

// Skeleton para formulário completo
export const FormSkeleton = ({ fields = 4 }) => (
  <div className="space-y-4">
    {Array.from({ length: fields }).map((_, i) => (
      <FormFieldSkeleton key={i} />
    ))}
    <Skeleton className="h-10 w-[120px]" />
  </div>
);

// ============================================
// NOVOS SKELETONS PARA PÁGINAS LAZY-LOADED
// ============================================

// Skeleton para página de Dashboard
export const DashboardPageSkeleton = () => (
  <div className="p-6 space-y-6" data-testid="dashboard-skeleton">
    {/* Header */}
    <div className="flex items-center justify-between">
      <Skeleton className="h-8 w-[200px]" />
      <Skeleton className="h-10 w-[150px]" />
    </div>
    
    {/* Stats Cards */}
    <StatsGridSkeleton count={4} />
    
    {/* Charts */}
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="bg-card border rounded-lg p-4">
        <Skeleton className="h-4 w-[150px] mb-4" />
        <Skeleton className="h-[250px] w-full" />
      </div>
      <div className="bg-card border rounded-lg p-4">
        <Skeleton className="h-4 w-[150px] mb-4" />
        <Skeleton className="h-[250px] w-full" />
      </div>
    </div>
    
    {/* Recent Activity */}
    <div className="bg-card border rounded-lg p-4">
      <Skeleton className="h-4 w-[180px] mb-4" />
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3">
            <Skeleton className="h-10 w-10 rounded-full" />
            <div className="flex-1 space-y-1">
              <Skeleton className="h-4 w-[200px]" />
              <Skeleton className="h-3 w-[150px]" />
            </div>
            <Skeleton className="h-4 w-[80px]" />
          </div>
        ))}
      </div>
    </div>
  </div>
);

// Skeleton para página de Clientes
export const ClientsPageSkeleton = () => (
  <div className="p-6 space-y-6" data-testid="clients-skeleton">
    {/* Header com busca */}
    <div className="flex items-center justify-between gap-4">
      <Skeleton className="h-8 w-[150px]" />
      <div className="flex gap-2">
        <Skeleton className="h-10 w-[250px]" />
        <Skeleton className="h-10 w-[120px]" />
      </div>
    </div>
    
    {/* Tabela */}
    <TableSkeleton rows={8} columns={6} />
    
    {/* Paginação */}
    <div className="flex items-center justify-between">
      <Skeleton className="h-4 w-[150px]" />
      <div className="flex gap-2">
        <Skeleton className="h-8 w-8" />
        <Skeleton className="h-8 w-8" />
        <Skeleton className="h-8 w-8" />
      </div>
    </div>
  </div>
);

// Skeleton para página de Processos (Kanban)
export const ProcessesPageSkeleton = () => (
  <div className="p-6 space-y-6" data-testid="processes-skeleton">
    {/* Header */}
    <div className="flex items-center justify-between">
      <Skeleton className="h-8 w-[180px]" />
      <div className="flex gap-2">
        <Skeleton className="h-10 w-[200px]" />
        <Skeleton className="h-10 w-[100px]" />
      </div>
    </div>
    
    {/* Kanban Columns */}
    <div className="flex gap-4 overflow-x-auto pb-4">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="flex-shrink-0 w-[300px] bg-muted/30 rounded-lg p-3 space-y-3">
          <div className="flex items-center justify-between">
            <Skeleton className="h-5 w-[120px]" />
            <Skeleton className="h-5 w-5 rounded-full" />
          </div>
          {Array.from({ length: 3 }).map((_, j) => (
            <ProcessCardSkeleton key={j} />
          ))}
        </div>
      ))}
    </div>
  </div>
);

// Skeleton para página de Settings
export const SettingsPageSkeleton = () => (
  <div className="p-6 space-y-6" data-testid="settings-skeleton">
    {/* Header */}
    <div className="border-b pb-4">
      <Skeleton className="h-8 w-[200px]" />
      <Skeleton className="h-4 w-[300px] mt-2" />
    </div>
    
    {/* Tabs */}
    <div className="flex gap-4 border-b">
      {Array.from({ length: 4 }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-[100px]" />
      ))}
    </div>
    
    {/* Form Content */}
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="space-y-4">
        <FormSkeleton fields={4} />
      </div>
      <div className="space-y-4">
        <FormSkeleton fields={3} />
      </div>
    </div>
  </div>
);

// Skeleton para página de Emails
export const EmailsPageSkeleton = () => (
  <div className="flex h-[calc(100vh-100px)]" data-testid="emails-skeleton">
    {/* Sidebar */}
    <div className="w-[300px] border-r p-4 space-y-2">
      <Skeleton className="h-10 w-full mb-4" />
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="p-3 space-y-2">
          <div className="flex justify-between">
            <Skeleton className="h-4 w-[150px]" />
            <Skeleton className="h-3 w-[50px]" />
          </div>
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-[80%]" />
        </div>
      ))}
    </div>
    
    {/* Content */}
    <div className="flex-1 p-6">
      <div className="space-y-4">
        <Skeleton className="h-8 w-[300px]" />
        <div className="flex gap-2">
          <Skeleton className="h-4 w-[150px]" />
          <Skeleton className="h-4 w-[200px]" />
        </div>
        <Skeleton className="h-[400px] w-full" />
      </div>
    </div>
  </div>
);

// Skeleton para página de Documentos
export const DocumentsPageSkeleton = () => (
  <div className="p-6 space-y-6" data-testid="documents-skeleton">
    {/* Header */}
    <div className="flex items-center justify-between">
      <Skeleton className="h-8 w-[180px]" />
      <Skeleton className="h-10 w-[150px]" />
    </div>
    
    {/* Filtros */}
    <div className="flex gap-4">
      <Skeleton className="h-10 w-[200px]" />
      <Skeleton className="h-10 w-[150px]" />
      <Skeleton className="h-10 w-[150px]" />
    </div>
    
    {/* Grid de Documentos */}
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
      {Array.from({ length: 12 }).map((_, i) => (
        <div key={i} className="bg-card border rounded-lg p-3 space-y-2">
          <Skeleton className="h-[100px] w-full rounded" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-3 w-[60%]" />
        </div>
      ))}
    </div>
  </div>
);

// Skeleton genérico para páginas
export const PageSkeleton = () => (
  <div className="p-6 space-y-6" data-testid="page-skeleton">
    <div className="flex items-center justify-between">
      <Skeleton className="h-8 w-[200px]" />
      <Skeleton className="h-10 w-[120px]" />
    </div>
    <div className="space-y-4">
      <Skeleton className="h-[400px] w-full rounded-lg" />
    </div>
  </div>
);

// Skeleton para Loading de página inteira
export const FullPageSkeleton = () => (
  <div className="flex items-center justify-center min-h-[400px]" data-testid="fullpage-skeleton">
    <div className="text-center space-y-4">
      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto" />
      <Skeleton className="h-4 w-[150px] mx-auto" />
    </div>
  </div>
);

export default {
  ProcessCardSkeleton,
  TableRowSkeleton,
  TableSkeleton,
  StatsCardSkeleton,
  StatsGridSkeleton,
  ProcessListSkeleton,
  ProcessDetailsSkeleton,
  SidebarSkeleton,
  FormFieldSkeleton,
  FormSkeleton,
  // Novos
  DashboardPageSkeleton,
  ClientsPageSkeleton,
  ProcessesPageSkeleton,
  SettingsPageSkeleton,
  EmailsPageSkeleton,
  DocumentsPageSkeleton,
  PageSkeleton,
  FullPageSkeleton,
};
