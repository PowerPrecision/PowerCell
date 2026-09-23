/**
 * Campo "Rede / Grupo Empresarial" (Lote 5, ponto 2).
 *
 * Era um `Input` de texto livre — e um `grupo_power` em vez de
 * `grupo_power_precision` não dá erro nenhum: cria silenciosamente uma
 * rede nova com uma empresa dentro. O isolamento quebra ao contrário
 * (esconde dados de quem os devia ver) e o sintoma aparece dias depois,
 * sem nada que o ligue ao engano.
 *
 * Um `select` fechado também não servia: tem de ser possível criar a
 * primeira rede de um grupo novo. A solução é autocomplete sobre as
 * redes que já existem — via `<datalist>`, que é nativo, acessível e
 * não impede a escrita livre — mais um aviso explícito sobre o efeito
 * do valor actual. É o aviso, não a lista, que apanha a gralha: o
 * utilizador vê "rede nova" onde esperava "junta-se a 2 empresas".
 */
import { useId, useMemo } from "react";

import { Input } from "../ui/input";
import { Label } from "../ui/label";

/**
 * @param {Object} props
 * @param {string} props.value            — rede actual (string vazia = isolada)
 * @param {(v: string) => void} props.onChange
 * @param {Array<{id: string, name: string, network_id?: string}>} props.companies
 */
export default function CompanyNetworkField({ value, onChange, companies = [] }) {
  const inputId = useId();
  const listId = `${inputId}-redes`;

  const redes = useMemo(() => {
    const contagem = new Map();
    for (const empresa of companies) {
      const rede = String(empresa?.network_id || "").trim();
      if (!rede) continue;
      contagem.set(rede, (contagem.get(rede) || 0) + 1);
    }
    return contagem;
  }, [companies]);

  const actual = String(value || "").trim();
  const empresasNaRede = redes.get(actual) || 0;

  let aviso;
  if (!actual) {
    aviso = "Em branco, a empresa fica isolada: ninguém de fora vê os seus processos e clientes.";
  } else if (empresasNaRede > 0) {
    aviso = `Junta-se a ${empresasNaRede} empresa${empresasNaRede === 1 ? "" : "s"} nesta rede, passando a partilhar a visibilidade dos dados.`;
  } else {
    aviso = "Rede nova — a empresa fica sozinha nela. Confirme o nome se pretendia juntá-la a um grupo existente.";
  }

  return (
    <div className="space-y-2">
      <Label htmlFor={inputId}>Rede / Grupo Empresarial</Label>
      <Input
        id={inputId}
        list={listId}
        value={value ?? ""}
        // Aparar aqui e não só ao gravar: um espaço à direita é uma rede
        // diferente, e a diferença é invisível no ecrã.
        onChange={(e) => onChange(e.target.value.trim())}
        placeholder="ex: grupo_power_precision"
        data-testid="company-network-input"
        autoComplete="off"
      />
      <datalist id={listId}>
        {[...redes.keys()].sort().map((rede) => (
          <option key={rede} value={rede} />
        ))}
      </datalist>
      <p className="text-xs text-muted-foreground">{aviso}</p>
    </div>
  );
}
