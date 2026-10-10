import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import AvisoEmIndexacao from "./AvisoEmIndexacao";

describe("AvisoEmIndexacao", () => {
  it("diz quantos ficheiros aguardam", () => {
    render(<AvisoEmIndexacao total={2} />);
    expect(screen.getByRole("status")).toHaveTextContent(/2 ficheiros enviados aguardam a Indexação/);
  });

  it("sem ficheiros em espera não desenha nada", () => {
    const { container } = render(<AvisoEmIndexacao total={0} />);
    expect(container).toBeEmptyDOMElement();
  });
});
