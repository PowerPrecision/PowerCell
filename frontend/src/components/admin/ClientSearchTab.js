/**
 * ClientSearchTab - Componente de Pesquisa de Clientes para Admin Dashboard
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Badge } from "../ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";
import { Search, Eye } from "lucide-react";

const ClientSearchTab = ({ processes, workflowStatuses }) => {
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState("");

  const filteredProcesses = processes.filter(p => 
    p.client_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    p.client_email?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    p.client_phone?.includes(searchTerm)
  );

  return (
    <Card className="border-border">
      <CardHeader>
        <CardTitle className="text-lg">Pesquisar Cliente</CardTitle>
        <CardDescription>Encontre e visualize informações de clientes</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input 
              placeholder="Pesquisar por nome, email ou telefone..." 
              className="pl-10" 
              value={searchTerm} 
              onChange={(e) => setSearchTerm(e.target.value)} 
            />
          </div>

          {searchTerm.length >= 2 ? (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Nome</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Telefone</TableHead>
                    <TableHead>Fase</TableHead>
                    <TableHead>Valor</TableHead>
                    <TableHead className="text-right">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredProcesses.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                        Nenhum cliente encontrado com &ldquo;{searchTerm}&rdquo;
                      </TableCell>
                    </TableRow>
                  ) : (
                    filteredProcesses.map((process) => {
                      const status = workflowStatuses.find(s => s.name === process.status);
                      return (
                        <TableRow 
                          key={process.id} 
                          className="cursor-pointer hover:bg-muted/50" 
                          onClick={() => navigate(`/process/${process.id}`)}
                        >
                          <TableCell className="font-medium">{process.client_name}</TableCell>
                          <TableCell>{process.client_email}</TableCell>
                          <TableCell>{process.client_phone || "-"}</TableCell>
                          <TableCell>
                            <Badge className={`bg-${status?.color || 'gray'}-100 text-${status?.color || 'gray'}-800 border`}>
                              {status?.label || process.status}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            {process.property_value ? `€${process.property_value.toLocaleString('pt-PT')}` : "-"}
                          </TableCell>
                          <TableCell className="text-right">
                            <Button 
                              variant="ghost" 
                              size="icon" 
                              onClick={(e) => { e.stopPropagation(); navigate(`/process/${process.id}`); }}
                            >
                              <Eye className="h-4 w-4" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      );
                    })
                  )}
                </TableBody>
              </Table>
            </div>
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              <Search className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p className="text-sm">Digite pelo menos 2 caracteres para pesquisar</p>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default ClientSearchTab;
