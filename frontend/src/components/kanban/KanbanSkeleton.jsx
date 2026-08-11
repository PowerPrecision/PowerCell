/**
 * KanbanSkeleton Component
 * 
 * Estado de loading do Kanban Board.
 * Mostra skeletons enquanto os dados estão a ser carregados.
 */
import { memo } from 'react';
import { Skeleton } from '../ui/skeleton';

const KanbanSkeleton = memo(() => {
  return (
    <div className="space-y-4" data-testid="kanban-loading">
      {/* Header Skeleton */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <Skeleton className="h-7 w-[250px] mb-2" />
          <Skeleton className="h-4 w-[180px]" />
        </div>
        <div className="flex items-center gap-2 w-full sm:w-auto">
          <Skeleton className="h-10 w-full sm:w-64" />
          <Skeleton className="h-10 w-10" />
          <Skeleton className="h-10 w-10" />
        </div>
      </div>
      
      {/* Kanban Columns Skeleton */}
      <div className="flex gap-4 overflow-hidden">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="flex-shrink-0 w-[320px]">
            <Skeleton className="h-12 w-full rounded-t-lg" />
            <div className="bg-muted/30 min-h-[60vh] rounded-b-lg p-2 space-y-2">
              {[1, 2, 3].map((j) => (
                <Skeleton key={j} className="h-24 w-full rounded-lg" />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
});

KanbanSkeleton.displayName = 'KanbanSkeleton';

export default KanbanSkeleton;
