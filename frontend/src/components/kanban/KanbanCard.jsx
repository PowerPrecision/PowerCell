/**
 * KanbanCard Component
 * 
 * Cartão individual do Kanban - representa um processo/cliente.
 * 
 * PERFORMANCE CRÍTICA:
 * - Envolve com React.memo para prevenir re-renders desnecessários
 * - Só re-renderiza quando as props exatas mudam
 * - Isola estado do formulário do estado do board
 * 
 * DESTAQUE DE PRIORIDADE:
 * - Alta: Borda esquerda grossa vermelha, fundo subtil, ícone 🔥 no título
 * - Média: Borda esquerda amarela
 * - Baixa: Sem destaque especial
 * 
 * @param {Object} process - Dados do processo
 * @param {boolean} isDragging - Se o cartão está a ser arrastado
 * @param {Function} onDragStart - Handler de início de drag
 * @param {Function} onCardClick - Handler de clique no cartão
 * @param {Function} onViewProcess - Handler para ver processo completo
 */
import React, { memo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent } from '../ui/card';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { GripVertical, Eye, User, Phone, Mail, Lock, Users, Flame, AlertTriangle } from 'lucide-react';
import { safeString } from '../../utils/safeString';
import { format } from 'date-fns';

// Comparador customizado para React.memo
// Só re-renderiza se o processo ou estado de drag mudar
const arePropsEqual = (prevProps, nextProps) => {
  return (
    prevProps.process.id === nextProps.process.id &&
    prevProps.process.client_name === nextProps.process.client_name &&
    prevProps.process.process_number === nextProps.process.process_number &&
    prevProps.process.consultor_name === nextProps.process.consultor_name &&
    prevProps.process.mediador_name === nextProps.process.mediador_name &&
    prevProps.process.prioridade === nextProps.process.prioridade &&
    prevProps.process.priority === nextProps.process.priority &&
    prevProps.process.under_35 === nextProps.process.under_35 &&
    prevProps.process.updated_at === nextProps.process.updated_at &&
    prevProps.process.labels === nextProps.process.labels &&
    prevProps.isDragging === nextProps.isDragging &&
    prevProps.isLocked === nextProps.isLocked &&
    prevProps.lockedBy === nextProps.lockedBy
  );
};

