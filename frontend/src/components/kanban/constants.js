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

export const statusHeaderColors = {
  yellow: "bg-yellow-500 text-yellow-900",
  blue: "bg-blue-500",
  purple: "bg-purple-500",
  orange: "bg-orange-500",
  green: "bg-green-500",
  red: "bg-red-500",
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
