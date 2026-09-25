/**
 * O cabeçalho que destrói um upload (Épico 10, dívida técnica).
 *
 * SINTOMA: `POST /api/documents/client/{id}/upload` devolvia **422** com
 * `Field required` para `body.file` E `body.category`. Os dois campos ao
 * mesmo tempo é a assinatura de um corpo que o servidor não conseguiu
 * sequer analisar como multipart — não de um campo esquecido.
 *
 * CAUSA: a instância Axios de `services/api.js` declara
 * `Content-Type: application/json` como predefinição, e o
 * `transformRequest` do Axios 1.x faz, literalmente:
 *
 *     if (isFormData) {
 *       return hasJSONContentType ? JSON.stringify(formDataToJSON(data)) : data;
 *     }
 *
 * Com JSON no cabeçalho, **o FormData é convertido em JSON** e o ficheiro
 * vira `{}`. Só mais tarde, já dentro do adaptador, é que o Axios limparia
 * o cabeçalho para o browser gerar o `boundary` — e a essa altura já não
 * há FormData nenhum. A ordem é que decide.
 *
 * A LIÇÃO INVERTE A REGRA QUE SEGUÍAMOS. "Não escrever o `Content-Type` à
 * mão" é necessário, mas **não é suficiente**: omitir não limpa nada, deixa
 * entrar a predefinição da instância. É preciso ANULÁ-LO.
 *
 * PORQUE É UM INTERCEPTOR E NÃO UMA CORRECÇÃO EM CADA FUNÇÃO: eram três as
 * funções partidas (`uploadProcessS3File`, `aiAnalyzeS3Documents`,
 * `uploadEmailAttachment`) e nenhuma delas parecia errada — a que estava
 * "certa" era a que omitia o cabeçalho. Uma regra que depende de cada autor
 * se lembrar dela já falhou três vezes; num ponto único não há onde falhar.
 */

/** `true` se o corpo do pedido é um `FormData`. */
export function ehFormData(data) {
  return typeof FormData !== "undefined" && data instanceof FormData;
}

/**
 * Interceptor de pedido: anula o `Content-Type` quando o corpo é FormData.
 *
 * Anular (`undefined`) não é o mesmo que não escrever: remove o cabeçalho
 * do pedido, predefinição da instância incluída, e deixa o Axios/browser
 * gerar `multipart/form-data; boundary=…`. Um pedido que não leve FormData
 * passa por aqui sem ser tocado.
 */
export function normalizarCabecalhosDeFormData(config) {
  if (!config || !ehFormData(config.data)) return config;

  if (!config.headers) return config;

  // Dois ramos porque há duas formas, e ter as duas em sequência era
  // redundância a fingir de defesa: uma mutação que apagasse os `delete`
  // não partia teste nenhum, porque o `setContentType` já tinha feito o
  // trabalho. Um `else` torna cada ramo alcançável — e testável.
  if (typeof config.headers.setContentType === "function") {
    // `AxiosHeaders` (o que existe em produção): API documentada, trata a
    // insensibilidade a maiúsculas por nós.
    config.headers.setContentType(null);
  } else {
    // Objecto simples: quem escreveu o cabeçalho pode tê-lo escrito de
    // qualquer das formas, e o HTTP não distingue maiúsculas.
    for (const chave of Object.keys(config.headers)) {
      if (chave.toLowerCase() === "content-type") delete config.headers[chave];
    }
  }
  return config;
}
