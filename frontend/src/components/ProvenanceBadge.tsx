import { ORIGIN_LABELS } from "../domain/presentation";
import type { DataOrigin } from "../domain/types";

const STYLES: Record<DataOrigin, string> = {
  simulated: "bg-amber-100 text-amber-900 ring-amber-300",
  measured: "bg-emerald-100 text-emerald-900 ring-emerald-300",
  modeled: "bg-sky-100 text-sky-900 ring-sky-300",
};

export function ProvenanceBadge({ origin }: { origin: DataOrigin }) {
  const { label, description } = ORIGIN_LABELS[origin];
  return (
    <span
      title={description}
      data-origin={origin}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${STYLES[origin]}`}
    >
      {label}
    </span>
  );
}
