import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

here = Path(__file__).parent
bef = json.loads((here / 'quality_before.json').read_text())
aft = json.loads((here / 'quality_after.json').read_text())
mb = {m['rule_id']: m for m in bef['metrics']}
ma = {m['rule_id']: m for m in aft['metrics']}
rules = list(mb) + [r for r in ma if r not in mb]
YMIN, YMAX = 0.90, 1.10

def val(m):
    return None if m is None or m.get('value') is None else m['value']

x = list(range(len(rules)))
w = 0.38
fig, ax = plt.subplots(figsize=(12, 7.5))
for off, src, color, name in ((-w / 2, mb, '#1f77b4', 'Before curation'),
                              (w / 2, ma, '#ff7f0e', 'After curation (9610 curated rows)')):
    first = True
    for i, r in enumerate(rules):
        m = src.get(r)
        v = val(m)
        if v is None:
            ax.text(i + off, YMIN + 0.003, 'n/a', ha='center', va='bottom', fontsize=8, color='gray')
            continue
        ax.bar(i + off, v, w, color=color, label=name if first else None)
        first = False
        ax.text(i + off, v + 0.002, f"{m['numerator']}/{m['denominator']}  ({v:.3f})",
                ha='center', va='bottom', fontsize=8, rotation=90)
ax.axhline(0.95, color='red', linestyle='--', linewidth=1, label='Threshold 0.95 (timeliness, agreement)')
ax.set_xticks(x)
ax.set_xticklabels(rules, rotation=30, ha='right')
ax.set_ylim(YMIN, YMAX)
ax.set_ylabel('Metric value (numerator/denominator). Axis starts at 0.90')
ax.set_title('Lab 2 quality metrics: before vs after curation')
ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.17), ncol=3)
fig.text(0.01, 0.01,
         'Populations: before = winners W (9960) for REQUIRED/VALUE/REFINT/TIME; UNIQUE = key-eligible (10160); '
         'TIMELY = rows with event<=ingest<=AS_OF (denominator 9890 of W before, 9610 curated after);\nREF_* = reference sample (100 IDs).',
         fontsize=7.5, ha='left')
plt.tight_layout(rect=(0, 0.03, 1, 1))
plt.savefig(here / 'quality_chart.png', dpi=150)
print('saved quality_chart.png')
