/**
 * Kanban Components Index
 * 
 * Export central para todos os componentes do Kanban Board.
 * Facilita a importação noutros ficheiros.
 */

// Core Components
export { default as KanbanCard } from './KanbanCard';
export { default as KanbanColumn } from './KanbanColumn';
export { default as KanbanHeader } from './KanbanHeader';
export { default as KanbanSkeleton } from './KanbanSkeleton';
export { default as SearchResultsList } from './SearchResultsList';

// Modals
export { default as ProcessDetailsModal } from './ProcessDetailsModal';
export { default as CreateClientModal } from './CreateClientModal';
export { default as AssignUsersModal } from './AssignUsersModal';

// Constants & Utils
export { statusColors, statusHeaderColors, openEmailClient } from './constants';
