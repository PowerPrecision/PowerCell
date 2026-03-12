/**
 * UnifiedDocumentsPanel - Painel Unificado de Documentos
 * Combina:
 * - Upload de ficheiros (S3)
 * - Links externos (Drive, Google Drive, SharePoint, etc.)
 */
import React, { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import { Upload, Link2 } from "lucide-react";
import S3FileManager from "./S3FileManager";
import DriveLinks from "./DriveLinks";

const UnifiedDocumentsPanel = ({ processId, clientName, onAIDataExtracted }) => {
  const [activeTab, setActiveTab] = useState("files");

  return (
    <div className="space-y-2" data-testid="unified-documents-panel">
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-2 h-8">
          <TabsTrigger value="files" className="text-xs gap-1.5" data-testid="files-tab">
            <Upload className="h-3.5 w-3.5" />
            Ficheiros
          </TabsTrigger>
          <TabsTrigger value="links" className="text-xs gap-1.5" data-testid="links-tab">
            <Link2 className="h-3.5 w-3.5" />
            Links
          </TabsTrigger>
        </TabsList>

        <TabsContent value="files" className="mt-3">
          <S3FileManager 
            processId={processId}
            clientName={clientName}
            onAIDataExtracted={onAIDataExtracted}
          />
        </TabsContent>

        <TabsContent value="links" className="mt-3">
          <DriveLinks 
            processId={processId} 
            clientName={clientName} 
          />
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default UnifiedDocumentsPanel;
