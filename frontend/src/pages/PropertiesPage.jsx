/**
 * PropertiesPage - Gestão de Imóveis Angariados
 * Lista, cria e edita imóveis listados pela agência
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Plus, Search, MapPin, Home, Ruler, User, Building2, MoreHorizontal, Trash2, Edit, Upload, FileSpreadsheet, Loader2, ExternalLink } from 'lucide-react';
import DashboardLayout from '../layouts/DashboardLayout';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '../components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '../components/ui/dropdown-menu';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { toast } from 'sonner';
import { hasAnyRole } from '../utils/roleUtils';

const API_URL = process.env.REACT_APP_BACKEND_URL;
const HCPRO_URL = "https://crmhcpro.pt/login";

const STATUS_CONFIG = {
  disponivel: { label: 'Disponível', color: 'bg-green-100 text-green-800' },
  reservado: { label: 'Reservado', color: 'bg-yellow-100 text-yellow-800' },
  vendido: { label: 'Vendido', color: 'bg-blue-100 text-blue-800' },
  suspenso: { label: 'Suspenso', color: 'bg-gray-100 text-gray-800' },
  em_analise: { label: 'Em Análise', color: 'bg-orange-100 text-orange-800' },
};

const PROPERTY_TYPES = {
  apartamento: 'Apartamento',
  moradia: 'Moradia',
  terreno: 'Terreno',
  loja: 'Loja',
  escritorio: 'Escritório',
  armazem: 'Armazém',
  garagem: 'Garagem',
  outro: 'Outro',
};

const CONDITIONS = {
  novo: 'Novo',
  como_novo: 'Como Novo',
  bom: 'Bom Estado',
  para_recuperar: 'Para Recuperar',
  em_construcao: 'Em Construção',
};

// Componente de card de imóvel
const PropertyCard = ({ property, onEdit, onDelete, onStatusChange }) => {
  const status = STATUS_CONFIG[property.status] || STATUS_CONFIG.em_analise;
  
  return (
    <Card className="hover:shadow-lg transition-shadow" data-testid={`property-card-${property.id}`}>
      <div className="relative h-40 bg-gray-200 rounded-t-lg overflow-hidden">
        {property.photo_url ? (
          <img 
            src={property.photo_url} 
            alt={property.title}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-gray-400">
            <Building2 size={48} />
          </div>
        )}
        <Badge className={`absolute top-2 right-2 ${status.color}`}>
          {status.label}
        </Badge>
        {property.internal_reference && (
          <Badge variant="outline" className="absolute top-2 left-2 bg-white">
            {property.internal_reference}
          </Badge>
        )}
      </div>
      
      <CardContent className="p-4">
        <div className="flex justify-between items-start mb-2">
          <h3 className="font-semibold text-lg line-clamp-1">{property.title}</h3>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" data-testid={`property-menu-${property.id}`}>
                <MoreHorizontal size={16} />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => onEdit(property)}>
                <Edit size={14} className="mr-2" /> Editar
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onStatusChange(property.id, 'disponivel')}>
                Marcar Disponível
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onStatusChange(property.id, 'reservado')}>
                Marcar Reservado
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onStatusChange(property.id, 'vendido')}>
                Marcar Vendido
              </DropdownMenuItem>
              <DropdownMenuItem 
                onClick={() => onDelete(property.id)}
                className="text-red-600"
              >
                <Trash2 size={14} className="mr-2" /> Eliminar
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        
        <div className="text-2xl font-bold text-primary mb-2">
          {property.asking_price?.toLocaleString('pt-PT')} €
        </div>
        
        <div className="flex items-center text-gray-600 text-sm mb-2">
          <MapPin size={14} className="mr-1" />
          <span>{property.municipality}, {property.district}</span>
        </div>
        
        <div className="flex gap-4 text-sm text-gray-600 mb-3">
          {property.bedrooms !== null && (
            <div className="flex items-center">
              <Home size={14} className="mr-1" />
              T{property.bedrooms}
            </div>
          )}
          {property.useful_area && (
            <div className="flex items-center">
              <Ruler size={14} className="mr-1" />
              {property.useful_area}m²
            </div>
          )}
        </div>
        
        {property.assigned_agent_name && (
          <div className="flex items-center text-xs text-gray-500 pt-2 border-t">
            <User size={12} className="mr-1" />
            {property.assigned_agent_name}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

// Formulário de criação/edição
const PropertyForm = ({ property, onSave, onCancel, users }) => {
  const [formData, setFormData] = useState({
    title: property?.title || '',
    property_type: property?.property_type || 'apartamento',
    condition: property?.condition || 'bom',
    status: property?.status || 'em_analise',
    description: property?.description || '',
    // Endereço
    district: property?.address?.district || '',
    municipality: property?.address?.municipality || '',
    locality: property?.address?.locality || '',
    street: property?.address?.street || '',
    postal_code: property?.address?.postal_code || '',
    // Características
    bedrooms: property?.features?.bedrooms || '',
    bathrooms: property?.features?.bathrooms || '',
    useful_area: property?.features?.useful_area || '',
    gross_area: property?.features?.gross_area || '',
    construction_year: property?.features?.construction_year || '',
    energy_certificate: property?.features?.energy_certificate || '',
    // Financeiro
    asking_price: property?.financials?.asking_price || '',
    minimum_price: property?.financials?.minimum_price || '',
    commission_percentage: property?.financials?.commission_percentage || '',
    condominium_fee: property?.financials?.condominium_fee || '',
    // Proprietário
    owner_name: property?.owner?.name || '',
    owner_phone: property?.owner?.phone || '',
    owner_email: property?.owner?.email || '',
    owner_nif: property?.owner?.nif || '',
    // Agente
    assigned_agent_id: property?.assigned_agent_id || '',
    // Notas
    notes: property?.notes || '',
    private_notes: property?.private_notes || '',
    // Fotos
    photos: property?.photos || [],
  });

  const [photoUrl, setPhotoUrl] = useState('');
  const [saving, setSaving] = useState(false);

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleAddPhoto = () => {
    if (photoUrl.trim()) {
      setFormData(prev => ({ ...prev, photos: [...prev.photos, photoUrl.trim()] }));
      setPhotoUrl('');
    }
  };

  const handleRemovePhoto = (index) => {
    setFormData(prev => ({
      ...prev,
      photos: prev.photos.filter((_, i) => i !== index)
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);

    try {
      // Validação básica
      if (!formData.title || !formData.district || !formData.municipality || !formData.asking_price || !formData.owner_name) {
        toast.error('Preencha os campos obrigatórios');
        setSaving(false);
        return;
      }

      const payload = {
        title: formData.title,
        property_type: formData.property_type,
        condition: formData.condition,
        status: formData.status,
        description: formData.description || null,
        address: {
          district: formData.district,
          municipality: formData.municipality,
          locality: formData.locality || null,
          street: formData.street || null,
          postal_code: formData.postal_code || null,
        },
        features: {
          bedrooms: formData.bedrooms ? parseInt(formData.bedrooms) : null,
          bathrooms: formData.bathrooms ? parseInt(formData.bathrooms) : null,
          useful_area: formData.useful_area ? parseFloat(formData.useful_area) : null,
          gross_area: formData.gross_area ? parseFloat(formData.gross_area) : null,
          construction_year: formData.construction_year ? parseInt(formData.construction_year) : null,
          energy_certificate: formData.energy_certificate || null,
        },
        financials: {
          asking_price: parseFloat(formData.asking_price),
          minimum_price: formData.minimum_price ? parseFloat(formData.minimum_price) : null,
          commission_percentage: formData.commission_percentage ? parseFloat(formData.commission_percentage) : null,
          condominium_fee: formData.condominium_fee ? parseFloat(formData.condominium_fee) : null,
        },
        owner: {
          name: formData.owner_name,
          phone: formData.owner_phone || null,
          email: formData.owner_email || null,
          nif: formData.owner_nif || null,
        },
        assigned_agent_id: formData.assigned_agent_id || null,
        notes: formData.notes || null,
        private_notes: formData.private_notes || null,
        photos: formData.photos,
      };

      await onSave(payload);
    } catch (error) {
      console.error('Erro ao guardar:', error);
      toast.error('Erro ao guardar imóvel');
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6 max-h-[70vh] overflow-y-auto pr-2">
      {/* Link para HCPro */}
      <div className="p-4 bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="font-semibold text-blue-800">Integração HCPro</h4>
            <p className="text-sm text-blue-600">Aceda ao CRM HCPro para consultar dados de imóveis</p>
          </div>
          <Button
            type="button"
            variant="outline"
            className="border-blue-300 text-blue-700 hover:bg-blue-100"
            onClick={() => window.open(HCPRO_URL, '_blank')}
            data-testid="hcpro-login-btn"
          >
            <ExternalLink size={16} className="mr-2" />
            Abrir HCPro
          </Button>
        </div>
      </div>

      {/* Informações Básicas */}
      <div className="space-y-4">
        <h4 className="font-semibold text-sm text-gray-700 border-b pb-2">Informações Básicas</h4>
        
        <div>
          <Label>Título do Anúncio *</Label>
          <Input
            value={formData.title}
            onChange={(e) => handleChange('title', e.target.value)}
            placeholder="Ex: Apartamento T2 com Vista Mar"
            required
            data-testid="property-title-input"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label>Tipo de Imóvel</Label>
            <Select value={formData.property_type} onValueChange={(v) => handleChange('property_type', v)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {Object.entries(PROPERTY_TYPES).map(([key, label]) => (
                  <SelectItem key={key} value={key}>{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Estado</Label>
            <Select value={formData.condition} onValueChange={(v) => handleChange('condition', v)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {Object.entries(CONDITIONS).map(([key, label]) => (
                  <SelectItem key={key} value={key}>{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div>
          <Label>Descrição</Label>
          <Textarea
            value={formData.description}
            onChange={(e) => handleChange('description', e.target.value)}
            placeholder="Descrição detalhada do imóvel..."
            rows={3}
          />
        </div>
      </div>

      {/* Localização */}
      <div className="space-y-4">
        <h4 className="font-semibold text-sm text-gray-700 border-b pb-2">Localização</h4>
        
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label>Distrito *</Label>
            <Input
              value={formData.district}
              onChange={(e) => handleChange('district', e.target.value)}
              placeholder="Lisboa"
              required
            />
          </div>
          <div>
            <Label>Concelho *</Label>
            <Input
              value={formData.municipality}
              onChange={(e) => handleChange('municipality', e.target.value)}
              placeholder="Cascais"
              required
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label>Localidade/Freguesia</Label>
            <Input
              value={formData.locality}
              onChange={(e) => handleChange('locality', e.target.value)}
              placeholder="Estoril"
            />
          </div>
          <div>
            <Label>Código Postal</Label>
            <Input
              value={formData.postal_code}
              onChange={(e) => handleChange('postal_code', e.target.value)}
              placeholder="2765-000"
            />
          </div>
        </div>

        <div>
          <Label>Morada</Label>
          <Input
            value={formData.street}
            onChange={(e) => handleChange('street', e.target.value)}
            placeholder="Rua das Flores, 123"
          />
        </div>
      </div>

      {/* Características */}
      <div className="space-y-4">
        <h4 className="font-semibold text-sm text-gray-700 border-b pb-2">Características</h4>
        
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          <div>
            <Label>Quartos (T)</Label>
            <Input
              type="number"
              value={formData.bedrooms}
              onChange={(e) => handleChange('bedrooms', e.target.value)}
              placeholder="2"
              min="0"
            />
          </div>
          <div>
            <Label>Casas de Banho</Label>
            <Input
              type="number"
              value={formData.bathrooms}
              onChange={(e) => handleChange('bathrooms', e.target.value)}
              placeholder="1"
              min="0"
            />
          </div>
          <div>
            <Label>Área Útil (m²)</Label>
            <Input
              type="number"
              value={formData.useful_area}
              onChange={(e) => handleChange('useful_area', e.target.value)}
              placeholder="85"
              min="0"
            />
          </div>
          <div>
            <Label>Área Bruta (m²)</Label>
            <Input
              type="number"
              value={formData.gross_area}
              onChange={(e) => handleChange('gross_area', e.target.value)}
              placeholder="100"
              min="0"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label>Ano Construção</Label>
            <Input
              type="number"
              value={formData.construction_year}
              onChange={(e) => handleChange('construction_year', e.target.value)}
              placeholder="2020"
              min="1900"
              max="2030"
            />
          </div>
          <div>
            <Label>Certificado Energético</Label>
            <Select value={formData.energy_certificate || 'none'} onValueChange={(v) => handleChange('energy_certificate', v === 'none' ? '' : v)}>
              <SelectTrigger><SelectValue placeholder="Seleccionar" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Não especificado</SelectItem>
                {['A+', 'A', 'B', 'B-', 'C', 'D', 'E', 'F'].map(c => (
                  <SelectItem key={c} value={c}>{c}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      {/* Financeiro */}
      <div className="space-y-4">
        <h4 className="font-semibold text-sm text-gray-700 border-b pb-2">Valores</h4>
        
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label>Preço Pedido (€) *</Label>
            <Input
              type="number"
              value={formData.asking_price}
              onChange={(e) => handleChange('asking_price', e.target.value)}
              placeholder="350000"
              required
              min="0"
              data-testid="property-price-input"
            />
          </div>
          <div>
            <Label>Preço Mínimo (€)</Label>
            <Input
              type="number"
              value={formData.minimum_price}
              onChange={(e) => handleChange('minimum_price', e.target.value)}
              placeholder="320000"
              min="0"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label>Comissão (%)</Label>
            <Input
              type="number"
              value={formData.commission_percentage}
              onChange={(e) => handleChange('commission_percentage', e.target.value)}
              placeholder="5"
              min="0"
              max="100"
              step="0.5"
            />
          </div>
          <div>
            <Label>Condomínio Mensal (€)</Label>
            <Input
              type="number"
              value={formData.condominium_fee}
              onChange={(e) => handleChange('condominium_fee', e.target.value)}
              placeholder="50"
              min="0"
            />
          </div>
        </div>
      </div>

      {/* Proprietário */}
      <div className="space-y-4">
        <h4 className="font-semibold text-sm text-gray-700 border-b pb-2">Proprietário</h4>
        
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label>Nome *</Label>
            <Input
              value={formData.owner_name}
              onChange={(e) => handleChange('owner_name', e.target.value)}
              placeholder="Nome do proprietário"
              required
            />
          </div>
          <div>
            <Label>Telefone</Label>
            <Input
              value={formData.owner_phone}
              onChange={(e) => handleChange('owner_phone', e.target.value)}
              placeholder="+351 912 345 678"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label>Email</Label>
            <Input
              type="email"
              value={formData.owner_email}
              onChange={(e) => handleChange('owner_email', e.target.value)}
              placeholder="email@exemplo.pt"
            />
          </div>
          <div>
            <Label>NIF</Label>
            <Input
              value={formData.owner_nif}
              onChange={(e) => handleChange('owner_nif', e.target.value)}
              placeholder="123456789"
            />
          </div>
        </div>
      </div>

      {/* Agente e Status */}
      <div className="space-y-4">
        <h4 className="font-semibold text-sm text-gray-700 border-b pb-2">Gestão</h4>
        
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label>Consultor Responsável</Label>
            <Select value={formData.assigned_agent_id || 'none'} onValueChange={(v) => handleChange('assigned_agent_id', v === 'none' ? '' : v)}>
              <SelectTrigger><SelectValue placeholder="Seleccionar" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Não atribuído</SelectItem>
                {users.map(u => (
                  <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Estado do Imóvel</Label>
            <Select value={formData.status} onValueChange={(v) => handleChange('status', v)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {Object.entries(STATUS_CONFIG).map(([key, config]) => (
                  <SelectItem key={key} value={key}>{config.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      {/* Fotos */}
      <div className="space-y-4">
        <h4 className="font-semibold text-sm text-gray-700 border-b pb-2">Fotos</h4>
        
        <div className="flex gap-2">
          <Input
            value={photoUrl}
            onChange={(e) => setPhotoUrl(e.target.value)}
            placeholder="URL da foto"
            className="flex-1"
          />
          <Button type="button" variant="outline" onClick={handleAddPhoto}>
            Adicionar
          </Button>
        </div>

        {formData.photos.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {formData.photos.map((url, i) => (
              <div key={i} className="relative">
                <img src={url} alt={`Foto ${i + 1}`} className="w-20 h-20 object-cover rounded" />
                <button
                  type="button"
                  onClick={() => handleRemovePhoto(i)}
                  className="absolute -top-1 -right-1 bg-red-500 text-white rounded-full w-5 h-5 text-xs"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Notas */}
      <div className="space-y-4">
        <h4 className="font-semibold text-sm text-gray-700 border-b pb-2">Notas</h4>
        
        <div>
          <Label>Notas Públicas</Label>
          <Textarea
            value={formData.notes}
            onChange={(e) => handleChange('notes', e.target.value)}
            placeholder="Notas visíveis ao cliente..."
            rows={2}
          />
        </div>

        <div>
          <Label>Notas Internas</Label>
          <Textarea
            value={formData.private_notes}
            onChange={(e) => handleChange('private_notes', e.target.value)}
            placeholder="Notas internas (não visíveis ao cliente)..."
            rows={2}
          />
        </div>
      </div>

      {/* Botões */}
      <div className="flex justify-end gap-3 pt-4 border-t">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="submit" disabled={saving} data-testid="property-save-btn">
          {saving ? 'A guardar...' : (property ? 'Actualizar' : 'Criar Imóvel')}
        </Button>
      </div>
    </form>
  );
};

// Página principal
const PropertiesPage = () => {
  const [properties, setProperties] = useState([]);
  const [users, setUsers] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingProperty, setEditingProperty] = useState(null);
  
  // Estado para importação Excel
  const [importing, setImporting] = useState(false);
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [importResults, setImportResults] = useState(null);
  const fileInputRef = useRef(null);

  const getAuthHeaders = () => {
    const token = localStorage.getItem('token');
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    };
  };

  const fetchProperties = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (searchTerm) params.append('search', searchTerm);
      if (statusFilter !== 'all') params.append('status', statusFilter);
      if (typeFilter !== 'all') params.append('property_type', typeFilter);

      const response = await fetch(`${API_URL}/api/properties?${params}`, {
        headers: getAuthHeaders(),
      });
      
      if (response.ok) {
        const data = await response.json();
        setProperties(data);
      }
    } catch (error) {
      console.error('Erro ao carregar imóveis:', error);
      toast.error('Erro ao carregar imóveis');
    }
  }, [searchTerm, statusFilter, typeFilter]);

  const fetchStats = async () => {
    try {
      const response = await fetch(`${API_URL}/api/properties/stats`, {
        headers: getAuthHeaders(),
      });
      if (response.ok) {
        const data = await response.json();
        setStats(data);
      }
    } catch (error) {
      console.error('Erro ao carregar estatísticas:', error);
    }
  };

  const fetchUsers = async () => {
    try {
      const response = await fetch(`${API_URL}/api/users`, {
        headers: getAuthHeaders(),
      });
      if (response.ok) {
        const data = await response.json();
        setUsers(data.filter(u => hasAnyRole(u, ['CONSULTOR', 'ADMIN', 'CEO'])));
      }
    } catch (error) {
      console.error('Erro ao carregar utilizadores:', error);
    }
  };

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([fetchProperties(), fetchStats(), fetchUsers()]);
      setLoading(false);
    };
    loadData();
  }, [fetchProperties]);

  const handleSaveProperty = async (payload) => {
    try {
      const url = editingProperty 
        ? `${API_URL}/api/properties/${editingProperty.id}`
        : `${API_URL}/api/properties`;
      
      const method = editingProperty ? 'PATCH' : 'POST';

      const response = await fetch(url, {
        method,
        headers: getAuthHeaders(),
        body: JSON.stringify(payload),
      });

      if (response.ok) {
        toast.success(editingProperty ? 'Imóvel actualizado!' : 'Imóvel criado!');
        setDialogOpen(false);
        setEditingProperty(null);
        fetchProperties();
        fetchStats();
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Erro ao guardar');
      }
    } catch (error) {
      console.error('Erro:', error);
      toast.error('Erro ao guardar imóvel');
    }
  };

  const handleDeleteProperty = async (propertyId) => {
    if (!window.confirm('Tem certeza que deseja eliminar este imóvel?')) return;

    try {
      const response = await fetch(`${API_URL}/api/properties/${propertyId}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      });

      if (response.ok) {
        toast.success('Imóvel eliminado');
        fetchProperties();
        fetchStats();
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Erro ao eliminar');
      }
    } catch (error) {
      toast.error('Erro ao eliminar imóvel');
    }
  };

  const handleStatusChange = async (propertyId, newStatus) => {
    try {
      const response = await fetch(`${API_URL}/api/properties/${propertyId}/status?status=${newStatus}`, {
        method: 'PATCH',
        headers: getAuthHeaders(),
      });

      if (response.ok) {
        toast.success('Estado actualizado');
        fetchProperties();
        fetchStats();
      }
    } catch (error) {
      toast.error('Erro ao actualizar estado');
    }
  };

  const handleEditProperty = (property) => {
    setEditingProperty(property);
    setDialogOpen(true);
  };

  // Função para importar ficheiro Excel (com processamento em background)
  const handleImportExcel = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    
    if (!file.name.endsWith('.xlsx') && !file.name.endsWith('.xls')) {
      toast.error('Por favor, selecione um ficheiro Excel (.xlsx ou .xls)');
      return;
    }
    
    setImporting(true);
    setImportResults(null);
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/properties/bulk/import-excel`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
        body: formData,
      });
      
      const data = await response.json();
      
      if (response.ok && data.job_id) {
        // Importação iniciada em background - mostrar progresso
        toast.info(`Importação iniciada: ${data.total_rows} linhas a processar`);
        
        // Polling para verificar progresso
        const pollProgress = async () => {
          try {
            const progressResponse = await fetch(`${API_URL}/api/properties/bulk/job/${data.job_id}`, {
              headers: { 'Authorization': `Bearer ${token}` },
            });
            const job = await progressResponse.json();
            
            if (job.status === 'processing') {
              const progress = job.progress || {};
              toast.info(`A importar... ${progress.percentage || 0}% (${progress.current || 0}/${progress.total || 0})`, { id: 'import-progress' });
              setTimeout(pollProgress, 2000);
            } else if (job.status === 'completed') {
              setImportResults(job.result);
              setImportDialogOpen(true);
              
              const result = job.result;
              if (result.importados > 0) {
                toast.success(`${result.importados} imóveis importados com sucesso!`, { id: 'import-progress' });
                fetchProperties();
                fetchStats();
              }
              
              if (result.erros?.length > 0) {
                toast.warning(`${result.erros.length} linhas com erros`);
              }
              setImporting(false);
            } else if (job.status === 'failed') {
              toast.error(`Erro na importação: ${job.error}`, { id: 'import-progress' });
              setImporting(false);
            }
          } catch (error) {
            console.error('Erro ao verificar progresso:', error);
            setTimeout(pollProgress, 3000);
          }
        };
        
        pollProgress();
      } else {
        toast.error(data.detail || 'Erro na importação');
        setImporting(false);
      }
    } catch (error) {
      console.error('Erro na importação:', error);
      toast.error('Erro ao importar ficheiro');
      setImporting(false);
    } finally {
      // Limpar input para permitir reimportar o mesmo ficheiro
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  return (
    <DashboardLayout title="Imóveis Angariados">
      <div data-testid="properties-page">
        {/* Header com Stats */}
        <div className="mb-6">
          <div className="flex justify-between items-center mb-4">
            <div>
              <p className="text-gray-600">Gestão de imóveis listados pela agência</p>
            </div>
            
            <div className="flex gap-2">
              {/* Botão Importar Excel */}
              <div className="relative">
                <input
                  type="file"
                  accept=".xlsx,.xls"
                  onChange={handleImportExcel}
                  ref={fileInputRef}
                  className="hidden"
                  id="excel-import"
                  data-testid="excel-import-input"
                />
                <Button
                  variant="outline"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={importing}
                  data-testid="import-excel-btn"
                >
                  {importing ? (
                    <>
                      <Loader2 size={18} className="mr-2 animate-spin" />
                      A importar...
                    </>
                  ) : (
                    <>
                      <FileSpreadsheet size={18} className="mr-2" />
                      Importar Excel
                    </>
                  )}
                </Button>
              </div>
              
              <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                <DialogTrigger asChild>
                  <Button onClick={() => setEditingProperty(null)} data-testid="new-property-btn">
                    <Plus size={18} className="mr-2" /> Novo Imóvel
                  </Button>
                </DialogTrigger>
                <DialogContent className="max-w-2xl">
                  <DialogHeader>
                    <DialogTitle>
                      {editingProperty ? 'Editar Imóvel' : 'Novo Imóvel'}
                    </DialogTitle>
                    <DialogDescription className="sr-only">
                      Formulário para {editingProperty ? 'editar' : 'criar'} imóvel.
                    </DialogDescription>
                  </DialogHeader>
                  <PropertyForm
                    property={editingProperty}
                    onSave={handleSaveProperty}
                    onCancel={() => setDialogOpen(false)}
                    users={users}
                  />
                </DialogContent>
              </Dialog>
            </div>
          </div>

          {/* Stats Cards */}
          {stats && (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mb-6">
              <Card>
                <CardContent className="pt-4">
                  <div className="text-2xl font-bold">{stats.total}</div>
                  <div className="text-sm text-gray-600">Total de Imóveis</div>
                </CardContent>
              </Card>
              <Card className="border-l-4 border-l-green-500">
                <CardContent className="pt-4">
                  <div className="text-2xl font-bold text-green-600">{stats.disponivel?.count || 0}</div>
                  <div className="text-sm text-gray-600">Disponíveis</div>
                </CardContent>
              </Card>
              <Card className="border-l-4 border-l-yellow-500">
                <CardContent className="pt-4">
                  <div className="text-2xl font-bold text-yellow-600">{stats.reservado?.count || 0}</div>
                  <div className="text-sm text-gray-600">Reservados</div>
                </CardContent>
              </Card>
              <Card className="border-l-4 border-l-blue-500">
                <CardContent className="pt-4">
                  <div className="text-2xl font-bold text-blue-600">{stats.vendido?.count || 0}</div>
                  <div className="text-sm text-gray-600">Vendidos</div>
                </CardContent>
              </Card>
            </div>
          )}
        </div>

        {/* Filters */}
        <div className="flex gap-4 mb-6">
          <div className="flex-1">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
              <Input
                placeholder="Pesquisar por título, referência ou localização..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
                data-testid="property-search-input"
              />
            </div>
          </div>
          
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-40">
              <SelectValue placeholder="Estado" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos os estados</SelectItem>
              {Object.entries(STATUS_CONFIG).map(([key, config]) => (
                <SelectItem key={key} value={key}>{config.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={typeFilter} onValueChange={setTypeFilter}>
            <SelectTrigger className="w-40">
              <SelectValue placeholder="Tipo" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos os tipos</SelectItem>
              {Object.entries(PROPERTY_TYPES).map(([key, label]) => (
                <SelectItem key={key} value={key}>{label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Properties Grid */}
        {loading ? (
          <div className="flex justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          </div>
        ) : properties.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <Building2 size={48} className="mx-auto mb-4 opacity-50" />
            <p>Nenhum imóvel encontrado</p>
            <p className="text-sm">Clique em "Novo Imóvel" para adicionar</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {properties.map(property => (
              <PropertyCard
                key={property.id}
                property={property}
                onEdit={handleEditProperty}
                onDelete={handleDeleteProperty}
                onStatusChange={handleStatusChange}
              />
            ))}
          </div>
        )}
        
        {/* Dialog de Resultados de Importação */}
        <Dialog open={importDialogOpen} onOpenChange={setImportDialogOpen}>
          <DialogContent className="max-w-lg">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <FileSpreadsheet size={20} />
                Resultado da Importação
              </DialogTitle>
              <DialogDescription className="sr-only">
                Detalhes do resultado da importação de imóveis.
              </DialogDescription>
            </DialogHeader>
            
            {importResults && (
              <div className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 text-center">
                  <div className="p-3 bg-gray-50 rounded-lg">
                    <div className="text-2xl font-bold">{importResults.total}</div>
                    <div className="text-sm text-gray-600">Total linhas</div>
                  </div>
                  <div className="p-3 bg-green-50 rounded-lg">
                    <div className="text-2xl font-bold text-green-600">{importResults.importados}</div>
                    <div className="text-sm text-gray-600">Importados</div>
                  </div>
                  <div className="p-3 bg-red-50 rounded-lg">
                    <div className="text-2xl font-bold text-red-600">{importResults.erros?.length || 0}</div>
                    <div className="text-sm text-gray-600">Erros</div>
                  </div>
                </div>
                
                {importResults.erros?.length > 0 && (
                  <div className="mt-4">
                    <h4 className="font-semibold text-sm mb-2">Erros encontrados:</h4>
                    <div className="max-h-48 overflow-y-auto space-y-1 text-sm">
                      {importResults.erros.map((err, idx) => (
                        <div key={idx} className="p-2 bg-red-50 rounded text-red-700">
                          <span className="font-medium">Linha {err.linha}:</span> {err.erro}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                
                <div className="text-sm text-gray-500 mt-4 p-3 bg-gray-50 rounded-lg">
                  <p className="font-medium mb-1">Formato do ficheiro Excel:</p>
                  <p>Colunas obrigatórias: titulo, preco, distrito, concelho, proprietario_nome</p>
                  <p className="text-xs mt-1">Outras colunas opcionais: tipo, localidade, quartos, area_util, etc.</p>
                </div>
              </div>
            )}
            
            <div className="flex justify-end mt-4">
              <Button onClick={() => setImportDialogOpen(false)}>
                Fechar
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </DashboardLayout>
  );
};

export default PropertiesPage;
