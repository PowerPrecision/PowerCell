import { toast } from "sonner";

/**
 * Kanban Constants
 * 
 * Constantes de cores e configurações para o Kanban Board.
 * Extraídas do monolito KanbanBoard.js para reutilização.
 */

export const statusColors = {
  yellow: "bg-yellow-100 border-yellow-300 text-yellow-900 dark:bg-yellow-900/40 dark:border-yellow-700 dark:text-yellow-100",
  blue: "bg-blue-100 border-blue-300 dark:bg-blue-900/40 dark:border-blue-700",
  purple: "bg-purple-100 border-purple-300 dark:bg-purple-900/40 dark:border-purple-700",
  orange: "bg-orange-100 border-orange-300 dark:bg-orange-900/40 dark:border-orange-700",
  green: "bg-green-100 border-green-300 dark:bg-green-900/40 dark:border-green-700",
  red: "bg-red-100 border-red-300 dark:bg-red-900/40 dark:border-red-700",
};

// Header backgrounds usam tons mais escuros para garantir contraste AA
// (>= 4.5:1) com o texto branco dos cabeçalhos das colunas.
export const statusHeaderColors = {
  yellow: "bg-amber-700",
  blue: "bg-blue-600",
  purple: "bg-purple-600",
  orange: "bg-orange-700",
  green: "bg-green-700",
  red: "bg-red-600",
};

/**
 * Função para abrir cliente de email com dados preenchidos
 */
export const openEmailClient = (email, clientName) => {
  if (!email) {
    toast.error("Cliente não tem email registado");
    return;
  }
  
  const subject = encodeURIComponent(`Processo de Crédito - ${clientName}`);
  const body = encodeURIComponent(`Olá ${clientName},\n\nEsperamos que esteja tudo bem.\n\n`);
  
  window.open(`mailto:${email}?subject=${subject}&body=${body}`, '_blank');
};
