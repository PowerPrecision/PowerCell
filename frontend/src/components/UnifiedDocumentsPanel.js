/**
 * UnifiedDocumentsPanel - Painel Unificado de Documentos
 * Combina:
 * - Upload de ficheiros (S3)
 * - Links externos (Drive, Google Drive, SharePoint, etc.)
 *
 * NOTA: O separador "Links" só é visível para admin e CEO.
 *
 * PACOTE BL — CATEGORIA INDEX FORÇADA E PRIVADA:
 * A categoria "Index" (pasta cofre) contém os documentos enviados
 * diretamente pelo cliente através do Portal. Esta categoria só é visível
 * para admin/CEO/diretor/indexacao. O S3FileManager aplica o filtro
 * granular (por ficheiro e por categoria), mas este painel também pode
 * ser usado como ponto de controlo futuro se outros componentes de
 * documentos forem adicionados. O utilizador (user) é passado ao
 * S3FileManager via contexto de autenticação.
 */
import React, { useState, useMemo } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import { Upload, Link2 } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import S3FileManager from "./S3FileManager";
import DriveLinks from "./DriveLinks";

const UnifiedDocumentsPanel = ({ processId, clientName, onAIDataExtracted }) => {
  const [activeTab, setActiveTab] = useState("files");
  const { effectiveRole, user } = useAuth();

  // O separador "Links" só é visível para admin e CEO
  const canSeeLinks = useMemo(() => {
    const role = (effectiveRole || "").toLowerCase();
    return role === "admin" || role === "ceo";
  }, [effectiveRole]);

  // PACOTE BL — Verificação de acesso à categoria "Index" (pasta cofre).
  // Apenas admin/CEO/diretor/indexacao vêem documentos dessa categoria.
  // O filtro granular é aplicado no S3FileManager, mas mantemos a flag aqui
  // para defesa em profundidade e futura extensibilidade do painel.
  const canSeeIndexCategory = useMemo(() => {
    if (!user) return false;
    const role = (user.role || "").toLowerCase();
    return ["admin", "ceo", "diretor", "indexacao"].includes(role);
  }, [user]);

  // Se o utilizador não tem acesso ao tab Links e está nele, voltar ao files
  React.useEffect(() => {
    if (!canSeeLinks && activeTab === "links") {
      setActiveTab("files");
    }
  }, [canSeeLinks, activeTab]);

  return (
    <div className="space-y-2" data-testid="unified-documents-panel" data-can-see-index={canSeeIndexCategory ? "true" : "false"}>
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        {/* PACOTE DB — Separador "Links" temporariamente oculto (display: none).
            O código é mantido para reativação futura — não apagar. */}
        <TabsList className="" style={{ display: 'none' }}>
          <TabsTrigger value="files" className="text-xs gap-1.5" data-testid="files-tab">
            <Upload className="h-3.5 w-3.5" />
            Ficheiros
          </TabsTrigger>
          {canSeeLinks && (
            <TabsTrigger value="links" className="text-xs gap-1.5" data-testid="links-tab">
              <Link2 className="h-3.5 w-3.5" />
              Links
            </TabsTrigger>
          )}
        </TabsList>

        <TabsContent value="files" className="mt-3">
          <S3FileManager
            processId={processId}
            clientName={clientName}
            onAIDataExtracted={onAIDataExtracted}
          />
        </TabsContent>

        {/* PACOTE DB — TabsContent "Links" temporariamente oculto (display: none).
            Mantido para reativação futura. */}
        {canSeeLinks && (
          <TabsContent value="links" className="mt-3" style={{ display: 'none' }}>
            <DriveLinks
              processId={processId}
              clientName={clientName}
            />
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
};

export default UnifiedDocumentsPanel;
