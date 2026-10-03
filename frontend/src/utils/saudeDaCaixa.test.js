/**
 * O aviso de uma caixa de correio a falhar (Lote 7, ponto 4).
 *
 * A sincronização automática morria num `logger.warning` e o ecrã mostrava a
 * lista antiga sem um único aviso. Estes testes afirmam o que se mostra — e,
 * sobretudo, o que NÃO se mostra, porque um aviso que aparece sempre ensina a
 * ignorar os que importam.
 */
import { describe, expect, it } from "vitest";
import {
  contasComProblema,
  diasEmFalha,
  precisaDeAviso,
  rotuloCurto,
  textoDoAviso,
} from "./saudeDaCaixa";

const FALHA_DE_AUTENTICACAO = {
  email_address: "a@b.pt",
  sync_status: "failed",
  sync_error_class: "autenticacao",
  sync_requires_action: true,
  sync_message: "As credenciais desta caixa foram recusadas pelo servidor.",
  sync_failing_since: "2026-09-30T10:00:00Z",
};

const FALHA_DE_REDE = {
  email_address: "c@d.pt",
  sync_status: "failed",
  sync_error_class: "rede",
  sync_requires_action: false,
  sync_message: "Não foi possível alcançar o servidor de email.",
  sync_failing_since: "2026-10-03T10:00:00Z",
};

const SAUDAVEL = {
  email_address: "e@f.pt",
  sync_status: "ok",
  sync_requires_action: false,
  sync_message: "",
};

const NUNCA_SINCRONIZOU = {
  email_address: "g@h.pt",
  sync_status: "desconhecido",
  sync_requires_action: false,
};

describe("precisaDeAviso", () => {
  it("avisa de uma falha de autenticação", () => {
    expect(precisaDeAviso(FALHA_DE_AUTENTICACAO)).toBe(true);
  });

  it("NÃO avisa de uma falha de rede nem de um limite de tráfego", () => {
    // Passam sozinhas. Avisar delas com a mesma força ensina a ignorar o
    // aviso todo — é o `desactivado ≠ em baixo` do painel de sinais vitais.
    expect(precisaDeAviso(FALHA_DE_REDE)).toBe(false);
    expect(precisaDeAviso({ ...FALHA_DE_REDE, sync_error_class: "limite" }))
      .toBe(false);
  });

  it("não avisa de uma conta saudável", () => {
    expect(precisaDeAviso(SAUDAVEL)).toBe(false);
  });

  it("não avisa de uma conta que nunca sincronizou", () => {
    // Pintá-la de vermelho seria um aviso falso no primeiro dia de todos.
    expect(precisaDeAviso(NUNCA_SINCRONIZOU)).toBe(false);
  });

  it("não rebenta com entrada inválida", () => {
    for (const lixo of [null, undefined, "x", 3, []]) {
      expect(precisaDeAviso(lixo)).toBe(false);
    }
  });

  it("não reclassifica a mensagem do servidor por sua conta", () => {
    // A classificação é do SERVIDOR. Duas classificações da mesma mensagem
    // divergem, e a que divergir avisa do que não deve.
    expect(precisaDeAviso({
      sync_status: "failed",
      sync_message: "535 Incorrect authentication data",
      sync_requires_action: false,
    })).toBe(false);
  });
});

describe("contasComProblema", () => {
  it("devolve só as que precisam de aviso", () => {
    const contas = [SAUDAVEL, FALHA_DE_AUTENTICACAO, FALHA_DE_REDE, NUNCA_SINCRONIZOU];
    expect(contasComProblema(contas).map((c) => c.email_address)).toEqual(["a@b.pt"]);
  });

  it("entrada que não é lista dá lista vazia", () => {
    for (const lixo of [null, undefined, {}, "x"]) {
      expect(contasComProblema(lixo)).toEqual([]);
    }
  });
});

describe("diasEmFalha", () => {
  const agora = new Date("2026-10-03T12:00:00Z");

  it("conta dias inteiros", () => {
    expect(diasEmFalha("2026-10-03T10:00:00Z", agora)).toBe(0);
    expect(diasEmFalha("2026-10-02T10:00:00Z", agora)).toBe(1);
    expect(diasEmFalha("2026-09-20T10:00:00Z", agora)).toBe(13);
  });

  it("devolve null para o que não sabe", () => {
    expect(diasEmFalha(null, agora)).toBeNull();
    expect(diasEmFalha("", agora)).toBeNull();
    expect(diasEmFalha("não é data", agora)).toBeNull();
  });

  it("uma data no FUTURO devolve null em vez de um número negativo", () => {
    // Relógios dessincronizados existem; «há -2 dias» no ecrã é pior do que
    // não dizer desde quando.
    expect(diasEmFalha("2026-10-05T10:00:00Z", agora)).toBeNull();
  });
});

describe("textoDoAviso", () => {
  const agora = new Date("2026-10-03T12:00:00Z");

  it("usa a mensagem do SERVIDOR e acrescenta a antiguidade", () => {
    // A mensagem diz o que fazer; duplicá-la aqui fazia-a divergir da que o
    // administrador vê.
    const texto = textoDoAviso(FALHA_DE_AUTENTICACAO, agora);
    expect(texto).toContain("credenciais");
    expect(texto).toContain("há 3 dias");
  });

  it("distingue hoje, ontem e há N dias", () => {
    const comData = (d) => ({ ...FALHA_DE_AUTENTICACAO, sync_failing_since: d });
    expect(textoDoAviso(comData("2026-10-03T08:00:00Z"), agora)).toContain("desde hoje");
    expect(textoDoAviso(comData("2026-10-02T08:00:00Z"), agora)).toContain("desde ontem");
    expect(textoDoAviso(comData("2026-09-25T08:00:00Z"), agora)).toContain("há 8 dias");
  });

  it("sem data não inventa antiguidade", () => {
    const texto = textoDoAviso(
      { ...FALHA_DE_AUTENTICACAO, sync_failing_since: null }, agora,
    );
    expect(texto).toContain("credenciais");
    expect(texto).not.toContain("desde");
    expect(texto).not.toContain("há ");
  });

  it("sem mensagem do servidor usa um recuo em vez de ficar vazio", () => {
    const texto = textoDoAviso(
      { ...FALHA_DE_AUTENTICACAO, sync_message: "" }, agora,
    );
    expect(texto).toContain("falhar");
  });

  it("uma conta sem problema não tem texto", () => {
    expect(textoDoAviso(SAUDAVEL, agora)).toBe("");
    expect(textoDoAviso(FALHA_DE_REDE, agora)).toBe("");
  });
});

describe("rotuloCurto", () => {
  it("é um ponto de atenção só para quem precisa de acção", () => {
    expect(rotuloCurto(FALHA_DE_AUTENTICACAO)).toBe("Credenciais recusadas");
    expect(rotuloCurto(FALHA_DE_REDE)).toBe("");
    expect(rotuloCurto(SAUDAVEL)).toBe("");
  });
});
