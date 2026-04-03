/**
 * Componentes partilhados para páginas de Administração
 * Elimina duplicação de código entre RGPDAdminPage e ClientRegistrationsAdminPage
 */
import React from "react";
import { Card, CardContent } from "../ui/card";
import { Badge } from "../ui/badge";
import { Input } from "../ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Button } from "../ui/button";
import { 
  AlertTriangle, 
  Trash2, 
  Loader2, 
  ChevronLeft, 
  ChevronRight, 
  Search,
  XCircle,
  RefreshCw,
  Eye,
  Edit
} from "lucide-react";

/**
 * StatCard - Card de estatísticas para dashboards admin
 */
export const StatCard = ({ title, value, icon: Icon, color }) => (
  <Card>
    <CardContent className="p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">{title}</p>
          <p className={`text-2xl font-bold ${color}`}>{value}</p>
        </div>
        <Icon className={`h-8 w-8 ${color} opacity-50`} />
      </div>
    </CardContent>
  </Card>
);

/**
 * ConfirmDeleteModal - Modal de confirmação de eliminação reutilizável
 */
export const ConfirmDeleteModal = ({ 
  open, 
  onClose, 
  onConfirm, 
  title = "Confirmar Eliminação",
  description = "Tem a certeza que deseja eliminar este item? Esta ação não pode ser revertida.",
  itemName,
  itemDetails,
  loading = false 
}) => (
  <Dialog open={open} onOpenChange={onClose}>
    <DialogContent className="max-w-md">
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2 text-red-600">
          <AlertTriangle className="h-5 w-5" />
          {title}
        </DialogTitle>
        <DialogDescription>{description}</DialogDescription>
      </DialogHeader>

      <div className="py-4 bg-red-50 dark:bg-red-950/30 rounded-lg p-4">
        {itemName && <p className="font-medium">{itemName}</p>}
        {itemDetails && <p className="text-sm text-muted-foreground">{itemDetails}</p>}
      </div>

      <DialogFooter>
        <Button variant="outline" onClick={onClose} disabled={loading}>Cancelar</Button>
        <Button variant="destructive" onClick={onConfirm} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Trash2 className="h-4 w-4 mr-2" />}
          Eliminar
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
);

/**
 * EmptyState - Estado vazio para listas
 */
export const EmptyState = ({ icon: Icon, message, action }) => (
  <div className="text-center py-12 text-muted-foreground">
    {Icon && <Icon className="h-12 w-12 mx-auto mb-4 opacity-50" />}
    <p>{message}</p>
    {action}
  </div>
);

/**
 * LoadingState - Estado de loading para listas
 */
export const LoadingState = ({ rows = 6, cols = 4 }) => (
  <div className="space-y-2 py-4">
    {Array.from({ length: rows }).map((_, i) => (
      <div key={i} className="flex gap-3">
        {Array.from({ length: cols }).map((_, j) => (
          <div key={j} className={`h-8 bg-muted animate-pulse rounded ${j === 0 ? 'flex-[2]' : 'flex-1'}`} />
        ))}
      </div>
    ))}
  </div>
);

/**
 * Pagination - Componente de paginação reutilizável
 */
export const Pagination = ({ page, totalPages, total, onPageChange }) => {
  if (totalPages <= 1) return null;
  
  return (
    <div className="flex items-center justify-between pt-4 border-t mt-4">
      <p className="text-sm text-muted-foreground">Página {page} de {totalPages} ({total} registos)</p>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={() => onPageChange(Math.max(1, page - 1))} disabled={page === 1}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <Button variant="outline" size="sm" onClick={() => onPageChange(Math.min(totalPages, page + 1))} disabled={page === totalPages}>
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
};

/**
 * AccessRestricted - Componente para páginas com acesso restrito
 */
export const AccessRestricted = ({ allowedRoles = ["admin", "staff"], userRole }) => {
  if (allowedRoles.includes(userRole)) return null;
  
  return (
    <div className="text-center py-12">
      <XCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
      <h2 className="text-xl font-semibold">Acesso Restrito</h2>
      <p className="text-muted-foreground">Apenas administradores podem aceder a esta página.</p>
    </div>
  );
};

/**
 * AdminSearchFilter - Componente de pesquisa e filtro reutilizável
 */
export const AdminSearchFilter = ({ 
  search, onSearchChange, statusFilter, onStatusChange, statusOptions = [], searchPlaceholder = "Pesquisar..."
}) => (
  <Card>
    <CardContent className="p-4">
      <div className="flex flex-wrap gap-4">
        <div className="flex-1 min-w-0 sm:min-w-[200px]">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input placeholder={searchPlaceholder} value={search} onChange={(e) => onSearchChange(e.target.value)} className="pl-9" />
          </div>
        </div>
        {statusOptions.length > 0 && (
          <Select value={statusFilter || "all"} onValueChange={(v) => onStatusChange(v === "all" ? "" : v)}>
            <SelectTrigger className="w-full sm:w-[180px]"><SelectValue placeholder="Todos os estados" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos</SelectItem>
              {statusOptions.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>
    </CardContent>
  </Card>
);

/**
 * PageHeader - Header padrão para páginas de administração
 */
export const PageHeader = ({ icon: Icon, title, description, onRefresh }) => (
  <div className="flex items-center justify-between">
    <div>
      <h1 className="text-2xl font-bold flex items-center gap-2">
        {Icon && <Icon className="h-6 w-6" />}
        {title}
      </h1>
      {description && <p className="text-muted-foreground">{description}</p>}
    </div>
    {onRefresh && (
      <Button variant="outline" onClick={onRefresh}>
        <RefreshCw className="h-4 w-4 mr-2" />
        Atualizar
      </Button>
    )}
  </div>
);

/**
 * AdminTable - Tabela reutilizável para admin pages
 */
export const AdminTable = ({ 
  columns, 
  data, 
  renderRow, 
  loading = false,
  emptyIcon,
  emptyMessage = "Nenhum registo encontrado"
}) => (
  <Card>
    <CardContent className="p-0">
      {loading ? (
        <LoadingState />
      ) : data.length === 0 ? (
        <EmptyState icon={emptyIcon} message={emptyMessage} />
      ) : (
        <div className="space-y-2 p-4">
          {/* Table Header */}
          <div className="grid gap-2 px-3 py-2 text-sm font-medium text-muted-foreground border-b" style={{ gridTemplateColumns: columns.grid }}>
            {columns.headers.map((header, i) => (
              <div key={i} className={columns.aligns?.[i] || ''}>{header}</div>
            ))}
          </div>
          {/* Rows */}
          {data.map((item, index) => renderRow(item, index))}
        </div>
      )}
    </CardContent>
  </Card>
);

/**
 * ActionButtons - Botões de ação padronizados para tabelas
 */
export const ActionButtons = ({ onView, onEdit, onDelete, showEdit = true }) => (
  <div className="flex justify-end gap-1">
    {onView && (
      <Button variant="ghost" size="sm" onClick={onView} title="Ver detalhes">
        <Eye className="h-4 w-4" />
      </Button>
    )}
    {showEdit && onEdit && (
      <Button variant="ghost" size="sm" onClick={onEdit} title="Editar">
        <Edit className="h-4 w-4" />
      </Button>
    )}
    {onDelete && (
      <Button variant="ghost" size="sm" onClick={onDelete} title="Eliminar" className="text-red-600 hover:text-red-700 hover:bg-red-50">
        <Trash2 className="h-4 w-4" />
      </Button>
    )}
  </div>
);
