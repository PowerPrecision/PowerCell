// @vitest-environment node
/**
 * O `FormData` e o cabeçalho que o destrói (Épico 10, dívida técnica).
 *
 * SINTOMA EM PRODUÇÃO: `POST /api/documents/client/{id}/upload` devolvia
 * 422 com `Field required` para `body.file` E `body.category` — os dois
 * campos, o que é a assinatura de um corpo que o servidor não conseguiu
 * sequer analisar como multipart.
 *
 * CAUSA: a instância Axios tem `Content-Type: application/json` como
 * predefinição. O `transformRequest` do Axios 1.x faz, literalmente:
 *
 *     if (isFormData) {
 *       return hasJSONContentType ? JSON.stringify(formDataToJSON(data)) : data;
 *     }
 *
 * ou seja, com JSON no cabeçalho **converte o FormData em JSON** e o
 * ficheiro vira `{}`. Só DEPOIS, já dentro do adaptador, é que o Axios
 * limparia o cabeçalho para o browser pôr o `boundary` — e a essa altura
 * já não há FormData nenhum para limpar. A ordem é que decide.
 *
 * A LIÇÃO, QUE INVERTE A REGRA QUE SEGUÍAMOS: "não escrever o
 * Content-Type à mão" é necessário mas NÃO é suficiente. Omitir não
 * limpa: deixa entrar a predefinição da instância. É preciso ANULÁ-LO
 * explicitamente, e é isso que o interceptor faz num sítio só.
 */
import { readFileSync } from "node:fs";
import http from "node:http";
import axios from "axios";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { ehFormData, normalizarCabecalhosDeFormData } from "../../utils/formDataTransport";

let servidor;
let url;
const recebidos = [];

beforeAll(async () => {
  servidor = http.createServer((req, res) => {
    let corpo = "";
    req.on("data", (c) => (corpo += c));
    req.on("end", () => {
      recebidos.push({ contentType: req.headers["content-type"] || "", corpo });
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end("{}");
    });
  });
  await new Promise((r) => servidor.listen(0, "127.0.0.1", r));
  url = `http://127.0.0.1:${servidor.address().port}/upload`;
});

afterAll(() => servidor?.close());

/** A MESMA predefinição de `services/api.js` — é ela que causa o defeito. */
function instancia({ comInterceptor }) {
  const cliente = axios.create({ headers: { "Content-Type": "application/json" } });
  if (comInterceptor) {
    cliente.interceptors.request.use(normalizarCabecalhosDeFormData);
  }
  return cliente;
}

function documento() {
  const fd = new FormData();
  fd.append("file", new Blob(["bytes-do-pdf"], { type: "application/pdf" }), "doc.pdf");
  fd.append("category", "Financeiros");
  return fd;
}

describe("ehFormData", () => {
  it("reconhece um FormData", () => {
    expect(ehFormData(new FormData())).toBe(true);
  });

  it("não confunde um objecto simples com FormData", () => {
    expect(ehFormData({ file: "x" })).toBe(false);
    expect(ehFormData(null)).toBe(false);
    expect(ehFormData("texto")).toBe(false);
  });
});

describe("o cabeçalho que destrói o upload", () => {
  it("SEM o interceptor, o ficheiro chega ao servidor como JSON vazio", async () => {
    // Contraprova: sem isto, o teste seguinte poderia passar por acaso e
    // nunca saberíamos que o interceptor é que o salva.
    await instancia({ comInterceptor: false }).post(url, documento());
    const { contentType, corpo } = recebidos.at(-1);

    expect(contentType).toContain("application/json");
    expect(corpo).toContain('"file":{}');   // o ficheiro desapareceu
    expect(corpo).not.toContain("bytes-do-pdf");
  });

  it("COM o interceptor, sai multipart com boundary e o ficheiro inteiro", async () => {
    await instancia({ comInterceptor: true }).post(url, documento());
    const { contentType, corpo } = recebidos.at(-1);

    expect(contentType).toContain("multipart/form-data");
    expect(contentType).toContain("boundary=");
    expect(corpo).toContain('name="file"');
    expect(corpo).toContain('filename="doc.pdf"');
    expect(corpo).toContain("bytes-do-pdf");
    expect(corpo).toContain('name="category"');
    expect(corpo).toContain("Financeiros");
  });

  it("um Content-Type escrito à mão também é anulado", async () => {
    // Havia funções a escrever `multipart/form-data` sem boundary. No
    // browser o Axios acabava por o limpar, mas depender disso é depender
    // de um pormenor interno da biblioteca.
    await instancia({ comInterceptor: true }).post(url, documento(), {
      headers: { "Content-Type": "multipart/form-data" },
    });
    const { contentType, corpo } = recebidos.at(-1);

    expect(contentType).toContain("boundary=");
    expect(corpo).toContain("bytes-do-pdf");
  });

  it("objecto simples com multipart explícito continua a virar multipart", async () => {
    // `createTempLink` usa esta forma de propósito: passa um objecto e
    // deixa o Axios convertê-lo em FormData por causa do cabeçalho. No
    // momento do interceptor `config.data` ainda NÃO é FormData, por isso
    // não lhe tocamos — e é preciso que continue assim.
    await instancia({ comInterceptor: true }).post(
      url,
      { titulo: "Pedido de documentos", dias: 7 },
      { headers: { "Content-Type": "multipart/form-data" } },
    );
    const { contentType, corpo } = recebidos.at(-1);

    expect(contentType).toContain("multipart/form-data");
    expect(corpo).toContain('name="titulo"');
    expect(corpo).toContain("Pedido de documentos");
  });

  it("um pedido JSON normal continua a ser JSON", async () => {
    // O interceptor não pode ter efeitos colaterais no resto da API.
    await instancia({ comInterceptor: true }).post(url, { nome: "Maria" });
    const { contentType, corpo } = recebidos.at(-1);

    expect(contentType).toContain("application/json");
    expect(corpo).toBe('{"nome":"Maria"}');
  });
});


