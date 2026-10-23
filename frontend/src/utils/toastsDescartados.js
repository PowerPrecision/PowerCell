/**
 * Toasts que o UTILIZADOR descartou — e que por isso não podem voltar.
 *
 * O PROBLEMA. O `TasksContext` mostra um toast «a carregar» por tarefa e chama `toast.loading(…, {id})`
 * a CADA evento de progresso e a cada poll. Com o Sonner, um `id` que já existe actualiza-se; um `id`
 * que o utilizador acabou de fechar no X NÃO existe — logo a chamada seguinte CRIA outro toast. O
 * utilizador fechava o aviso e ele reaparecia segundos depois (ou ao voltar a uma página, quando o
 * evento seguinte chegava). Pior: o toast de CONCLUSÃO, ao fechar-se, não confirmava a tarefa no
 * servidor, pelo que um recarregamento da página o voltava a mostrar.
 *
 * A REGRA. Um id que o utilizador fechou fica registado e nenhuma actualização o recria. O registo
 * sobrevive a um recarregamento (`sessionStorage`, opcional: sem ele, o comportamento é o do tempo de
 * vida da página). É preciso distinguir quem fechou: o Sonner chama `onDismiss` tanto no X como em
 * `toast.dismiss(id)`, e os fechos que o PRÓPRIO código faz (o tecto de cinco toasts, o limite do
 * toast de sincronização) não são uma escolha do utilizador — marcá-los como descartados fazia a
 * tarefa desaparecer para sempre por causa de um tecto de ecrã.
 */
const CHAVE = "powercell.toasts.descartados";
const TECTO = 200;

function lerDoArmazenamento(armazenamento) {
  try {
    const bruto = armazenamento?.getItem(CHAVE);
    const lista = bruto ? JSON.parse(bruto) : [];
    return Array.isArray(lista) ? lista.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function escreverNoArmazenamento(armazenamento, ids) {
  try {
    armazenamento?.setItem(CHAVE, JSON.stringify(ids.slice(-TECTO)));
  } catch {
    /* modo privado, quota cheia, bloqueado: o registo vale só para esta página */
  }
}

/** O `sessionStorage`, ou `null`: só ACEDER-lhe já lança (`SecurityError`) com os dados do site bloqueados. */
function armazenamentoDaSessao() {
  try {
    return typeof window !== "undefined" ? window.sessionStorage : null;
  } catch {
    return null;
  }
}

/**
 * @param {Storage|null} [armazenamento] por omissão `sessionStorage` (se existir e estiver acessível).
 */
export function criarRegistoDeToastsDescartados(armazenamento = armazenamentoDaSessao()) {
  let descartados = lerDoArmazenamento(armazenamento);
  const nossos = new Set();

  return {
    /** O utilizador fechou este toast: nenhuma actualização o recria. */
    marcarDescartado(id) {
      if (!id || descartados.includes(id)) return;
      descartados = [...descartados, id].slice(-TECTO);
      escreverNoArmazenamento(armazenamento, descartados);
    },
    foiDescartado(id) {
      return descartados.includes(id);
    },
    /** Uma NOVA situação da tarefa (ex.: terminou) merece um aviso novo: o descarte anterior não a cobre. */
    esquecerDescarte(id) {
      if (!descartados.includes(id)) return;
      descartados = descartados.filter((x) => x !== id);
      escreverNoArmazenamento(armazenamento, descartados);
    },
    /** O código vai fechar este toast (tecto, limite de tempo, cancelamento): não é uma escolha do utilizador. */
    prepararFechoNosso(id) {
      nossos.add(id);
    },
    /**
     * Chamada pelo `onDismiss` do toast. Devolve `"nosso"` se o fecho foi do código (e esquece-o:
     * só vale uma vez) ou `"utilizador"` se foi o X / o gesto de fechar — e, nesse caso, regista-o.
     */
    aoFechar(id) {
      if (nossos.delete(id)) return "nosso";
      this.marcarDescartado(id);
      return "utilizador";
    },
    /** O toast vai ser (re)criado: um fecho nosso que nunca chegou não pode contar para o próximo. */
    aoCriar(id) {
      nossos.delete(id);
    },
  };
}
