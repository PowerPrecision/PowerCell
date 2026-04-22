/**
 * ====================================================================
 * PÁGINA DE DOWNLOAD VIA LINK TEMPORÁRIO - POWERCELL
 * ====================================================================
 * Permite ao cliente descarregar documentação através de um link temporário.
 * Não requer autenticação.
 * ====================================================================
 */
import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import {
  Download,
  File,
  CheckCircle,
  AlertCircle,
  Loader2,
  Clock,
  FileText,
  Package,
} from "lucide-react";
import { toast } from "sonner";

const API_URL = process.env.REACT_APP_BACKEND_URL;

const TempLinkDownloadPage = () => {
  const { token } = useParams();

  const [loading, setLoading] = useState(true);
  const [linkInfo, setLinkInfo] = useState(null);
  const [files, setFiles] = useState([]);
  const [error, setError] = useState(null);
  const [downloadingIndex, setDownloadingIndex] = useState(null);

  // Verificar link ao carregar
  useEffect(() => {
    verifyLink();
  }, [token]);

  const verifyLink = async () => {
    try {
      // Verificar link
      const linkResponse = await fetch(`${API_URL}/api/temp-links/public/${token}`);
      const linkData = await linkResponse.json();

      if (!linkData.valid) {
        setError(linkData.error || "Link inválido ou expirado");
        setLoading(false);
        return;
      }

      setLinkInfo(linkData);

      // Se é link de download, buscar lista de ficheiros
      if (linkData.link_type === "download" && linkData.file_count > 0) {
        const filesResponse = await fetch(`${API_URL}/api/temp-links/public/${token}/files`);
        const filesData = await filesResponse.json();

        if (filesResponse.ok) {
          setFiles(filesData.files || []);
        }
      }
    } catch (err) {
      setError("Erro ao verificar o link. Tente novamente.");
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async (fileIndex) => {
    setDownloadingIndex(fileIndex);

    try {
      const response = await fetch(
        `${API_URL}/api/temp-links/public/${token}/download/${fileIndex}`
      );

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Erro ao descarregar ficheiro");
      }

      const data = await response.json();

      // Abrir URL de download em nova janela
      window.open(data.url, "_blank");

      toast.success("Download iniciado!");
    } catch (err) {
      toast.error(err.message || "Erro ao descarregar ficheiro");
    } finally {
      setDownloadingIndex(null);
    }
  };

  const handleDownloadAll = async () => {
    setDownloadingIndex(-1); // -1 = batch in progress
    try {
      // O backend retorna um ZIP com todos os ficheiros
      const response = await fetch(
        `${API_URL}/api/temp-links/public/${token}/download-all`
      );

      if (!response.ok) {
        // Tentar parsear erro como JSON, fallback para texto
        let errorMsg = "Erro ao descarregar ficheiros";
        try {
          const error = await response.json();
          errorMsg = error.detail || errorMsg;
        } catch {
          errorMsg = await response.text() || errorMsg;
        }
        throw new Error(errorMsg);
      }

      // Obter o nome do ficheiro do header Content-Disposition
      const disposition = response.headers.get('Content-Disposition');
      let zipName = 'documentos.zip';
      if (disposition) {
        const match = disposition.match(/filename[^;=\n]*=(['"]?)([^'";\n]*)\1/);
        if (match && match[2]) {
          zipName = match[2];
        }
      }

      // Receber o ZIP como blob e iniciar download
      const blob = await response.blob();
      const blobUrl = URL.createObjectURL(blob);

      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = zipName;
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();

      // Cleanup
      setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(blobUrl);
      }, 250);

      toast.success(`${files.length} ficheiro(s) descarregado(s) como ZIP!`);
    } catch (err) {
      toast.error(err.message || "Erro ao descarregar ficheiros");
    } finally {
      setDownloadingIndex(null);
    }
  };

  const getFileIcon = (filename) => {
    const ext = filename.split(".").pop().toLowerCase();
    if (ext === "pdf") {
      return <FileText className="h-8 w-8 text-red-500" />;
    }
    if (["jpg", "jpeg", "png"].includes(ext)) {
      return <File className="h-8 w-8 text-green-500" />;
    }
    if (["doc", "docx"].includes(ext)) {
      return <File className="h-8 w-8 text-blue-500" />;
    }
    return <File className="h-8 w-8 text-gray-500" />;
  };

  // Loading state
  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-50 flex items-center justify-center p-4">
        <div className="text-center">
          <Loader2 className="h-12 w-12 animate-spin text-blue-600 mx-auto mb-4" />
          <p className="text-gray-600">A verificar link...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-red-50 to-orange-50 flex items-center justify-center p-4">
        <Card className="max-w-md w-full">
          <CardContent className="pt-6 text-center">
            <AlertCircle className="h-16 w-16 text-red-500 mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Link Inválido</h2>
            <p className="text-gray-600 mb-6">{error}</p>
            <p className="text-sm text-gray-500">
              Se precisa de ajuda, contacte o seu consultor.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-50 flex items-center justify-center p-4">
      <div className="max-w-2xl w-full space-y-6">
        {/* Header */}
        <div className="text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-100 rounded-full mb-4">
            <Package className="h-8 w-8 text-blue-600" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Documentação Disponível</h1>
          <p className="text-gray-600 mt-2">
            Olá, <strong>{linkInfo?.client_name}</strong>!
          </p>
          <p className="text-gray-500 mt-1">
            Tem {files.length} documento(s) disponível(eis) para download.
          </p>
        </div>

        {/* Info Card */}
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 text-sm text-gray-600">
              <Clock className="h-4 w-4" />
              <span>Link válido por tempo limitado</span>
            </div>
            {linkInfo?.description && (
              <p className="mt-2 text-sm text-gray-700 bg-blue-50 p-3 rounded-lg">
                <strong>Notas:</strong> {linkInfo.description}
              </p>
            )}
          </CardContent>
        </Card>

        {/* Files List */}
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-gray-900">Documentos</h3>
              {files.length > 1 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleDownloadAll}
                  disabled={downloadingIndex !== null}
                >
                  <Download className="h-4 w-4 mr-2" />
                  Descarregar Todos
                </Button>
              )}
            </div>

            <div className="space-y-3">
              {files.map((file, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between bg-white border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow"
                >
                  <div className="flex items-center gap-4">
                    {getFileIcon(file.filename)}
                    <div>
                      <p className="font-medium text-gray-700">{file.filename}</p>
                      <p className="text-xs text-gray-500">Documento {index + 1}</p>
                    </div>
                  </div>

                  <Button
                    onClick={() => handleDownload(index)}
                    disabled={downloadingIndex !== null}
                    className="bg-blue-600 hover:bg-blue-700"
                  >
                    {downloadingIndex === index ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        A baixar...
                      </>
                    ) : (
                      <>
                        <Download className="h-4 w-4 mr-2" />
                        Descarregar
                      </>
                    )}
                  </Button>
                </div>
              ))}
            </div>

            {files.length === 0 && (
              <div className="text-center py-8">
                <File className="h-12 w-12 text-gray-400 mx-auto mb-3" />
                <p className="text-gray-500">Nenhum documento disponível</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Help Text */}
        <div className="text-center text-sm text-gray-500 space-y-1">
          <p>Clique em cada botão para descarregar o respetivo documento.</p>
          <p>O link de download será válido durante algumas horas.</p>
        </div>

        {/* Footer */}
        <p className="text-center text-sm text-gray-500">
          PowerCell - Sistema de Gestão de Processos
        </p>
      </div>
    </div>
  );
};

export default TempLinkDownloadPage;
