/**
 * CompanyEmailConfigSection — SMTP por empresa.
 */
import { useState, useEffect } from "react";
import { useAuth } from "../../contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Badge } from "../../components/ui/badge";
import { Switch } from "../../components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../components/ui/select";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import { toast } from "sonner";
import {
  Building,
  Building2,
  Save,
  Loader2,
  Trash2,
  FileEdit,
  Info,
  Plus,
  ShieldCheck,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;


// ====================================================================
// Company Email Config Section
// ====================================================================
export default function CompanyEmailConfigSection() {
  const { token } = useAuth();
  const [configs, setConfigs] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editingCompany, setEditingCompany] = useState(null);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [selectedCompany, setSelectedCompany] = useState("");
  const [formData, setFormData] = useState({
    company_name: "",
    imap_server: "",
    imap_port: 993,
    smtp_server: "",
    smtp_port: 465,
    require_ssl: true,
  });
  const [deletingCompany, setDeletingCompany] = useState(null);

  const fetchConfigs = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/company-email-configs`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setConfigs(data.configs || []);
      }
    } catch (error) {
      console.error("Erro ao carregar configs:", error);
    } finally {
      setLoading(false);
    }
  };

  const fetchCompanies = async () => {
    try {
      const res = await fetch(`${API_URL}/api/admin/company-email-configs/available-companies`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setCompanies(data.companies || []);
      }
    } catch (error) {
      console.error("Erro ao carregar empresas:", error);
    }
  };

  useEffect(() => {
    fetchConfigs();
    fetchCompanies();
  }, []);

  const handleEdit = (config) => {
    setEditingCompany(config.company_name);
    setFormData({
      company_name: config.company_name,
      imap_server: config.imap_server || "",
      imap_port: config.imap_port || 993,
      smtp_server: config.smtp_server || "",
      smtp_port: config.smtp_port || 465,
      require_ssl: config.require_ssl !== false,
    });
  };

  const handleCreate = () => {
    if (!selectedCompany) {
      toast.error("Selecione uma empresa");
      return;
    }
    setFormData({
      company_name: selectedCompany,
      imap_server: "",
      imap_port: 993,
      smtp_server: "",
      smtp_port: 465,
      require_ssl: true,
    });
    setShowCreateDialog(true);
  };

  const handleSave = async () => {
    if (!formData.imap_server || !formData.smtp_server) {
      toast.error("Preencha os servidores IMAP e SMTP");
      return;
    }
    setSaving(true);
    try {
      const isUpdate = !!editingCompany;
      const method = isUpdate ? "PUT" : "POST";
      const url = isUpdate
        ? `${API_URL}/api/admin/company-email-configs/${encodeURIComponent(editingCompany)}`
        : `${API_URL}/api/admin/company-email-configs`;

      const res = await fetch(url, {
        method,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(formData),
      });

      if (res.ok) {
        toast.success(isUpdate ? "Configuração atualizada" : "Configuração criada");
        setEditingCompany(null);
        setShowCreateDialog(false);
        setSelectedCompany("");
        fetchConfigs();
        fetchCompanies();
      } else {
        const data = await res.json();
        toast.error(extractErrorMessage(data.detail, "Erro ao guardar"));
      }
    } catch (error) {
      toast.error("Erro de conexão");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (companyName) => {
    if (!window.confirm(`Remover a configuração de email para "${companyName}"?`)) return;
    setDeletingCompany(companyName);
    try {
      const res = await fetch(
        `${API_URL}/api/admin/company-email-configs/${encodeURIComponent(companyName)}`,
        {
          method: "DELETE",
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      if (res.ok) {
        toast.success("Configuração removida");
        fetchConfigs();
        fetchCompanies();
      } else {
        toast.error("Erro ao remover");
      }
    } catch (error) {
      toast.error("Erro de conexão");
    } finally {
      setDeletingCompany(null);
    }
  };

  const companiesWithoutConfig = companies.filter((c) => !c.has_email_config);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Building2 className="h-5 w-5 text-primary" />
            <div>
              <CardTitle className="text-lg">Configuração de Email por Empresa</CardTitle>
              <CardDescription>
                Defina servidores IMAP/SMTP padrão para cada empresa. Os utilizadores herdam estes servidores automaticamente.
              </CardDescription>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Info box about inheritance */}
        <div className="flex items-start gap-3 p-3 bg-blue-50 border border-blue-200 rounded-lg text-blue-800 text-sm">
          <Info className="h-4 w-4 mt-0.5 shrink-0" />
          <div>
            <p className="font-medium">Caminho da Herança</p>
            <ol className="list-decimal list-inside mt-1 space-y-0.5 text-blue-700">
              <li><strong>User Config</strong> — Configuração individual do utilizador</li>
              <li><strong>Company Config</strong> — Servidores padrão da empresa (esta secção)</li>
              <li><strong>System Config</strong> — Configuração global do sistema (fallback)</li>
            </ol>
            <p className="mt-2 text-blue-700 text-xs">
              A password e o email do utilizador são sempre individuais. Apenas os servidores (IMAP/SMTP) são herdados.
            </p>
          </div>
        </div>

        {/* Create new */}
        {companiesWithoutConfig.length > 0 && !showCreateDialog && (
          <div className="flex items-center gap-3">
            <Select value={selectedCompany} onValueChange={setSelectedCompany}>
              <SelectTrigger className="w-64">
                <SelectValue placeholder="Selecione uma empresa..." />
              </SelectTrigger>
              <SelectContent>
                {companiesWithoutConfig.map((c) => (
                  <SelectItem key={c.company_name} value={c.company_name}>
                    {c.company_name} ({c.total_users} utilizadores)
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button onClick={handleCreate} disabled={!selectedCompany} className="gap-2">
              <Plus className="h-4 w-4" />
              Adicionar Configuração
            </Button>
          </div>
        )}

        {/* Create/Edit Form */}
        {(showCreateDialog || editingCompany) && (
          <div className="border rounded-lg p-4 space-y-4 bg-muted/30">
            <div className="flex items-center justify-between">
              <h4 className="font-medium">
                {editingCompany ? `Editar: ${editingCompany}` : "Nova Configuração"}
              </h4>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => { setEditingCompany(null); setShowCreateDialog(false); }}>
                  Cancelar
                </Button>
                <Button size="sm" onClick={handleSave} disabled={saving} className="gap-2">
                  {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                  Guardar
                </Button>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Empresa</Label>
                <Input value={formData.company_name} disabled />
              </div>
              <div className="space-y-2" />
              <div className="space-y-2">
                <Label htmlFor="ce_imap_server">Servidor IMAP</Label>
                <Input
                  id="ce_imap_server"
                  value={formData.imap_server}
                  onChange={(e) => setFormData({ ...formData, imap_server: e.target.value })}
                  placeholder="imap.empresa.pt"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ce_imap_port">Porta IMAP</Label>
                <Input
                  id="ce_imap_port"
                  type="number"
                  value={formData.imap_port}
                  onChange={(e) => setFormData({ ...formData, imap_port: parseInt(e.target.value) || 993 })}
                  placeholder="993"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ce_smtp_server">Servidor SMTP</Label>
                <Input
                  id="ce_smtp_server"
                  value={formData.smtp_server}
                  onChange={(e) => setFormData({ ...formData, smtp_server: e.target.value })}
                  placeholder="smtp.empresa.pt"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ce_smtp_port">Porta SMTP</Label>
                <Input
                  id="ce_smtp_port"
                  type="number"
                  value={formData.smtp_port}
                  onChange={(e) => setFormData({ ...formData, smtp_port: parseInt(e.target.value) || 465 })}
                  placeholder="465"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ce_require_ssl">Requer SSL/TLS</Label>
                <div className="flex items-center gap-3 h-9">
                  <Switch
                    id="ce_require_ssl"
                    checked={formData.require_ssl}
                    onCheckedChange={(v) => setFormData({ ...formData, require_ssl: v })}
                  />
                  <span className="text-sm text-muted-foreground">
                    {formData.require_ssl ? "Ativado" : "Desativado"}
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Existing configs list */}
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : configs.length === 0 ? (
          <p className="text-center text-muted-foreground py-6">
            Nenhuma empresa com configuração de email definida.
          </p>
        ) : (
          <div className="space-y-3">
            {configs.map((cfg) => (
              <div key={cfg.id} className="border rounded-lg p-4 hover:bg-muted/30 transition-colors">
                <div className="flex items-start justify-between">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <Building className="h-4 w-4 text-muted-foreground" />
                      <span className="font-medium">{cfg.company_name}</span>
                      <Badge variant="secondary" className="text-xs">
                        {cfg.total_users} {cfg.total_users === 1 ? "utilizador" : "utilizadores"}
                      </Badge>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm text-muted-foreground">
                      <div>
                        <span className="text-xs uppercase tracking-wider">IMAP</span>
                        <p>{cfg.imap_server}:{cfg.imap_port}</p>
                      </div>
                      <div>
                        <span className="text-xs uppercase tracking-wider">SMTP</span>
                        <p>{cfg.smtp_server}:{cfg.smtp_port}</p>
                      </div>
                      <div>
                        <span className="text-xs uppercase tracking-wider">SSL/TLS</span>
                        <p className="flex items-center gap-1">
                          <ShieldCheck className={`h-3 w-3 ${cfg.require_ssl !== false ? "text-green-500" : "text-muted-foreground"}`} />
                          {cfg.require_ssl !== false ? "Ativado" : "Desativado"}
                        </p>
                      </div>
                      <div>
                        <span className="text-xs uppercase tracking-wider">Utilizadores</span>
                        <p>{cfg.total_users}</p>
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="icon" onClick={() => handleEdit(cfg)} title="Editar">
                      <FileEdit className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleDelete(cfg.company_name)}
                      disabled={deletingCompany === cfg.company_name}
                      className="text-destructive hover:text-destructive"
                      title="Eliminar"
                    >
                      {deletingCompany === cfg.company_name ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Companies without config summary */}
        {companiesWithoutConfig.length > 0 && (
          <div className="mt-4 pt-4 border-t">
            <p className="text-xs text-muted-foreground mb-2">
              Empresas sem configuração (utilizadores usarão System Config como fallback):
            </p>
            <div className="flex flex-wrap gap-2">
              {companiesWithoutConfig.map((c) => (
                <Badge key={c.company_name} variant="outline" className="text-xs">
                  {c.company_name} ({c.total_users})
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

