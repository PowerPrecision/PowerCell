/**
 * O upload directo da bancada do Index (Out 2026): o MESMO endpoint de upload do CRM, sem sair do ecrã, e sem nunca
 * sobrepor um ficheiro que já lá está.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../services/api", () => ({ uploadProcessS3File: vi.fn() }));

import { uploadProcessS3File } from "../../../services/api";
import { TIPOS_ACEITES, UploadNaBancada } from "../UploadNaBancada";

const pdf = (nome) => new File(["%PDF-1.4"], nome, { type: "application/pdf" });

function montar(props = {}) {
  const onConcluido = vi.fn();
  render(<UploadNaBancada processId="proc-9" nomesExistentes={["recibo.pdf"]} onConcluido={onConcluido} {...props} />);
  return { onConcluido, entrada: screen.getByTestId("upload-bancada-entrada") };
}

beforeEach(() => {
  uploadProcessS3File.mockReset();
  uploadProcessS3File.mockResolvedValue({ data: { success: true } });
});

describe("UploadNaBancada", () => {
  it("o botão abre o seletor de ficheiros e tem nome acessível", async () => {
    montar();
    const botao = screen.getByRole("button", { name: /Adicionar ficheiros/ });
    expect(botao).toBeEnabled();
    expect(screen.getByTestId("upload-bancada-entrada")).toHaveAttribute("accept", TIPOS_ACEITES);
  });

  it("envia cada ficheiro para o processo, com a categoria por omissão", async () => {
    const { entrada, onConcluido } = montar();
    await userEvent.upload(entrada, [pdf("a.pdf"), pdf("b.pdf")]);
    await waitFor(() => expect(uploadProcessS3File).toHaveBeenCalledTimes(2));
    const [processo, form] = uploadProcessS3File.mock.calls[0];
    expect(processo).toBe("proc-9");
    expect(form.get("file").name).toBe("a.pdf");
    expect(form.get("category")).toBe("Outros");
    await waitFor(() => expect(onConcluido).toHaveBeenCalledWith(2));
    expect(await screen.findByText("2 ficheiros adicionados.")).toBeInTheDocument();
  });

  it("nunca sobrepõe: um nome que já existe segue com (2)", async () => {
    const { entrada } = montar();
    await userEvent.upload(entrada, [pdf("recibo.pdf")]);
    await waitFor(() => expect(uploadProcessS3File).toHaveBeenCalled());
    expect(uploadProcessS3File.mock.calls[0][1].get("custom_filename")).toBe("recibo (2).pdf");
  });

  it("um nome livre não leva custom_filename", async () => {
    const { entrada } = montar();
    await userEvent.upload(entrada, [pdf("novo.pdf")]);
    await waitFor(() => expect(uploadProcessS3File).toHaveBeenCalled());
    expect(uploadProcessS3File.mock.calls[0][1].has("custom_filename")).toBe(false);
  });

  it("dois ficheiros com o mesmo nome no lote não se pisam um ao outro", async () => {
    const { entrada } = montar({ nomesExistentes: [] });
    await userEvent.upload(entrada, [pdf("x.pdf"), pdf("x.pdf")]);
    await waitFor(() => expect(uploadProcessS3File).toHaveBeenCalledTimes(2));
    expect(uploadProcessS3File.mock.calls[0][1].has("custom_filename")).toBe(false);
    expect(uploadProcessS3File.mock.calls[1][1].get("custom_filename")).toBe("x (2).pdf");
  });

  it("uma recusa diz o motivo do servidor para esse ficheiro e os outros seguem", async () => {
    uploadProcessS3File
      .mockRejectedValueOnce({ response: { status: 403, data: { detail: "Processo fechado: reabra-o primeiro." } } })
      .mockResolvedValueOnce({ data: { success: true } });
    const { entrada, onConcluido } = montar();
    await userEvent.upload(entrada, [pdf("a.pdf"), pdf("b.pdf")]);
    expect(await screen.findByText(/«a\.pdf» não foi adicionado: Processo fechado: reabra-o primeiro\./)).toBeInTheDocument();
    expect(screen.getByText("1 ficheiro adicionado.")).toBeInTheDocument();
    expect(onConcluido).toHaveBeenCalledWith(1);
  });

  it("se nenhum entrou, não refresca a lista", async () => {
    uploadProcessS3File.mockRejectedValue({ response: { status: 500 } });
    const { entrada, onConcluido } = montar();
    await userEvent.upload(entrada, [pdf("a.pdf")]);
    expect(await screen.findByText(/não foi adicionado/)).toBeInTheDocument();
    expect(onConcluido).not.toHaveBeenCalled();
  });

  it("arrastar e largar envia os ficheiros aceites e recusa os outros dizendo quais", async () => {
    const { onConcluido } = montar();
    const zona = screen.getByTestId("upload-bancada-zona");
    const exe = new File(["MZ"], "virus.exe", { type: "application/x-msdownload" });
    fireEvent.drop(zona, { dataTransfer: { types: ["Files"], files: [pdf("largado.pdf"), exe] } });
    await waitFor(() => expect(uploadProcessS3File).toHaveBeenCalledTimes(1));
    expect(uploadProcessS3File.mock.calls[0][1].get("file").name).toBe("largado.pdf");
    expect(await screen.findByText(/virus\.exe/)).toBeInTheDocument();
    await waitFor(() => expect(onConcluido).toHaveBeenCalledWith(1));
  });

  it("desactivado não envia (nem pelo botão nem pelo arrastar)", async () => {
    montar({ desactivado: true });
    expect(screen.getByRole("button", { name: /Adicionar ficheiros/ })).toBeDisabled();
    fireEvent.drop(screen.getByTestId("upload-bancada-zona"), { dataTransfer: { types: ["Files"], files: [pdf("a.pdf")] } });
    expect(uploadProcessS3File).not.toHaveBeenCalled();
  });

  it("enquanto envia, o botão fica desligado (sem envios em duplicado)", async () => {
    let libertar;
    uploadProcessS3File.mockImplementationOnce(() => new Promise((r) => { libertar = () => r({ data: {} }); }));
    const { entrada } = montar();
    await userEvent.upload(entrada, [pdf("a.pdf")]);
    expect(screen.getByRole("button", { name: /Adicionar ficheiros/ })).toBeDisabled();
    libertar();
    await waitFor(() => expect(screen.getByRole("button", { name: /Adicionar ficheiros/ })).toBeEnabled());
  });
});
