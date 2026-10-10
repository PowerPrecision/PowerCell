import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import usePortalTheme, {
  CHAVE_DO_TEMA_DO_PORTAL,
  CLASSE_DO_PORTAL,
  guardarTemaDoPortal,
  lerTemaDoPortal,
} from "../usePortalTheme";

const raiz = () => document.documentElement;

beforeEach(() => {
  localStorage.clear();
  raiz().classList.remove("dark", CLASSE_DO_PORTAL);
});
afterEach(() => {
  raiz().classList.remove("dark", CLASSE_DO_PORTAL);
  vi.restoreAllMocks();
});

describe("a preferência guardada", () => {
  it("por omissão o Portal é CLARO — nunca segue o sistema nem o CRM", () => {
    window.matchMedia = vi.fn().mockReturnValue({ matches: true, addEventListener() {}, removeEventListener() {} });
    localStorage.setItem("theme", "dark"); // o tema do CRM não conta
    expect(lerTemaDoPortal()).toBe("light");
  });

  it("só 'dark' é noturno; qualquer outro valor é claro", () => {
    localStorage.setItem(CHAVE_DO_TEMA_DO_PORTAL, "dark");
    expect(lerTemaDoPortal()).toBe("dark");
    localStorage.setItem(CHAVE_DO_TEMA_DO_PORTAL, "lixo");
    expect(lerTemaDoPortal()).toBe("light");
  });

  it("um armazenamento bloqueado não rebenta: lê claro, guarda em silêncio", () => {
    const bloqueado = { getItem() { throw new Error("bloqueado"); }, setItem() { throw new Error("bloqueado"); } };
    expect(lerTemaDoPortal(bloqueado)).toBe("light");
    expect(() => guardarTemaDoPortal("dark", bloqueado)).not.toThrow();
  });

  it("a chave é PRÓPRIA do Portal (não a do CRM)", () => {
    expect(CHAVE_DO_TEMA_DO_PORTAL).toBe("portal-theme");
    expect(CHAVE_DO_TEMA_DO_PORTAL).not.toBe("theme");
  });
});

describe("usePortalTheme", () => {
  it("monta claro: marca o <html> como Portal e não põe dark", () => {
    const { result } = renderHook(() => usePortalTheme());
    expect(result.current.escuro).toBe(false);
    expect(raiz().classList.contains(CLASSE_DO_PORTAL)).toBe(true);
    expect(raiz().classList.contains("dark")).toBe(false);
  });

  it("um CRM em modo escuro NÃO contamina o Portal: abre claro", () => {
    raiz().classList.add("dark"); // o ThemeProvider do CRM
    renderHook(() => usePortalTheme());
    expect(raiz().classList.contains("dark")).toBe(false);
  });

  it("alternar liga o escuro, guarda-o e volta a desligar", () => {
    const { result } = renderHook(() => usePortalTheme());
    act(() => result.current.alternar());
    expect(result.current.escuro).toBe(true);
    expect(raiz().classList.contains("dark")).toBe(true);
    expect(localStorage.getItem(CHAVE_DO_TEMA_DO_PORTAL)).toBe("dark");

    act(() => result.current.alternar());
    expect(result.current.escuro).toBe(false);
    expect(raiz().classList.contains("dark")).toBe(false);
    expect(localStorage.getItem(CHAVE_DO_TEMA_DO_PORTAL)).toBe("light");
  });

  it("a escolha sobrevive: a próxima visita abre noturna", () => {
    localStorage.setItem(CHAVE_DO_TEMA_DO_PORTAL, "dark");
    const { result } = renderHook(() => usePortalTheme());
    expect(result.current.escuro).toBe(true);
    expect(raiz().classList.contains("dark")).toBe(true);
  });

  it("não escreve no tema do CRM", () => {
    const { result } = renderHook(() => usePortalTheme());
    act(() => result.current.alternar());
    expect(localStorage.getItem("theme")).toBeNull();
  });

  it("ao sair repõe o CRM como estava: escuro volta escuro", () => {
    raiz().classList.add("dark");
    const { unmount } = renderHook(() => usePortalTheme());
    expect(raiz().classList.contains("dark")).toBe(false);
    unmount();
    expect(raiz().classList.contains("dark")).toBe(true);
    expect(raiz().classList.contains(CLASSE_DO_PORTAL)).toBe(false);
  });

  it("ao sair repõe o CRM claro: o noturno do Portal não fica pendurado", () => {
    localStorage.setItem(CHAVE_DO_TEMA_DO_PORTAL, "dark");
    const { unmount } = renderHook(() => usePortalTheme());
    expect(raiz().classList.contains("dark")).toBe(true);
    unmount();
    expect(raiz().classList.contains("dark")).toBe(false);
    expect(raiz().classList.contains(CLASSE_DO_PORTAL)).toBe(false);
  });
});