const KanbanCard = memo(({ 
  process, 
  columnName,
  isDragging, 
  onDragStart, 
  onCardClick,
  draggingCard,
  isLocked = false,
  lockedBy,
}) => {
  const navigate = useNavigate();

  // Check if process has a 2nd proponent
  const hasSecondProponent = 
    (process.co_buyers && process.co_buyers.length > 0) ||
    (process.compradores && process.compradores.length > 1) ||
    !!process.comprador2 ||
    !!process.segundo_proponente;

  // Handlers memoizados para prevenir re-criação
  const handleDragStart = useCallback((e) => {
    onDragStart?.(e, process, columnName);
  }, [onDragStart, process, columnName]);

  const handleClick = useCallback((e) => {
    // Não navegar se estiver arrastando
    if (!draggingCard) {
      onCardClick?.(process);
    }
  }, [draggingCard, onCardClick, process]);

  const handleViewProcess = useCallback((e) => {
    e.stopPropagation();
    navigate(`/process/${process.id}`);
  }, [navigate, process.id]);

  const isCurrentlyDragging = isDragging || draggingCard?.process?.id === process.id;

  // Compute priority level (normalised)
  const prioridade = (process.prioridade || process.priority || '').toLowerCase();
  const isAlta = prioridade === 'alta' || prioridade === 'high';
  const isMedia = prioridade === 'media' || prioridade === 'medium';
  const isBaixa = prioridade === 'baixa' || prioridade === 'low';

  // Compute priority-based styling
  // Alta: Gross left border (4px red-500), subtle red bg tint, 🔥 icon
  // Media: Left border amber-400
  // Baixa / none: No special border (except 2nd proponent indicator)
  const getPriorityStyles = () => {
    if (isAlta) {
      return {
        borderClass: 'border-l-[4px] border-l-red-500',
        bgClass: 'bg-red-50/60 dark:bg-red-950/20',
        shadowClass: 'shadow-red-200/50 dark:shadow-red-900/20',
      };
    }
    if (isMedia) {
      return {
        borderClass: 'border-l-[3px] border-l-amber-400',
        bgClass: 'bg-amber-50/30 dark:bg-amber-950/10',
        shadowClass: '',
      };
    }
    return {
      borderClass: hasSecondProponent ? 'border-l-[3px] border-l-blue-600' : '',
      bgClass: '',
      shadowClass: '',
    };
  };

  const priorityStyles = getPriorityStyles();

  return (
    <Card
      className={`cursor-pointer hover:shadow-md transition-all duration-200 relative ${
        isCurrentlyDragging ? "opacity-50" : ""
      } ${priorityStyles.borderClass} ${priorityStyles.bgClass} ${priorityStyles.shadowClass}`}
      draggable
      onDragStart={handleDragStart}
      onClick={handleClick}
      data-testid={`process-card-${process.id}`}
    >
      {/* Lock indicator badge */}
      {isLocked && (
        <div
          className="absolute top-1.5 right-1.5 flex items-center gap-1 bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 text-[10px] px-1.5 py-0.5 rounded-full font-medium z-10"
          title={`Em edição por ${lockedBy}`}
        >
          <Lock className="h-2.5 w-2.5" />
          <span className="hidden sm:inline max-w-[80px] truncate">{lockedBy}</span>
        </div>
      )}
      <CardContent className="p-2">
        <div className="space-y-1.5">
          {/* Linha 1: Número do processo + Badge de prioridade */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <GripVertical className="h-3 w-3 text-muted-foreground flex-shrink-0 cursor-grab" />
              <span className="text-[10px] font-medium text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                #{process.process_number || '—'}
              </span>
              {isAlta && (
                <Badge className="bg-red-500 text-white border-red-600 text-[9px] px-1.5 py-0 h-4 gap-0.5 animate-pulse shadow-sm shadow-red-300/50">
                  <Flame className="h-2.5 w-2.5" /> Alta
                </Badge>
              )}
              {isMedia && (
                <Badge className="bg-amber-100 text-amber-700 border-amber-300 text-[9px] px-1.5 py-0 h-4">
                  Média
                </Badge>
              )}
              {isBaixa && (
                <Badge className="bg-green-100 text-green-700 border-green-300 text-[9px] px-1.5 py-0 h-4">
                  Baixa
                </Badge>
              )}
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-5 w-5 flex-shrink-0"
              onClick={handleViewProcess}
              title="Ver processo"
              data-testid={`view-process-${process.id}`}
            >
              <Eye className="h-3 w-3" />
            </Button>
          </div>
          
          {/* Linha 2: Nome do cliente - SEMPRE VISÍVEL, com 🔥 para Alta */}
          <p 
            className={`text-sm leading-snug break-words whitespace-normal min-w-0 ${
              isAlta ? 'font-bold text-red-900 dark:text-red-100' : 'font-semibold'
            }`} 
            style={{ wordBreak: 'break-word', overflowWrap: 'anywhere' }}
            title={process.client_name || process.client_id || ''}
          >
            {isAlta && <span className="mr-1" title="Prioridade Alta">🔥</span>}
            {safeString(process.client_name) || (process.client_id ? 'Cliente #' + process.client_id.slice(0,6) : '—')}
          </p>
          
          {/* Linha 3: Consultor (se existir) */}
          {process.consultor_name && (
            <div className="flex items-center gap-1">
              <User className="h-3 w-3 text-muted-foreground" />
              <span className="text-[10px] text-muted-foreground truncate">
                {safeString(process.consultor_name)}
              </span>
            </div>
          )}
          
          {/* Linha 4: Mediador (se existir) */}
          {process.mediador_name && (
            <div className="flex items-center gap-1">
              <User className="h-3 w-3 text-muted-foreground" />
              <span className="text-[10px] text-muted-foreground truncate">
                {safeString(process.mediador_name)}
              </span>
            </div>
          )}
          
          {/* Linha 5: Badges e indicadores */}
          <div className="flex items-center gap-1 flex-wrap">
            {hasSecondProponent && (
              <span className="text-[9px] bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300 px-2 py-0.5 rounded-full font-medium whitespace-nowrap">
                👥 2 Proponentes
              </span>
            )}
            {process.under_35 && (
              <Badge variant="outline" className="text-[9px] bg-green-50 text-green-700 border-green-200 px-1 py-0 h-4">
                &lt;35
              </Badge>
            )}
            {process.process_type && (
              <Badge variant="outline" className="text-[9px] px-1 py-0 h-4 truncate max-w-[100px]">
                {process.process_type.replace(/_/g, ' ')}
              </Badge>
            )}
            {/* Completion date badge for concluded processes */}
            {(columnName === 'concluidos' || columnName === 'desistencias') && process.updated_at && (
              <span className="text-[9px] bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300 px-2 py-0.5 rounded-full font-medium whitespace-nowrap border border-emerald-200 dark:border-emerald-800">
                ✓ {format(new Date(process.updated_at), "dd/MM/yyyy")}
              </span>
            )}
          </div>
          
          {/* Linha 5b: Tags/Labels pills */}
          {process.labels && process.labels.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1">
              {process.labels.map((label, idx) => (
                <Badge key={idx} variant="outline" className="text-[10px] px-1.5 py-0 h-4 font-normal bg-muted/50">
                  {safeString(label)}
                </Badge>
              ))}
            </div>
          )}
          
          {/* Linha 6: Contacto rápido */}
          {(process.client_phone || process.client_email) && (
            <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
              {process.client_phone && (
                <span className="flex items-center gap-0.5 truncate">
                  <Phone className="h-2.5 w-2.5" />
                  {safeString(process.client_phone)}
                </span>
              )}
              {process.client_email && !process.client_phone && (
                <span className="flex items-center gap-0.5 truncate">
                  <Mail className="h-2.5 w-2.5" />
                  {safeString(process.client_email)}
                </span>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}, arePropsEqual);

// Nome para debugging
KanbanCard.displayName = 'KanbanCard';

export default KanbanCard;
