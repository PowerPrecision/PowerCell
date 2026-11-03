import { describe, it, expect } from "vitest";
import { deveApitar } from "./deveApitar";

describe("deveApitar", () => {
  it("apita só o que o servidor marcou como importante", () => {
    expect(deveApitar({ alerta: true })).toBe(true);
    expect(deveApitar({ agrupada: true, apitar: true })).toBe(true);
  });

  it("fica calado no resto, incluindo avisos antigos sem a marca", () => {
    expect(deveApitar({ alerta: false })).toBe(false);
    expect(deveApitar({ message: "aviso antigo" })).toBe(false);
    expect(deveApitar(null)).toBe(false);
  });
});
