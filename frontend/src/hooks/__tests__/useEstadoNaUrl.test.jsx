import { act, renderHook } from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate, useNavigationType } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CODEC_BOOLEANO,
  CODEC_LISTA,
  useEstadoNaUrl,
  useTextoNaUrl,
} from "../useEstadoNaUrl";

const SEM_ETIQUETAS = [];

function montar(hook, url = "/quadro") {
  const envolver = ({ children }) => <MemoryRouter initialEntries={[url]}>{children}</MemoryRouter>;
  return renderHook(
    () => ({ estado: hook(), local: useLocation(), tipo: useNavigationType(), nav: useNavigate() }),
    { wrapper: envolver },
  );
}

describe("useEstadoNaUrl", () => {
  it("sem parâmetro devolve a omissão e o URL fica limpo", () => {
    const { result } = montar(() => useEstadoNaUrl("kb_urg", "all"));
    expect(result.current.estado[0]).toBe("all");
    expect(result.current.local.search).toBe("");
  });

  it("lê o valor do URL (é isto que sobrevive ao «Voltar»)", () => {
    const { result } = montar(() => useEstadoNaUrl("kb_urg", "all"), "/quadro?kb_urg=high");
    expect(result.current.estado[0]).toBe("high");
  });

  it("escrever põe o parâmetro; escrever a omissão tira-o", () => {
    const { result } = montar(() => useEstadoNaUrl("kb_urg", "all"));
    act(() => result.current.estado[1]("high"));
    expect(result.current.local.search).toBe("?kb_urg=high");
    expect(result.current.estado[0]).toBe("high");
    act(() => result.current.estado[1]("all"));
    expect(result.current.local.search).toBe("");
  });

  it("nunca pisa os outros parâmetros da página", () => {
    const { result } = montar(() => useEstadoNaUrl("kb_urg", "all"), "/quadro?consultor=u1&page=3");
    act(() => result.current.estado[1]("high"));
    const p = new URLSearchParams(result.current.local.search);
    expect(p.get("consultor")).toBe("u1");
    expect(p.get("page")).toBe("3");
    expect(p.get("kb_urg")).toBe("high");
  });

  it("escreve com REPLACE: mexer num filtro não empilha história", () => {
    const { result } = montar(() => useEstadoNaUrl("kb_urg", "all"));
    act(() => result.current.estado[1]("high"));
    expect(result.current.tipo).toBe("REPLACE");
  });

  it("aceita a forma funcional", () => {
    const { result } = montar(() => useEstadoNaUrl("kb_n", "0"), "/quadro?kb_n=2");
    act(() => result.current.estado[1]((n) => String(Number(n) + 1)));
    expect(result.current.estado[0]).toBe("3");
  });
});

describe("codecs", () => {
  it("booleano: só true vai para o URL", () => {
    const { result } = montar(() => useEstadoNaUrl("kb_sub35", false, CODEC_BOOLEANO));
    expect(result.current.estado[0]).toBe(false);
    act(() => result.current.estado[1](true));
    expect(result.current.local.search).toBe("?kb_sub35=true");
    expect(result.current.estado[0]).toBe(true);
    act(() => result.current.estado[1](false));
    expect(result.current.local.search).toBe("");
  });

  it("booleano: um valor estranho no URL é falso", () => {
    const { result } = montar(() => useEstadoNaUrl("kb_sub35", false, CODEC_BOOLEANO), "/q?kb_sub35=talvez");
    expect(result.current.estado[0]).toBe(false);
  });

  it("lista: vai separada por vírgulas e volta como lista, sem vazios", () => {
    const { result } = montar(() => useEstadoNaUrl("kb_labels", SEM_ETIQUETAS, CODEC_LISTA));
    expect(result.current.estado[0]).toBe(SEM_ETIQUETAS);
    act(() => result.current.estado[1](["a", "b"]));
    expect(result.current.local.search).toBe("?kb_labels=a%2Cb");
    expect(result.current.estado[0]).toEqual(["a", "b"]);
    act(() => result.current.estado[1]([]));
    expect(result.current.local.search).toBe("");
  });

  it("lista: ' a, ,b ' limpa-se", () => {
    const { result } = montar(() => useEstadoNaUrl("kb_labels", SEM_ETIQUETAS, CODEC_LISTA), "/q?kb_labels=%20a%2C%20%2Cb");
    expect(result.current.estado[0]).toEqual(["a", "b"]);
  });

  it("o valor devolvido é estável entre renders sem mudanças (serve de dependência)", () => {
    const { result, rerender } = montar(() => useEstadoNaUrl("kb_labels", SEM_ETIQUETAS, CODEC_LISTA), "/q?kb_labels=a");
    const primeiro = result.current.estado[0];
    rerender();
    expect(result.current.estado[0]).toBe(primeiro);
  });
});

describe("useTextoNaUrl", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("arranca com o que está no URL", () => {
    const { result } = montar(() => useTextoNaUrl("kb_q"), "/quadro?kb_q=ana");
    expect(result.current.estado[0]).toBe("ana");
  });

  it("a caixa é imediata e o URL só segue quando se pára de escrever", () => {
    const { result } = montar(() => useTextoNaUrl("kb_q", { atrasoMs: 300 }));
    act(() => result.current.estado[1]("an"));
    expect(result.current.estado[0]).toBe("an");
    expect(result.current.local.search).toBe("");
    act(() => result.current.estado[1]("ana"));
    act(() => { vi.advanceTimersByTime(299); });
    expect(result.current.local.search).toBe("");
    act(() => { vi.advanceTimersByTime(2); });
    expect(result.current.local.search).toBe("?kb_q=ana");
  });

  it("apagar tudo limpa o parâmetro", () => {
    const { result } = montar(() => useTextoNaUrl("kb_q", { atrasoMs: 10 }), "/quadro?kb_q=ana");
    act(() => result.current.estado[1](""));
    act(() => { vi.advanceTimersByTime(20); });
    expect(result.current.local.search).toBe("");
  });

  it("a caixa acompanha o URL quando ele muda por fora (Voltar/Avançar)", () => {
    const envolver = ({ children }) => (
      <MemoryRouter initialEntries={["/q?kb_q=ana", "/q?kb_q=rui"]} initialIndex={1}>{children}</MemoryRouter>
    );
    const { result } = renderHook(() => ({ t: useTextoNaUrl("kb_q"), nav: useNavigate() }), { wrapper: envolver });
    expect(result.current.t[0]).toBe("rui");
    act(() => result.current.nav(-1));
    expect(result.current.t[0]).toBe("ana");
  });
});
