/**
 * PremiumBadge — «Módulo Premium»: destaque de uma novidade de um módulo que
 * nem todas as empresas têm. Serve o upsell: quem ainda não tem a funcionalidade
 * vê-a anunciada e sabe que pode pedi-la.
 */
import { Crown } from "lucide-react";

import { Badge } from "../ui/badge";
import { cn } from "../../lib/utils";

export default function PremiumBadge({ className }) {
  return (
    <Badge
      variant="outline"
      data-testid="badge-premium"
      className={cn(
        "gap-1 border-amber-500/40 bg-amber-500/10 text-[10px] font-semibold text-amber-700 dark:text-amber-300",
        className,
      )}
    >
      <Crown className="h-3 w-3" aria-hidden="true" />
      Módulo Premium
    </Badge>
  );
}
