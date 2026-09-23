/**
 * Campo "Rede / Grupo Empresarial" (Lote 5, ponto 2).
 *
 * O CAMPO ERA TEXTO LIVRE — e fui eu que o pus assim no Lote 4.
 * Escrever `grupo_power` em vez de `grupo_power_precision` não dá erro
 * nenhum: cria silenciosamente uma REDE NOVA com uma empresa dentro.
 * O isolamento quebra ao contrário — esconde dados de quem os devia ver
 * — e o sintoma só aparece dias depois, sem nada que o ligue ao engano.
 *
 * Um `select` fechado também não serve: tem de ser possível criar a
 * primeira rede de um grupo novo. Daí o autocomplete sobre as redes que
 * já existem, mais um aviso explícito quando o valor é inédito.
 */
import { useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import CompanyNetworkField from "../CompanyNetworkField";

const EMPRESAS = [
  { id: "cmp-power", name: "Power Real Estate", network_id: "grupo_power_precision" },
  { id: "cmp-precision", name: "Precision Crédito", network_id: "grupo_power_precision" },
  { id: "cmp-domus", name: "Domus", network_id: "grupo_domus" },
  { id: "cmp-nova", name: "Nova", network_id: "" },
];

function montar(props = {}) {
  const onChange = vi.fn();
  render(
    <CompanyNetworkField
      value=""
      onChange={onChange}
      companies={EMPRESAS}
      {...props}
    />,
  );
  return { onChange };
}

describe("As redes existentes", () => {
  it("oferece as redes já em uso", () => {
    montar();
    const opcoes = [...document.querySelectorAll("datalist option")].map(
      (o) => o.value,
    );
    expect(opcoes).toContain("grupo_power_precision");
    expect(opcoes).toContain("grupo_domus");
  });

  it("não repete uma rede partilhada por várias empresas", () => {
    montar();
    const opcoes = [...document.querySelectorAll("datalist option")].map(
      (o) => o.value,
    );
    expect(opcoes.filter((o) => o === "grupo_power_precision")).toHaveLength(1);
  });

  it("ignora empresas sem rede", () => {
    montar();
    const opcoes = [...document.querySelectorAll("datalist option")].map(
      (o) => o.value,
    );
    expect(opcoes).not.toContain("");
  });
});

describe("O aviso que evita o erro de dactilografia", () => {
  it("diz a quantas empresas a rede escolhida se junta", () => {
    montar({ value: "grupo_power_precision" });
    expect(screen.getByText(/2 empresas?/i)).toBeTruthy();
  });

  it("avisa que uma rede inédita nasce isolada", () => {
    // É este o aviso que apanha o `grupo_power` em vez de
    // `grupo_power_precision`: o utilizador vê "rede nova" onde
    // esperava "junta-se a 2 empresas".
    montar({ value: "grupo_powr" });
    expect(screen.getByText(/rede nova/i)).toBeTruthy();
  });

  it("em branco explica que a empresa fica isolada", () => {
    montar({ value: "" });
    expect(screen.getByText(/isolada/i)).toBeTruthy();
  });
});

/**
 * O campo é CONTROLADO: sem devolver o valor, cada tecla chega sozinha e
 * as asserções sobre o texto completo medem uma letra. A primeira versão
 * destes dois testes passou por isso — " grupo_domus " começa por um
 * espaço, `"".trim()` é `""`, e a asserção dava-se por satisfeita.
 */
function CampoControlado({ inicial = "", aoMudar }) {
  const [valor, setValor] = useState(inicial);
  return (
    <CompanyNetworkField
      value={valor}
      onChange={(v) => {
        setValor(v);
        aoMudar?.(v);
      }}
      companies={EMPRESAS}
    />
  );
}

describe("O que o campo devolve", () => {
  it("apara espaços — um espaço à direita cria outra rede", async () => {
    const utilizador = userEvent.setup();
    const aoMudar = vi.fn();
    render(<CampoControlado aoMudar={aoMudar} />);

    await utilizador.type(screen.getByLabelText(/rede/i), " grupo_domus ");

    await waitFor(() => expect(aoMudar).toHaveBeenCalled());
    const ultimo = aoMudar.mock.calls.at(-1)[0];
    expect(ultimo).toBe("grupo_domus");
  });

  it("permite escrever uma rede que ainda não existe", async () => {
    const utilizador = userEvent.setup();
    const aoMudar = vi.fn();
    render(<CampoControlado aoMudar={aoMudar} />);

    await utilizador.type(screen.getByLabelText(/rede/i), "grupo_novo");

    await waitFor(() => expect(aoMudar).toHaveBeenCalled());
    expect(aoMudar.mock.calls.at(-1)[0]).toBe("grupo_novo");
  });

  it("o aviso segue o que está escrito", async () => {
    // Contraprova dos avisos: com o campo controlado a sério, o texto
    // muda ao escrever — e não só na montagem.
    const utilizador = userEvent.setup();
    render(<CampoControlado />);

    expect(screen.getByText(/isolada/i)).toBeTruthy();
    await utilizador.type(screen.getByLabelText(/rede/i), "grupo_domus");
    await waitFor(() => expect(screen.getByText(/1 empresa\b/i)).toBeTruthy());
  });
});
