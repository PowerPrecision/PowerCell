/**
 * O ecrã dos limiares de SLA — montado a sério.
 *
 * A secção `dashboard_slas` existia no backend com omissões (7/15/30) e nunca
 * teve ecrã: mudava-se só por `PATCH /api/system-config/dashboard_slas`.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../services/api", () => ({
  getSystemConfig: vi.fn(),
  updateSystemConfigSection: vi.fn(async () => ({ data: {} })),
}));

import SlaThresholdsSection from "../SlaThresholdsSection";
import * as api from "../../../services/api";

// Valores DIFERENTES das omissões (7/15/30) de propósito. Com os valores por
// omissão aqui, um erro no caminho de leitura era indistinguível de uma
// leitura correcta — foi a mutação que o denunciou: apontar a leitura para a
// chave errada matava um único teste, e nenhum deste ficheiro.
const CONFIG = { enabled: true, novo: 4, analise: 11, aprovado: 22 };

function montar() {
  return render(<SlaThresholdsSection />);
}

describe("SlaThresholdsSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // A forma REAL de `GET /api/system-config`: `{config, fields}`. O mock
    // tinha a configuração no TOPO — uma forma inventada — e por isso os
    // testes passavam enquanto produção mostrava sempre as omissões.
    api.getSystemConfig.mockResolvedValue({ data: { config: { dashboard_slas: CONFIG } } });
  });

  it("mostra os limiares gravados", async () => {
    montar();
    expect(await screen.findByTestId("sla-novo")).toHaveValue("4");
    expect(screen.getByTestId("sla-analise")).toHaveValue("11");
    expect(screen.getByTestId("sla-aprovado")).toHaveValue("22");
  });

  it("o botão de guardar começa desactivado — nada mudou", async () => {
    montar();
    await screen.findByTestId("sla-novo");
    expect(screen.getByTestId("sla-guardar")).toBeDisabled();
  });

  it("grava os NÚMEROS na secção certa", async () => {
    const utilizador = userEvent.setup();
    montar();
    const campo = await screen.findByTestId("sla-novo");

    await utilizador.clear(campo);
    await utilizador.type(campo, "10");
    await utilizador.click(screen.getByTestId("sla-guardar"));

    await waitFor(() => {
      // Dois argumentos, não três: o `company_id` é OMITIDO (ver o último
      // teste). Passá-lo como `undefined` explícito seria outra chamada.
      expect(api.updateSystemConfigSection).toHaveBeenCalledWith(
        "dashboard_slas",
        { enabled: true, novo: 10, analise: 11, aprovado: 22 },
      );
    });
  });

  it("recusa guardar um valor inválido e diz porquê", async () => {
    const utilizador = userEvent.setup();
    montar();
    const campo = await screen.findByTestId("sla-analise");

    await utilizador.clear(campo);
    await utilizador.type(campo, "0");

    expect(await screen.findByTestId("sla-analise-erro")).toBeTruthy();
    expect(screen.getByTestId("sla-guardar")).toBeDisabled();
    expect(api.updateSystemConfigSection).not.toHaveBeenCalled();
  });

  it("depois de gravar, o botão volta a desactivar", async () => {
    // Sem actualizar a referência, ficava activo para sempre e convidava a
    // gravar o mesmo valor repetidamente.
    const utilizador = userEvent.setup();
    montar();
    const campo = await screen.findByTestId("sla-novo");

    await utilizador.clear(campo);
    await utilizador.type(campo, "9");
    await utilizador.click(screen.getByTestId("sla-guardar"));

    await waitFor(() => {
      expect(screen.getByTestId("sla-guardar")).toBeDisabled();
    });
  });

  it("um erro de leitura é DITO, e avisa que guardar escreve por cima", async () => {
    // O caso perigoso: falhar a ler e mostrar as omissões como se fossem os
    // valores gravados.
    api.getSystemConfig.mockRejectedValue({
      response: { data: { detail: "Sem permissão" } },
    });
    montar();

    const aviso = await screen.findByTestId("sla-erro-leitura");
    expect(aviso.textContent).toContain("Sem permissão");
    expect(aviso.textContent).toContain("escreve por cima");
  });

  it("diz que o âmbito é de TODAS as empresas", async () => {
    // O leitor (`stats_sla._limiares`) chama `get_system_config()` sem
    // company_id. Um ecrã que sugerisse âmbito por empresa mentia.
    montar();
    await screen.findByTestId("sla-novo");
    expect(screen.getByTestId("sla-thresholds-section").textContent).toContain(
      "todas as empresas",
    );
  });

  it("não envia company_id — o âmbito é o mesmo que o leitor usa", async () => {
    const utilizador = userEvent.setup();
    montar();
    const campo = await screen.findByTestId("sla-aprovado");

    await utilizador.clear(campo);
    await utilizador.type(campo, "45");
    await utilizador.click(screen.getByTestId("sla-guardar"));

    await waitFor(() => {
      expect(api.updateSystemConfigSection).toHaveBeenCalled();
    });
    const [, , companyId] = api.updateSystemConfigSection.mock.calls[0];
    expect(companyId).toBeUndefined();
  });
});
