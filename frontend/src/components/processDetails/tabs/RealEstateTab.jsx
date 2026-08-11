/**
 * RealEstateTab — extraído de ProcessDetails.js (tab realestate).
 * Mantém o JSX original; estado e permissões vêm por props.
 */
import { Card, CardContent } from "../../ui/card";
import { Input } from "../../ui/input";
import { Label } from "../../ui/label";
import { Textarea } from "../../ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../ui/select";
import { AIBadge } from "../../ui/AIBadge";
// PACOTE DH — Badge necessário para a lista de características (localização)
import { Badge } from "../../ui/badge";
import { Building2, Search, MapPin, FileSignature, Users } from "lucide-react";

export default function RealEstateTab({
  financialData, setFinancialData, realEstateData, setRealEstateData, editingCardId, canEditRealEstate, CardHeaderWithEdit, getFieldMetaFor, shouldCardBeCollapsed,
}) {
  return (
    <>
                    {!canEditRealEstate && !realEstateData?.tipo_imovel && !realEstateData?.property_type && !realEstateData?.num_quartos ? (
                      <div className="text-center py-8 text-muted-foreground">
                        <Building2 className="h-12 w-12 mx-auto mb-4 opacity-50" />
                        <p>Dados imobiliários serão preenchidos pelo consultor</p>
                      </div>
                    ) : (
                      <div className="space-y-4">

                        {/* ====== Grupo D: Estado da Procura ====== */}
                        <Card className={`border-l-4 border-l-indigo-500 ${editingCardId !== 'realestate_procura' ? 'read-only-card' : ''}`}>
                          <CardContent className="pt-4">
                            <CardHeaderWithEdit title="Estado da Procura" cardKey="realestate_procura" icon={Search} canEdit={canEditRealEstate} collapsible />
                            {!shouldCardBeCollapsed('realestate_procura') && (
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                              <div className="space-y-1 flex items-center gap-3 pb-1">
                                <input
                                  type="checkbox"
                                  id="ja_tem_imovel"
                                  checked={realEstateData.ja_tem_imovel || realEstateData.has_property || false}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, ja_tem_imovel: e.target.checked, has_property: e.target.checked })}
                                  disabled={editingCardId !== 'realestate_procura' || !canEditRealEstate}
                                  className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                                />
                                <Label htmlFor="ja_tem_imovel" className="text-xs text-muted-foreground cursor-pointer whitespace-nowrap">
                                  Já tem imóvel identificado
                                </Label>
                              </div>
                              <div className="space-y-1 flex items-center gap-3 pb-1">
                                <input
                                  type="checkbox"
                                  id="ja_tem_casa_escolhida"
                                  checked={realEstateData.ja_tem_casa_escolhida || false}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, ja_tem_casa_escolhida: e.target.checked })}
                                  disabled={editingCardId !== 'realestate_procura' || !canEditRealEstate}
                                  className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                                />
                                <Label htmlFor="ja_tem_casa_escolhida" className="text-xs text-muted-foreground cursor-pointer whitespace-nowrap">
                                  Já tem casa escolhida
                                </Label>
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Nome do Proprietário (vendedor)</Label>
                                <Input
                                  value={realEstateData.proprietario_nome || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, proprietario_nome: e.target.value })}
                                  disabled={editingCardId !== 'realestate_procura' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="Nome do proprietário do imóvel"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Contacto do Proprietário</Label>
                                <Input
                                  value={realEstateData.proprietario_contacto || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, proprietario_contacto: e.target.value })}
                                  disabled={editingCardId !== 'realestate_procura' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="+351 000 000 000"
                                />
                              </div>
                            </div>
                            )}
                          </CardContent>
                        </Card>

                        {/* ====== Grupo A: Características do Imóvel ====== */}
                        {/* PACOTE DH — tornou-se colapsável (progressive disclosure) */}
                        <Card className={`border-l-4 border-l-green-500 ${editingCardId !== 'realestate_caracteristicas' ? 'read-only-card' : ''}`}>
                          <CardContent className="pt-4">
                            <CardHeaderWithEdit title="Características do Imóvel" cardKey="realestate_caracteristicas" icon={Building2} canEdit={canEditRealEstate} collapsible />
                            {!shouldCardBeCollapsed('realestate_caracteristicas') && (
                            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Tipo de Imóvel</Label>
                                <Select
                                  value={realEstateData.tipo_imovel || ""}
                                  onValueChange={(value) => setRealEstateData({ ...realEstateData, tipo_imovel: value })}
                                  disabled={editingCardId !== 'realestate_caracteristicas' || !canEditRealEstate}
                                >
                                  <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                  <SelectContent>
                                    <SelectItem value="apartamento">Apartamento</SelectItem>
                                    <SelectItem value="moradia">Moradia</SelectItem>
                                    <SelectItem value="terreno">Terreno</SelectItem>
                                    <SelectItem value="outro">Outro</SelectItem>
                                    <SelectItem value="comercial">Espaço Comercial</SelectItem>
                                  </SelectContent>
                                </Select>
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Tipologia (Quartos)</Label>
                                <Select
                                  value={realEstateData.num_quartos || ""}
                                  onValueChange={(value) => setRealEstateData({ ...realEstateData, num_quartos: value })}
                                  disabled={editingCardId !== 'realestate_caracteristicas' || !canEditRealEstate}
                                >
                                  <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                  <SelectContent>
                                    <SelectItem value="T0">T0</SelectItem>
                                    <SelectItem value="T1">T1</SelectItem>
                                    <SelectItem value="T2">T2</SelectItem>
                                    <SelectItem value="T3">T3</SelectItem>
                                    <SelectItem value="T4">T4+</SelectItem>
                                  </SelectContent>
                                </Select>
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Tipologia</Label>
                                <Input
                                  value={realEstateData.tipologia || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, tipologia: e.target.value })}
                                  disabled={editingCardId !== 'realestate_caracteristicas' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="Ex: T2, T3, T4"
                                />
                              </div>
                              <div className="space-y-1">
                                <div className="flex items-center gap-1">
                                  <Label className="text-xs text-muted-foreground">Valor do Imóvel (€)</Label>
                                  <AIBadge {...(getFieldMetaFor("real_estate_data.valor_imovel") || {})} />
                                </div>
                                <Input
                                  type="number"
                                  value={realEstateData.valor_imovel || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, valor_imovel: parseFloat(e.target.value) || null })}
                                  disabled={editingCardId !== 'realestate_caracteristicas' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="0.00"
                                />
                              </div>
                              <div className="space-y-1">
                                <div className="flex items-center gap-1">
                                  <Label className="text-xs text-muted-foreground">Valor Patrimonial (€)</Label>
                                  <AIBadge {...(getFieldMetaFor("real_estate_data.valor_patrimonial") || {})} />
                                </div>
                                <Input
                                  type="number"
                                  value={realEstateData.valor_patrimonial || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, valor_patrimonial: parseFloat(e.target.value) || null })}
                                  disabled={editingCardId !== 'realestate_caracteristicas' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="0.00"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Certificado Energético</Label>
                                <Input
                                  value={realEstateData.certificado_energetico || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, certificado_energetico: e.target.value })}
                                  disabled={editingCardId !== 'realestate_caracteristicas' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="Ex: A, B-, C"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Área Bruta (m²)</Label>
                                <Input
                                  type="number"
                                  value={realEstateData.area_bruta || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, area_bruta: e.target.value })}
                                  disabled={editingCardId !== 'realestate_caracteristicas' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="0"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Área Útil (m²)</Label>
                                <Input
                                  type="number"
                                  value={realEstateData.area_util || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, area_util: e.target.value })}
                                  disabled={editingCardId !== 'realestate_caracteristicas' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="0"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Fração</Label>
                                <Input
                                  value={realEstateData.fracao || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, fracao: e.target.value })}
                                  disabled={editingCardId !== 'realestate_caracteristicas' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="Ex: A, B, C"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Artigo Matricial</Label>
                                <Input
                                  value={realEstateData.artigo_matricial || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, artigo_matricial: e.target.value })}
                                  disabled={editingCardId !== 'realestate_caracteristicas' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="Ex: 1234"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Conservatória</Label>
                                <Input
                                  value={realEstateData.conservatoria || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, conservatoria: e.target.value })}
                                  disabled={editingCardId !== 'realestate_caracteristicas' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="Nome da conservatória"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Número Predial</Label>
                                <Input
                                  value={realEstateData.numero_predial || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, numero_predial: e.target.value })}
                                  disabled={editingCardId !== 'realestate_caracteristicas' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="Ex: 000"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Estacionamento</Label>
                                <Input
                                  value={realEstateData.estacionamento || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, estacionamento: e.target.value })}
                                  disabled={editingCardId !== 'realestate_caracteristicas' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="Ex: Garagem dupla, Lugar 12"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Arrecadação</Label>
                                <Input
                                  value={realEstateData.arrecadacao || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, arrecadacao: e.target.value })}
                                  disabled={editingCardId !== 'realestate_caracteristicas' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="Ex: Arrecadação A, Caixa 5"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Outras Características</Label>
                                <Input
                                  value={realEstateData.outras_caracteristicas || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, outras_caracteristicas: e.target.value })}
                                  disabled={editingCardId !== 'realestate_caracteristicas' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="Ex: Varanda, Piscina, Solar"
                                />
                              </div>
                              <div className="space-y-1 sm:col-span-2 md:col-span-3">
                                <Label className="text-xs text-muted-foreground">Descrição do Imóvel</Label>
                                <Textarea
                                  value={realEstateData.descricao_imovel || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, descricao_imovel: e.target.value })}
                                  disabled={editingCardId !== 'realestate_caracteristicas' || !canEditRealEstate}
                                  rows={2}
                                  placeholder="Descrição detalhada do imóvel"
                                />
                              </div>
                            </div>
                            )}
                          </CardContent>
                        </Card>

                        {/* ====== Grupo B: Localização ====== */}
                        {/* PACOTE DH — tornou-se colapsável (progressive disclosure) */}
                        <Card className={`border-l-4 border-l-blue-500 ${editingCardId !== 'realestate_localizacao' ? 'read-only-card' : ''}`}>
                          <CardContent className="pt-4">
                            <CardHeaderWithEdit title="Localização" cardKey="realestate_localizacao" icon={MapPin} canEdit={canEditRealEstate} collapsible />
                            {!shouldCardBeCollapsed('realestate_localizacao') && (
                            <>
                            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Localização Pretendida</Label>
                                <Input
                                  value={realEstateData.localizacao || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, localizacao: e.target.value })}
                                  disabled={editingCardId !== 'realestate_localizacao' || !canEditRealEstate}
                                  className="h-9"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Área Pretendida (m²)</Label>
                                <Input
                                  type="number"
                                  value={realEstateData.area_pretendida || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, area_pretendida: parseFloat(e.target.value) || null })}
                                  disabled={editingCardId !== 'realestate_localizacao' || !canEditRealEstate}
                                  className="h-9"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Valor Máximo (€)</Label>
                                <Input
                                  type="number"
                                  value={realEstateData.valor_maximo_imovel || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, valor_maximo_imovel: parseFloat(e.target.value) || null })}
                                  disabled={editingCardId !== 'realestate_localizacao' || !canEditRealEstate}
                                  className="h-9"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Finalidade</Label>
                                <Select
                                  value={realEstateData.finalidade || ""}
                                  onValueChange={(value) => setRealEstateData({ ...realEstateData, finalidade: value })}
                                  disabled={editingCardId !== 'realestate_localizacao' || !canEditRealEstate}
                                >
                                  <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                  <SelectContent>
                                    <SelectItem value="compra_imovel">Compra de Imóvel</SelectItem>
                                    <SelectItem value="habitacao_propria">Habitação Própria</SelectItem>
                                    <SelectItem value="investimento">Investimento</SelectItem>
                                    <SelectItem value="arrendamento">Arrendamento</SelectItem>
                                    <SelectItem value="refinanciamento">Refinanciamento</SelectItem>
                                  </SelectContent>
                                </Select>
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Código Postal</Label>
                                <Input
                                  value={realEstateData.codigo_postal || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, codigo_postal: e.target.value })}
                                  disabled={editingCardId !== 'realestate_localizacao' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="0000-000"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Localidade</Label>
                                <Input
                                  value={realEstateData.localidade || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, localidade: e.target.value })}
                                  disabled={editingCardId !== 'realestate_localizacao' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="Cidade"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Freguesia</Label>
                                <Input
                                  value={realEstateData.freguesia || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, freguesia: e.target.value })}
                                  disabled={editingCardId !== 'realestate_localizacao' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="Freguesia"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Concelho</Label>
                                <Input
                                  value={realEstateData.concelho || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, concelho: e.target.value })}
                                  disabled={editingCardId !== 'realestate_localizacao' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="Concelho"
                                />
                              </div>
                            </div>
                            {/* Características como badges */}
                            {(() => {
                              const chars = Array.isArray(realEstateData?.caracteristicas)
                                ? realEstateData.caracteristicas
                                : typeof realEstateData?.caracteristicas === 'string' && realEstateData.caracteristicas.trim()
                                  ? realEstateData.caracteristicas.split(',').map(s => s.trim()).filter(Boolean)
                                  : [];
                              return chars.length > 0 ? (
                                <div className="mt-3 space-y-1">
                                  <Label className="text-xs text-muted-foreground">Características Pretendidas</Label>
                                  <div className="flex flex-wrap gap-2">
                                    {chars.map((c, idx) => (
                                      <Badge key={idx} variant="secondary">{c}</Badge>
                                    ))}
                                  </div>
                                </div>
                              ) : null;
                            })()}
                            <div className="mt-3 space-y-1">
                              <Label className="text-xs text-muted-foreground">Outras Informações</Label>
                              <Textarea
                                value={realEstateData.outras_informacoes || ""}
                                onChange={(e) => setRealEstateData({ ...realEstateData, outras_informacoes: e.target.value })}
                                disabled={editingCardId !== 'realestate_localizacao' || !canEditRealEstate}
                                rows={2}
                              />
                            </div>
                            </>
                            )}
                          </CardContent>
                        </Card>

                        {/* ====== Grupo C: Dados do CPCV e Prazos ====== */}
                        {/* PACOTE DH — tornou-se colapsável (progressive disclosure) */}
                        <Card className={`border-l-4 border-l-amber-500 ${editingCardId !== 'realestate_cpcv' ? 'read-only-card' : ''}`}>
                          <CardContent className="pt-4">
                            <CardHeaderWithEdit title="Dados do CPCV e Prazos" cardKey="realestate_cpcv" icon={FileSignature} canEdit={canEditRealEstate} collapsible />
                            {!shouldCardBeCollapsed('realestate_cpcv') && (
                            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                              {/* Valores Financeiros do CPCV (Fase 3) */}
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Sinal / Entrada (€)</Label>
                                <Input
                                  type="number"
                                  value={financialData.valor_entrada || ""}
                                  onChange={(e) => setFinancialData({ ...financialData, valor_entrada: parseFloat(e.target.value) || null })}
                                  disabled={editingCardId !== 'realestate_cpcv' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="0.00"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Data do Sinal</Label>
                                <Input
                                  type="date"
                                  value={financialData.data_sinal || ""}
                                  onChange={(e) => setFinancialData({ ...financialData, data_sinal: e.target.value })}
                                  disabled={editingCardId !== 'realestate_cpcv' || !canEditRealEstate}
                                  className="h-9"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Reforço do Sinal (€)</Label>
                                <Input
                                  type="number"
                                  value={financialData.reforco_sinal || ""}
                                  onChange={(e) => setFinancialData({ ...financialData, reforco_sinal: parseFloat(e.target.value) || null })}
                                  disabled={editingCardId !== 'realestate_cpcv' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="0.00"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Comissão Mediação (€)</Label>
                                <Input
                                  type="number"
                                  value={financialData.comissao_mediacao || ""}
                                  onChange={(e) => setFinancialData({ ...financialData, comissao_mediacao: parseFloat(e.target.value) || null })}
                                  disabled={editingCardId !== 'realestate_cpcv' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="0.00"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Data do CPCV</Label>
                                <Input
                                  type="date"
                                  value={realEstateData.data_cpcv || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, data_cpcv: e.target.value })}
                                  disabled={editingCardId !== 'realestate_cpcv' || !canEditRealEstate}
                                  className="h-9"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Data Escritura Prevista</Label>
                                <Input
                                  type="date"
                                  value={realEstateData.data_escritura_prevista || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, data_escritura_prevista: e.target.value })}
                                  disabled={editingCardId !== 'realestate_cpcv' || !canEditRealEstate}
                                  className="h-9"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Prazo Escritura (dias)</Label>
                                <Input
                                  type="number"
                                  min="0"
                                  value={realEstateData.prazo_escritura_dias || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, prazo_escritura_dias: parseInt(e.target.value) || null })}
                                  disabled={editingCardId !== 'realestate_cpcv' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="Ex: 90"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Data Entrega de Chaves</Label>
                                <Input
                                  type="date"
                                  value={realEstateData.data_entrega_chaves || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, data_entrega_chaves: e.target.value })}
                                  disabled={editingCardId !== 'realestate_cpcv' || !canEditRealEstate}
                                  className="h-9"
                                />
                              </div>
                              <div className="space-y-1 sm:col-span-2">
                                <Label className="text-xs text-muted-foreground">Condição Suspensiva</Label>
                                <Input
                                  value={realEstateData.condicao_suspensiva || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, condicao_suspensiva: e.target.value })}
                                  disabled={editingCardId !== 'realestate_cpcv' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="Ex: Aprovação de financiamento bancário"
                                />
                              </div>
                              <div className="space-y-1 sm:col-span-2 md:col-span-3">
                                <Label className="text-xs text-muted-foreground">Observações do CPCV</Label>
                                <Textarea
                                  value={realEstateData.observacoes_cpcv || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, observacoes_cpcv: e.target.value })}
                                  disabled={editingCardId !== 'realestate_cpcv' || !canEditRealEstate}
                                  rows={2}
                                  placeholder="Observações adicionais sobre o CPCV"
                                />
                              </div>
                            </div>
                            )}
                          </CardContent>
                        </Card>

                        {/* Dados do Proprietário (existente) */}
                        {/* PACOTE DH — tornou-se colapsável (progressive disclosure) */}
                        <Card className={`border-l-4 border-l-orange-500 ${editingCardId !== 'realestate_vendedor' ? 'read-only-card' : ''}`}>
                          <CardContent className="pt-4">
                            <CardHeaderWithEdit title="Dados do Proprietário / Vendedor" cardKey="realestate_vendedor" icon={Users} canEdit={canEditRealEstate} collapsible />
                            {!shouldCardBeCollapsed('realestate_vendedor') && (
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Nome</Label>
                                <Input
                                  value={realEstateData.owner_name || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, owner_name: e.target.value })}
                                  disabled={editingCardId !== 'realestate_vendedor' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="Nome completo"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Email</Label>
                                <Input
                                  type="email"
                                  value={realEstateData.owner_email || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, owner_email: e.target.value })}
                                  disabled={editingCardId !== 'realestate_vendedor' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="email@exemplo.com"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Telefone</Label>
                                <Input
                                  value={realEstateData.owner_phone || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, owner_phone: e.target.value })}
                                  disabled={editingCardId !== 'realestate_vendedor' || !canEditRealEstate}
                                  className="h-9"
                                  placeholder="+351 000 000 000"
                                />
                              </div>
                            </div>
                            )}
                          </CardContent>
                        </Card>

                      </div>
                    )}
    </>
  );
}
