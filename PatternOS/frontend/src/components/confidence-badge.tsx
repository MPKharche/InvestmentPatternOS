import { Badge } from "@/components/ui/badge";

export function ConfidenceBadge({ score }: { score: number }) {
  const color =
    score >= 85 ? "bg-green-500/20 text-green-400 border-green-500/30" :
    score >= 70 ? "bg-yellow-500/20 text-yellow-400 border-yellow-500/30" :
                  "bg-red-500/20 text-red-400 border-red-500/30";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold border ${color}`}>
      {score.toFixed(0)}%
    </span>
  );
}
