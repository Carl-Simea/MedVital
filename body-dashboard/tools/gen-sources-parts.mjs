// Generates docs/SOURCES-parts.md from public/parts.mjs. Run: node tools/gen-sources-parts.mjs
import { PARTS, SRC, INDICATORS } from '../public/parts.mjs';
import { writeFileSync } from 'node:fs';
const used = {};
for (const [id, p] of Object.entries(PARTS)) for (const x of [...p.facts, ...p.helps]) (used[x.s] ||= new Set()).add(id);
let md = `# Sources behind the part cards (generated, do not edit)\n\nGenerated from \`public/parts.mjs\` by \`tools/gen-sources-parts.mjs\`. Every fact and countermeasure on a part card cites one of these.\n\n## Sources\n\n| Key | Kind | Title | Used by |\n|---|---|---|---|\n`;
for (const k of Object.keys(used).sort()) md += `| ${k} | ${SRC[k].kind} | [${SRC[k].title.replace(/\|/g, '/')}](${SRC[k].url}) | ${[...used[k]].join(', ')} |\n`;
md += `\n## Indicators and whether they can be measured in flight\n\n| Key | Label | How | In flight |\n|---|---|---|---|\n`;
for (const [k, i] of Object.entries(INDICATORS)) md += `| ${k} | ${i.label} | ${i.how} | ${i.flight ? 'yes' : 'no'} |\n`;
md += `\n## Parts without a verified spaceflight fact (shown as "Gap" in the app)\n\n`;
for (const [id, p] of Object.entries(PARTS)) if (p.gap) md += `- ${id}: ${p.gap}\n`;
md += `\n## How to read a rule's basis\n\n- verified: the number or statement is in the cited source.\n- reference: compared with a verified NASA reference value (for example mean bone loss per month); the cut-offs around it are a convention.\n- convention: general clinical convention (for example WHO anemia cut-off, resting heart-rate limits, 80 % of the radiation limit). Not NASA-specific and not verified here.\n- model: model output, not a measurement.\n\nKnown weak points: spleen to anemia link and part descriptions (\`does\`) are textbook statements; the liver and gut evidence is animal or press-based; urine volume and calcium cut-offs, back-pain cut-offs and the sleep-hours cut-offs are conventions.\n`;
writeFileSync(new URL('../docs/SOURCES-parts.md', import.meta.url), md);
console.log('written', Object.keys(used).length, 'sources');
