/**
 * UsersTab - Componente de Utilizadores para Admin Dashboard
 */
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";
import { Users, UserPlus, CheckCircle, XCircle, Edit, Mail, Eye } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "../../contexts/AuthContext";

const roleLabels = { 
  admin: "Administrador", 
  ceo: "CEO", 
  consultor: "Consultor", 
  mediador: "Intermediário de Crédito", 
  intermediario: "Intermediário de Crédito", 
  diretor: "Diretor(a)", 
  administrativo: "Administrativo(a)"
};

const roleColors = {
  admin: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  ceo: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400",
  consultor: "bg-blue-100 text-blue-800 dark:bg-teal-600/30 dark:text-blue-400",
  mediador: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400",
  intermediario: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400",
  diretor: "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400",
  administrativo: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
};

const UsersTab = ({ users, onImpersonate }) => {
  const navigate = useNavigate();
  const { user: currentUser } = useAuth();

  const handleImpersonate = async (targetUser) => {
    try {
      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/admin/impersonate/${targetUser.id}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        }
      });
      if (response.ok) {
        const data = await response.json();
        localStorage.setItem('originalToken', localStorage.getItem('token'));
        localStorage.setItem('token', data.access_token);
        toast.success(`A ver como ${targetUser.name}`);
        window.location.reload();
      } else {
        toast.error('Erro ao iniciar visualização');
      }
    } catch (error) {
      toast.error('Erro ao iniciar visualização');
    }
  };

  return (
    <Card className="border-border">
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <Users className="h-5 w-5" />
          Gestão de Utilizadores
        </CardTitle>
        <CardDescription>
          {users.length} utilizadores no sistema
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-6">
          {/* Quick Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
              <p className="text-sm text-muted-foreground">Consultores</p>
              <p className="text-2xl font-bold text-blue-800">
                {users.filter(u => u.role === 'consultor').length}
              </p>
            </div>
            <div className="p-4 bg-emerald-50 rounded-lg border border-emerald-200">
              <p className="text-sm text-muted-foreground">Intermediários</p>
              <p className="text-2xl font-bold text-emerald-800">
                {users.filter(u => ['mediador', 'intermediario'].includes(u.role)).length}
              </p>
            </div>
            <div className="p-4 bg-purple-50 rounded-lg border border-purple-200">
              <p className="text-sm text-muted-foreground">Diretores</p>
              <p className="text-2xl font-bold text-purple-800">
                {users.filter(u => u.role === 'diretor').length}
              </p>
            </div>
            <div className="p-4 bg-amber-50 rounded-lg border border-amber-200">
              <p className="text-sm text-muted-foreground">Administrativos</p>
              <p className="text-2xl font-bold text-amber-800">
                {users.filter(u => u.role === 'administrativo').length}
              </p>
            </div>
          </div>

          {/* Users Table */}
          <div>
            <div className="flex justify-between items-center mb-3">
              <h4 className="font-medium">Todos os Utilizadores</h4>
              <Button 
                size="sm"
                onClick={() => navigate('/utilizadores')}
                className="bg-teal-600 hover:bg-teal-700"
              >
                <UserPlus className="h-4 w-4 mr-2" />
                Gerir Utilizadores
              </Button>
            </div>
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Nome</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Papel</TableHead>
                    <TableHead>Estado</TableHead>
                    <TableHead className="text-right">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {users.map((u) => (
                    <TableRow key={u.id}>
                      <TableCell className="font-medium">{u.name}</TableCell>
                      <TableCell>{u.email}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className={roleColors[u.role] || ""}>
                          {roleLabels[u.role] || u.role}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {u.is_active !== false ? (
                          <Badge className="bg-green-100 text-green-800"><CheckCircle className="h-3 w-3 mr-1" />Ativo</Badge>
                        ) : (
                          <Badge variant="secondary"><XCircle className="h-3 w-3 mr-1" />Inativo</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => window.open(`mailto:${u.email}`, '_blank')}
                            title="Enviar Email"
                            className="h-8 w-8 text-blue-600 hover:text-blue-800 hover:bg-blue-50"
                          >
                            <Mail className="h-4 w-4" />
                          </Button>
                          {currentUser?.role === 'admin' && u.id !== currentUser?.id && u.role !== 'admin' && (
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleImpersonate(u)}
                              title="Ver como este utilizador"
                              className="h-8 w-8 text-purple-600 hover:text-purple-800 hover:bg-purple-50"
                            >
                              <Eye className="h-4 w-4" />
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => navigate('/utilizadores')}
                            title="Editar"
                            className="h-8 w-8"
                          >
                            <Edit className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default UsersTab;
