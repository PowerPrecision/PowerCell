/**
 * ====================================================================
 * PÁGINA DE UPLOAD VIA LINK TEMPORÁRIO - POWERCELL
 * ====================================================================
 * Permite ao cliente carregar documentação através de um link temporário.
 * Não requer autenticação.
 * ====================================================================
 */
import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Progress } from "../components/ui/progress";
import {
  Upload,
  File,
  CheckCircle,
  AlertCircle,
  Loader2,
  Clock,
  X,
  FileText,
  Image,
  FilePlus,
} from "lucide-react";
import { toast } from "sonner";

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function TempLinkUploadPage() {
  const { token } = useParams();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [linkInfo, setLinkInfo] = useState(null);
  const [error, setError] = useState(null);
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [dragActive, setDragActive] = useState(false);
  
  // Ref para o input de ficheiros (substitui document.getElementById)
  const fileInputRef = useRef(null);

  // Verificar link ao carregar
  useEffect(() => {
    verifyLink();
  }, [token]);

  const verifyLink = async () => {
    try {
      const response = await fetch(`${API_URL}/api/temp-links/public/${token}`);
      const data = await response.json();

      if (!data.valid) {
        setError(data.error || "Link inválido ou expirado");
      } else {
        setLinkInfo(data);
      }
    } catch (err) {
      setError("Erro ao verificar o link. Tente novamente.");
    } finally {
      setLoading(false);
    }
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleFileInput = (e) => {
    if (e.target.files) {
      handleFiles(Array.from(e.target.files));
    }
  };

  const handleFiles = (newFiles) => {
    // Validar tipos de ficheiro
    const allowedTypes = [
      "application/pdf",
      "image/jpeg",
      "image/png",
      "image/tiff",
      "application/msword",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ];

    const validFiles = newFiles.filter((file) => {
      const ext = file.name.split(".").pop().toLowerCase();
      const allowedExts = ["pdf", "jpg", "jpeg", "png", "tiff", "tif", "doc", "docx"];
      return allowedExts.includes(ext) || allowedTypes.includes(file.type);
    });

    if (validFiles.length !== newFiles.length) {
      toast.warning("Alguns ficheiros foram ignorados (formato não suportado)");
    }

    setFiles((prev) => [...prev, ...validFiles]);
  };

  const removeFile = (index) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  const getFileIcon = (file) => {
    const ext = file.name.split(".").pop().toLowerCase();
    if (["jpg", "jpeg", "png", "tiff", "tif"].includes(ext)) {
      return <Image className="h-5 w-5 text-green-500" />;
    }
    return <FileText className="h-5 w-5 text-blue-500" />;
  };

  const handleUpload = async () => {
    if (files.length === 0) {
      toast.error("Selecione pelo menos um ficheiro");
      return;
    }

    setUploading(true);
    setUploadProgress(0);

    const formData = new FormData();
    files.forEach((file) => {
      formData.append("files", file);
    });

    try {
      const xhr = new XMLHttpRequest();

      xhr.upload.addEventListener("progress", (event) => {
        if (event.lengthComputable) {
          const progress = Math.round((event.loaded / event.total) * 100);
          setUploadProgress(progress);
        }
      });

      xhr.addEventListener("load", () => {
        if (xhr.status === 200) {
          const response = JSON.parse(xhr.responseText);
          setUploadedFiles(response.files || []);
          setFiles([]);
          toast.success(response.message || "Ficheiros carregados com sucesso!");
        } else {
          const error = JSON.parse(xhr.responseText);
          toast.error(extractErrorMessage(error.detail, "Erro ao carregar ficheiros"));
        }
        setUploading(false);
      });

      xhr.addEventListener("error", () => {
        toast.error("Erro ao carregar ficheiros");
        setUploading(false);
      });

      xhr.open("POST", `${API_URL}/api/temp-links/public/${token}/upload`);
      xhr.send(formData);
    } catch (err) {
      toast.error("Erro ao carregar ficheiros");
      setUploading(false);
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-teal-50 to-blue-50 flex items-center justify-center p-4">
        <div className="text-center">
          <Loader2 className="h-12 w-12 animate-spin text-teal-600 mx-auto mb-4" />
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

  // Success state (after upload)
  if (uploadedFiles.length > 0) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-green-50 to-teal-50 flex items-center justify-center p-4">
        <Card className="max-w-lg w-full">
          <CardContent className="pt-6 text-center">
            <CheckCircle className="h-16 w-16 text-green-500 mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-gray-900 mb-2">
              Documentos Enviados com Sucesso!
            </h2>
            <p className="text-gray-600 mb-6">
              Obrigado, <strong>{linkInfo?.client_name}</strong>! Os seus documentos foram carregados.
            </p>

            <div className="bg-gray-50 rounded-lg p-4 mb-6 text-left">
              <p className="text-sm font-medium text-gray-700 mb-2">Ficheiros enviados:</p>
              <ul className="space-y-1">
                {uploadedFiles.map((file, index) => (
                  <li key={index} className="text-sm text-gray-600 flex items-center gap-2">
                    <CheckCircle className="h-4 w-4 text-green-500" />
                    {file.original_name}
                  </li>
                ))}
              </ul>
            </div>

            <p className="text-sm text-gray-500">
              O seu consultor irá entrar em contacto consigo em breve.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Upload form
  return (
    <div className="min-h-screen bg-gradient-to-br from-teal-50 to-blue-50 flex items-center justify-center p-4">
      <div className="max-w-2xl w-full space-y-6">
        {/* Header */}
        <div className="text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-teal-100 rounded-full mb-4">
            <Upload className="h-8 w-8 text-teal-600" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Carregar Documentação</h1>
          <p className="text-gray-600 mt-2">
            Olá, <strong>{linkInfo?.client_name}</strong>!
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
              <p className="mt-2 text-sm text-gray-700 bg-amber-50 p-3 rounded-lg">
                <strong>Notas:</strong> {linkInfo.description}
              </p>
            )}
          </CardContent>
        </Card>

        {/* Drop Zone */}
        <Card>
          <CardContent className="pt-6">
            <div
              className={`
                border-2 border-dashed rounded-xl p-8 text-center transition-colors cursor-pointer
                ${dragActive ? "border-teal-500 bg-teal-50" : "border-gray-300 hover:border-gray-400"}
              `}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <FilePlus className="h-12 w-12 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-600 mb-2">
                Arraste ficheiros aqui ou clique para selecionar
              </p>
              <p className="text-sm text-gray-500">
                PDF, JPG, PNG, TIFF, DOC, DOCX
              </p>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".pdf,.jpg,.jpeg,.png,.tiff,.tif,.doc,.docx"
                onChange={handleFileInput}
                className="hidden"
              />
            </div>

            {/* Selected Files */}
            {files.length > 0 && (
              <div className="mt-6 space-y-2">
                <h3 className="font-medium text-gray-700">
                  Ficheiros selecionados ({files.length})
                </h3>
                <div className="space-y-2 max-h-60 overflow-y-auto">
                  {files.map((file, index) => (
                    <div
                      key={index}
                      className="flex items-center justify-between bg-gray-50 rounded-lg p-3"
                    >
                      <div className="flex items-center gap-3">
                        {getFileIcon(file)}
                        <div>
                          <p className="text-sm font-medium text-gray-700">{file.name}</p>
                          <p className="text-xs text-gray-500">{formatFileSize(file.size)}</p>
                        </div>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeFile(index)}
                        className="text-red-500 hover:text-red-700 hover:bg-red-50"
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Progress Bar */}
            {uploading && (
              <div className="mt-6">
                <div className="flex items-center justify-between text-sm text-gray-600 mb-2">
                  <span>A enviar...</span>
                  <span>{uploadProgress}%</span>
                </div>
                <Progress value={uploadProgress} className="h-2" />
              </div>
            )}

            {/* Upload Button */}
            <Button
              onClick={handleUpload}
              disabled={files.length === 0 || uploading}
              className="w-full mt-6 bg-teal-600 hover:bg-teal-700"
              size="lg"
            >
              {uploading ? (
                <>
                  <Loader2 className="h-5 w-5 mr-2 animate-spin" />
                  A enviar...
                </>
              ) : (
                <>
                  <Upload className="h-5 w-5 mr-2" />
                  Enviar {files.length > 0 ? `(${files.length})` : ""}
                </>
              )}
            </Button>
          </CardContent>
        </Card>

        {/* Footer */}
        <p className="text-center text-sm text-gray-500">
          PowerCell - Sistema de Gestão de Processos
        </p>
      </div>
    </div>
  );
}
