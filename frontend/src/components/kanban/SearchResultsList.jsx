/**
 * SearchResultsList Component
 * 
 * Lista de resultados de pesquisa em formato de tabela.
 * Mostrado quando o utilizador pesquisa com pelo menos 2 caracteres
 * e selecciona o modo de vista "lista".
 */
import React, { memo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { ScrollArea } from '../ui/scroll-area';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table';
import { Search, Phone, Eye } from 'lucide-react';
import { statusColors } from './constants';
import { safeString } from '../../utils/safeString';

const SearchResultsList = memo(({
  processes,
  searchTerm,
}) => {
  const navigate = useNavigate();

  const handleRowClick = useCallback((processId) => {
    navigate(`/process/${processId}`);
  }, [navigate]);

  const handleViewClick = useCallback((e, processId) => {
    e.stopPropagation();
    navigate(`/process/${processId}`);
  }, [navigate]);

  return (
    <Card className="border-border">
      <CardHeader className="pb-2">
        <CardTitle className="text-lg flex items-center gap-2">
          <Search className="h-5 w-5" />
          Resultados da Pesquisa
          <Badge variant="secondary">{processes.length}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <ScrollArea className="h-[300px] sm:h-[500px]">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Cliente</TableHead>
                  <TableHead>Contacto</TableHead>
                  <TableHead>Fase</TableHead>
                  <TableHead>Valor</TableHead>
                  <TableHead>Consultor</TableHead>
                  <TableHead>Intermediário</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {processes.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                      Nenhum resultado para &quot;{searchTerm}&quot;
                    </TableCell>
                  </TableRow>
                ) : (
                  processes.map((process) => (
                    <TableRow
                      key={process.id}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => handleRowClick(process.id)}
                    >
                      <TableCell>
                        <div>
                          <p className="font-medium">{safeString(process.client_name)}</p>
                          <p className="text-xs text-muted-foreground font-semibold">
                            #{process.process_number || '—'}
                          </p>
                          {process.under_35 && (
                            <Badge variant="outline" className="text-[10px] bg-green-50 text-green-700 mt-1">
                              &lt;35 anos
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="text-sm">
                          <p className="flex items-center gap-1">
                            <Phone className="h-3 w-3" />
                            {process.client_phone || '-'}
                          </p>
                          <p className="text-muted-foreground text-xs truncate max-w-[150px]">
                            {safeString(process.client_email)}
                          </p>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge 
                          className={`${statusColors[process.columnColor]} border text-xs`}
                        >
                          {safeString(process.columnLabel)}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-medium">
                        {process.property_value 
                          ? `€${process.property_value.toLocaleString('pt-PT')}`
                          : '-'
                        }
                      </TableCell>
                      <TableCell className="text-sm">
                        {process.consultor_name || '-'}
                      </TableCell>
                      <TableCell className="text-sm">
                        {process.mediador_name || '-'}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={(e) => handleViewClick(e, process.id)}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
});

SearchResultsList.displayName = 'SearchResultsList';

export default SearchResultsList;
