/**
 * GlobalUploadProgress - Barra de progresso global para uploads
 * 
 * Mostra uma barra fixa no canto inferior direito com o progresso
 * de todos os uploads activos, mesmo quando o utilizador navega.
 */
import { useState } from "react";
import { useUploadProgress } from "../contexts/UploadProgressContext";
import { Progress } from "./ui/progress";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { ScrollArea } from "./ui/scroll-area";
import { 
  X, 
  ChevronUp, 
  ChevronDown, 
  CheckCircle, 
  XCircle, 
  Loader2,
  FolderUp,
  FileText
} from "lucide-react";

const GlobalUploadProgress = () => {
  const { uploadList, hasActiveUploads, dismissUpload } = useUploadProgress();
  const [expanded, setExpanded] = useState(true);
  const [minimized, setMinimized] = useState(false);
  
  // Se não há uploads, não mostrar nada
  if (uploadList.length === 0) {
    return null;
  }
  
  // Calcular totais
  const totalProcessed = uploadList.reduce((acc, u) => acc + u.processed, 0);
  const totalFiles = uploadList.reduce((acc, u) => acc + u.total, 0);
  const totalErrors = uploadList.reduce((acc, u) => acc + u.errors, 0);
  const overallProgress = totalFiles > 0 ? Math.round((totalProcessed / totalFiles) * 100) : 0;
  
  // Ícone de estado
  const getStatusIcon = (status) => {
    switch (status) {
      case "success":
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case "error":
        return <XCircle className="h-4 w-4 text-red-500" />;
      default:
        return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
    }
  };
  
  // Versão minimizada - apenas ícone com contador
  if (minimized) {
    return (
      <div 
        className="fixed bottom-4 right-4 z-50"
        data-testid="global-upload-minimized"
      >
        <Button
          onClick={() => setMinimized(false)}
          className="h-12 w-12 rounded-full bg-gradient-to-r from-purple-500 to-indigo-500 hover:from-purple-600 hover:to-indigo-600 shadow-lg"
        >
          <div className="relative">
            <FolderUp className="h-5 w-5 text-white" />
            {hasActiveUploads && (
              <span className="absolute -top-2 -right-2 h-4 w-4 bg-yellow-400 rounded-full flex items-center justify-center">
                <Loader2 className="h-3 w-3 animate-spin text-yellow-800" />
              </span>
            )}
            {!hasActiveUploads && uploadList.length > 0 && (
              <span className="absolute -top-2 -right-2 h-4 w-4 bg-green-500 rounded-full flex items-center justify-center">
                <CheckCircle className="h-3 w-3 text-white" />
              </span>
            )}
          </div>
        </Button>
      </div>
    );
  }
  
  return (
    <div 
      className="fixed bottom-4 right-4 z-50 w-80 bg-background border rounded-lg shadow-xl overflow-hidden"
      data-testid="global-upload-progress"
    >
      {/* Header */}
      <div 
        className="bg-gradient-to-r from-purple-500 to-indigo-500 px-4 py-2 flex items-center justify-between cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2 text-white">
          <FolderUp className="h-4 w-4" />
          <span className="font-medium text-sm">
            {hasActiveUploads ? "Upload em Progresso" : "Upload Concluído"}
          </span>
          {hasActiveUploads && (
            <Badge variant="secondary" className="bg-white/20 text-white text-xs">
              {overallProgress}%
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-white/70 hover:text-white hover:bg-white/20"
            onClick={(e) => { e.stopPropagation(); setMinimized(true); }}
          >
            <ChevronDown className="h-4 w-4" />
          </Button>
          {!hasActiveUploads && (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-white/70 hover:text-white hover:bg-white/20"
              onClick={(e) => { 
                e.stopPropagation(); 
                uploadList.forEach(u => dismissUpload(u.id));
              }}
            >
              <X className="h-4 w-4" />
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-white/70 hover:text-white hover:bg-white/20"
          >
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </Button>
        </div>
      </div>
      
      {/* Barra de progresso global */}
      {hasActiveUploads && (
        <div className="px-4 py-2 border-b">
          <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
            <span>{totalProcessed} de {totalFiles} ficheiros</span>
            {totalErrors > 0 && (
              <span className="text-red-500">{totalErrors} erros</span>
            )}
          </div>
          <Progress value={overallProgress} className="h-2" />
        </div>
      )}
      
      {/* Lista de uploads (expandida) */}
      {expanded && (
        <ScrollArea className="max-h-60">
          <div className="p-2 space-y-2">
            {uploadList.map((upload) => (
              <div 
                key={upload.id}
                className="bg-muted/50 rounded-lg p-2"
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    {getStatusIcon(upload.status)}
                    <span className="text-sm font-medium truncate max-w-[180px]">
                      {upload.clientName}
                    </span>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-5 w-5"
                    onClick={() => dismissUpload(upload.id)}
                  >
                    <X className="h-3 w-3" />
                  </Button>
                </div>
                
                {upload.status === "running" && (
                  <>
                    <Progress value={upload.progress} className="h-1.5 mb-1" />
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>{upload.processed}/{upload.total}</span>
                      {upload.currentFile && (
                        <span className="flex items-center gap-1 truncate max-w-[150px]">
                          <FileText className="h-3 w-3" />
                          {upload.currentFile}
                        </span>
                      )}
                    </div>
                  </>
                )}
                
                {upload.status === "success" && (
                  <p className="text-xs text-green-600">
                    {upload.processed} ficheiros processados
                    {upload.errors > 0 && ` (${upload.errors} erros)`}
                  </p>
                )}
                
                {upload.status === "error" && (
                  <p className="text-xs text-red-500">
                    {upload.message || "Erro no upload"}
                  </p>
                )}
              </div>
            ))}
          </div>
        </ScrollArea>
      )}
    </div>
  );
};

export default GlobalUploadProgress;
