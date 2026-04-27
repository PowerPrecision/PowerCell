/**
 * DocumentsPage — Navegador de Ficheiros S3/OneDrive.
 *
 * Página standalone para explorar documentos sem contexto de processo.
 * Redireciona para o dashboard com uma mensagem se não houver contexto.
 * Para gestão de documentos de um processo específico, use ProcessDetails.
 */
import React from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Database, FolderOpen } from "lucide-react";

const DocumentsPage = () => {
  return (
    <DashboardLayout title="Ficheiros">
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Database className="h-6 w-6 text-primary" />
            Ficheiros
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Navegue nos ficheiros dos processos diretamente a partir da ficha do processo.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <FolderOpen className="h-5 w-5 text-muted-foreground" />
              Aceder a Ficheiros
            </CardTitle>
            <CardDescription>
              Os ficheiros de cada processo estão disponíveis na página de detalhes do processo.
              Selecione um processo no Quadro Geral ou na lista de processos para gerir os seus documentos.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-center py-8 text-muted-foreground text-sm">
              <p>Use o menu lateral para navegar para os seus processos e aceder aos ficheiros.</p>
            </div>
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
};

export default DocumentsPage;
