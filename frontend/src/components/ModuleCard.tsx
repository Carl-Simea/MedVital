import { MODULE_LABELS } from "../domain/presentation";
import type { ModuleId } from "../domain/types";

export function ModuleCard({ module, count }: { module: ModuleId; count: number }) {
  const { title, blurb } = MODULE_LABELS[module];
  return (
    <article
      data-module={module}
      className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
    >
      <h2 className="text-base font-semibold text-slate-900">{title}</h2>
      <p className="mt-1 text-sm text-slate-600">{blurb}</p>
      <p className="mt-3 text-xs text-slate-500">
        {count} stored observation{count === 1 ? "" : "s"}
      </p>
    </article>
  );
}
