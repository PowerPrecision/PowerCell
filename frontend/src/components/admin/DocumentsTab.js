/**
 * DocumentsTab - Componente de Documentos a Expirar para Admin Dashboard
 */
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { FileText, Users, Eye } from "lucide-react";

const DocumentsTab = ({ upcomingExpiries }) => {
  const navigate = useNavigate();

  if (upcomingExpiries.length === 0) {
    return (
      <Card className="border-border">
        <CardHeader>
          <CardTitle className="text-lg">Documentos a Expirar (Próximos 60 dias)</CardTitle>
          <CardDescription>Documentos de todos os clientes próximos da data de validade</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8 text-muted-foreground">
            <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Nenhum documento a expirar nos próximos 60 dias</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Ordenar documentos por data de expiração e agrupar por cliente
  const sortedDocs = [...upcomingExpiries].sort((a, b) => 
    new Date(a.expiry_date) - new Date(b.expiry_date)
  );
  
  // Agrupar por cliente mantendo a ordem
  const grouped = sortedDocs.reduce((acc, doc) => {
    const clientKey = doc.client_name || 'Sem Cliente';
    if (!acc[clientKey]) {
      acc[clientKey] = {
        client_name: doc.client_name,
        process_id: doc.process_id,
        documents: [],
        earliestExpiry: doc.expiry_date
      };
    }
    acc[clientKey].documents.push(doc);
    return acc;
  }, {});
  
  // Ordenar grupos pelo documento mais próximo a expirar
  const sortedGroups = Object.entries(grouped).sort((a, b) => 
    new Date(a[1].earliestExpiry) - new Date(b[1].earliestExpiry)
  );

  return (
    <Card className="border-border">
      <CardHeader>
        <CardTitle className="text-lg">Documentos a Expirar (Próximos 60 dias)</CardTitle>
        <CardDescription>Documentos agrupados por cliente e ordenados por data de validade</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {sortedGroups.map(([clientName, clientData]) => (
            <Card key={clientName} className="border-l-4 border-l-amber-500">
              <CardHeader className="py-3 px-4 bg-muted/30">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Users className="h-4 w-4 text-blue-900" />
                    {clientData.process_id ? (
                      <CardTitle 
                        className="text-base font-semibold text-blue-900 hover:text-blue-700 cursor-pointer hover:underline"
                        onClick={() => navigate(`/process/${clientData.process_id}`)}
                      >
                        {clientName}
                      </CardTitle>
                    ) : (
                      <CardTitle className="text-base font-semibold">{clientName}</CardTitle>
                    )}
                    <Badge variant="outline" className="ml-2">
                      {clientData.documents.length} documento(s)
                    </Badge>
                  </div>
                  {clientData.process_id && (
                    <Button variant="ghost" size="sm" onClick={() => navigate(`/process/${clientData.process_id}`)}>
                      <Eye className="h-4 w-4 mr-1" /> Ver Processo
                    </Button>
                  )}
                </div>
              </CardHeader>
              <CardContent className="pt-2 pb-3">
                <div className="space-y-2">
                  {clientData.documents.map((doc) => {
                    const daysUntil = Math.ceil((new Date(doc.expiry_date) - new Date()) / (1000 * 60 * 60 * 24));
                    const urgencyClass = daysUntil <= 7 ? 'bg-red-50 border-red-200 text-red-800' : 
                                         daysUntil <= 30 ? 'bg-amber-50 border-amber-200 text-amber-800' : 
                                         'bg-blue-50 border-blue-200 text-blue-800';
                    return (
                      <div key={doc.id} className={`flex items-center justify-between p-2 rounded border ${urgencyClass}`}>
                        <div className="flex items-center gap-3">
                          <FileText className="h-4 w-4" />
                          <span className="font-medium">{doc.document_name}</span>
                          <Badge variant="outline" className="text-xs">{doc.document_type}</Badge>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm">
                            {new Date(doc.expiry_date).toLocaleDateString('pt-PT')}
                          </span>
                          <Badge className={daysUntil <= 7 ? 'bg-red-500' : daysUntil <= 30 ? 'bg-amber-500' : 'bg-blue-500'}>
                            {daysUntil} dias
                          </Badge>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

export default DocumentsTab;
