import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import AssignmentContextCard from "../AssignmentContextCard";

// «20 ficheiros aguardam a Indexação» — e a que Index? A linha está sempre à vista.
describe("AssignmentContextCard — linha da Indexação", () => {
  it("mostra o Index atribuído", () => {
    render(<AssignmentContextCard process={{ id: "p1", indexacao_name: "Iris" }} />);
    expect(screen.getByText("Indexação")).toBeInTheDocument();
    expect(screen.getByText("Iris")).toBeInTheDocument();
  });

  it("sem Index diz «Não atribuído» em vez de esconder a linha", () => {
    render(<AssignmentContextCard process={{ id: "p1" }} />);
    expect(screen.getByText("Indexação")).toBeInTheDocument();
    expect(screen.getAllByText("Não atribuído").length).toBeGreaterThanOrEqual(1);
  });
});