describe("a ligação ao cliente real", () => {
  // Os testes acima montam uma instância com a MESMA configuração de
  // `services/api.js`. Estas guardas afirmam que essa premissa continua
  // verdadeira — sem elas, o `api.js` podia mudar e os testes continuavam
  // verdes a provar coisas sobre um cliente que já não existe.
  const fonte = readFileSync(
    new URL("../api.js", import.meta.url), "utf-8",
  );

  it("o cliente Axios continua a declarar o default que causa o defeito", () => {
    expect(fonte).toMatch(/axios\.create\([\s\S]*?"Content-Type":\s*"application\/json"/);
  });

  it("o interceptor de pedido chama a normalização", () => {
    const inicio = fonte.indexOf("api.interceptors.request.use");
    const fim = fonte.indexOf("api.interceptors.response.use");
    expect(inicio).toBeGreaterThan(-1);
    expect(fonte.slice(inicio, fim)).toContain("normalizarCabecalhosDeFormData(config)");
  });

  it("nenhuma função escreve multipart/form-data sobre um FormData", () => {
    // `createTempLink` é a excepção legítima: passa um OBJECTO e deixa o
    // Axios convertê-lo. Escrever o cabeçalho sobre um FormData é que era
    // o padrão enganador — parecia a correcção e não era.
    const suspeitas = fonte
      .split("\n")
      .map((linha, i) => [i + 1, linha])
      .filter(([, linha]) => /["']Content-Type["']:\s*["']multipart\/form-data["']/.test(linha))
      .filter(([, linha]) => !linha.includes("//"));

    expect(suspeitas.map(([n]) => n)).toEqual([LINHA_DO_TEMP_LINK()]);

    function LINHA_DO_TEMP_LINK() {
      const alvo = fonte.split("\n").findIndex((l) => l.includes("createTempLink"));
      return alvo + 2; // o cabeçalho vem na linha seguinte à chamada
    }
  });

  it("a função duplicada e morta não voltou", () => {
    expect(fonte).not.toMatch(/export const uploadClientS3File\s*=/);
  });
});

describe("as duas formas de cabeçalho", () => {
  // Em produção `config.headers` é sempre um `AxiosHeaders`. O ramo do
  // objecto simples existe porque esta função é exportada e pode ser
  // chamada à mão — e um ramo que nenhum teste alcança é código morto a
  // fingir de defesa.
  it("limpa um AxiosHeaders pela API documentada", () => {
    const chamadas = [];
    const config = {
      data: new FormData(),
      headers: {
        "Content-Type": "application/json",
        setContentType: (v) => chamadas.push(v),
      },
    };
    normalizarCabecalhosDeFormData(config);
    expect(chamadas).toEqual([null]);
  });

  it("limpa um objecto simples em qualquer capitalização", () => {
    const config = {
      data: new FormData(),
      headers: { "content-TYPE": "application/json", Authorization: "Bearer x" },
    };
    normalizarCabecalhosDeFormData(config);
    expect(config.headers).toEqual({ Authorization: "Bearer x" });
  });

  it("não toca em nada quando o corpo não é FormData", () => {
    const config = { data: { a: 1 }, headers: { "Content-Type": "application/json" } };
    normalizarCabecalhosDeFormData(config);
    expect(config.headers["Content-Type"]).toBe("application/json");
  });
});
