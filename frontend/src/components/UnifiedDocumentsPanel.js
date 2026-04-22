/**
 * UnifiedDocumentsPanel - Painel Unificado de Documentos
 * Combina:
 * - Upload de ficheiros (S3)
 * - Links externos (Drive, Google Drive, SharePoint, etc.)
 *
 * NOTA: O separador "Links" só é visível para admin e CEO.
 */
import React, { useState, useMemo } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import { Upload, Link2 } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import S3FileManager from "./S3FileManager";
import DriveLinks from "./DriveLinks";

const UnifiedDocumentsPanel = ({ processId, clientName, onAIDataExtracted }) => {
  const [activeTab, setActiveTab] = useState("files");
  const { effectiveRole } = useAuth();

  // O separador "Links" só é visível para admin e CEO
  const canSeeLinks = useMemo(() => {
    const role = (effectiveRole || "").toLowerCase();
    return role === "admin" || role === "ceo";
  }, [effectiveRole]);

  // Se o utilizador não tem acesso ao tab Links e está nele, voltar ao files
  React.useEffect(() => {
    if (!canSeeLinks && activeTab === "links") {
      setActiveTab("files");
    }
  }, [canSeeLinks, activeTab]);

  return (
    <div className="space-y-2" data-testid="unified-documents-panel">
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className={canSeeLinks ? "grid w-full grid-cols-2 h-8" : ""}>
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

        {canSeeLinks && (
          <TabsContent value="links" className="mt-3">
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
