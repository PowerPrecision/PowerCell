import { useState, useEffect } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { 
  Search, Eye, FileText, Phone, Mail, MapPin, Euro, Filter
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { getProcesses } from "../services/api";
import { TableSkeleton } from "../components/ui/skeletons";

const ProcessesPage = () => {
  const navigate = useNavigate();
  const [processes, setProcesses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");

  useEffect(() => {
    fetchProcesses();
  }, []);

  const fetchProcesses = async () => {
    try {
      setLoading(true);
      const response = await getProcesses();
      setProcesses(response.data);
    } catch (error) {
      toast.error("Erro ao carregar processos");
    } finally {
      setLoading(false);
    }
  };

  const filteredProcesses = processes.filter(p => 
    p.client_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    p.client_email?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    p.client_phone?.includes(searchTerm) ||
    p.property_location?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const getPriorityBadge = (priority) => {
    const colors = {
      high: "bg-red-100 text-red-800",
      medium: "bg-yellow-100 text-yellow-800",
      low: "bg-green-100 text-green-800",
    };
    const labels = {
      high: "Alta",
      medium: "Média",
      low: "Baixa",
    };
    return { color: colors[priority] || colors.medium, label: labels[priority] || priority };
  };

  if (loading) {
    return (
      <DashboardLayout title="Todos os Processos">
        <div className="space-y-6 p-6">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <FileText className="h-5 w-5" />
                    Lista de Processos
                  </CardTitle>
                  <CardDescription>
                    A carregar processos...
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <TableSkeleton rows={8} columns={7} />
            </CardContent>
          </Card>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title="Todos os Processos">
      <div className="space-y-6 p-6">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg flex items-center gap-2">
                  <FileText className="h-5 w-5" />
                  Lista de Processos
                </CardTitle>
                <CardDescription>
                  Total de {processes.length} processos no sistema
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="relative mb-4">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input 
                placeholder="Pesquisar por nome, email, telefone ou localização..." 
                className="pl-10" 
                value={searchTerm} 
                onChange={(e) => setSearchTerm(e.target.value)} 
              />
            </div>

            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Cliente</TableHead>
                    <TableHead>Contacto</TableHead>
                    <TableHead>Localização</TableHead>
                    <TableHead>Valor</TableHead>
                    <TableHead>Prioridade</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredProcesses.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                        {searchTerm ? `Nenhum processo encontrado com "${searchTerm}"` : "Nenhum processo encontrado"}
                      </TableCell>
                    </TableRow>
                  ) : (
                    filteredProcesses.map((process) => {
                      const priorityBadge = getPriorityBadge(process.priority);
                      return (
                        <TableRow 
                          key={process.id} 
                          className="cursor-pointer hover:bg-muted/50"
                          onClick={() => navigate(`/process/${process.id}`)}
                        >
                          <TableCell className="font-medium">
                            <div>
                              <p>{process.client_name}</p>
                              {process.client_nif && (
                                <p className="text-xs text-muted-foreground">NIF: {process.client_nif}</p>
                              )}
                            </div>
                          </TableCell>
                          <TableCell>
                            <div className="text-sm space-y-1">
                              {process.client_email && (
                                <div className="flex items-center gap-1">
                                  <Mail className="h-3 w-3 text-muted-foreground" />
                                  <span className="text-xs">{process.client_email}</span>
                                </div>
                              )}
                              {process.client_phone && (
                                <div className="flex items-center gap-1">
                                  <Phone className="h-3 w-3 text-muted-foreground" />
                                  <span className="text-xs">{process.client_phone}</span>
                                </div>
                              )}
                            </div>
                          </TableCell>
                          <TableCell>
                            {process.property_location ? (
                              <div className="flex items-center gap-1">
                                <MapPin className="h-3 w-3 text-muted-foreground" />
                                <span className="text-sm">{process.property_location}</span>
                              </div>
                            ) : (
                              "-"
                            )}
                          </TableCell>
                          <TableCell>
                            {process.property_value ? (
                              <div className="text-sm">
                                <div className="font-medium text-emerald-600 flex items-center gap-1">
                                  <Euro className="h-3 w-3" />
                                  {process.property_value.toLocaleString('pt-PT')}
                                </div>
                                {process.loan_amount && (
                                  <div className="text-xs text-muted-foreground">
                                    Financ: €{process.loan_amount.toLocaleString('pt-PT')}
                                  </div>
                                )}
                              </div>
                            ) : (
                              "-"
                            )}
                          </TableCell>
                          <TableCell>
                            {process.priority && (
                              <Badge className={priorityBadge.color}>
                                {priorityBadge.label}
                              </Badge>
                            )}
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline" className="capitalize">
                              {process.status?.replace(/_/g, ' ')}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-right">
                            <Button 
                              variant="ghost" 
                              size="icon"
                              onClick={(e) => {
                                e.stopPropagation();
                                navigate(`/process/${process.id}`);
                              }}
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
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
};

export default ProcessesPage;
