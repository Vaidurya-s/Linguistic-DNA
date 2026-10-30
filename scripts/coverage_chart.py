"""Render docs/media/coverage-by-language.svg: words per configured language, open seed vs
research database (read-only queries through psql).

    python3 scripts/coverage_chart.py data/config/languages.csv docs/media/coverage-by-language.svg lsg_public
"""
import csv, subprocess, sys, html

def q(db, sql):
    out = subprocess.run(["psql", "-h", "localhost", "-U", "postgres", "-d", db, "-At", "-F", "\t", "-c", sql],
                         check=True, capture_output=True, text=True).stdout
    return [l.split("\t") for l in out.strip().splitlines() if l]

PUBDB = sys.argv[3] if len(sys.argv) > 3 else "lsg_public"
SQL = "select l.language_id, count(*) from lexeme l join language g on g.id = l.language_id where g.is_enabled group by 1"
langs = list(csv.DictReader(open(sys.argv[1])))
pub = {k: int(v) for k, v in q(PUBDB, SQL)}
res = {k: int(v) for k, v in q("lsg", SQL)}
groups = [("Indo-Aryan", lambda l: l["role"] == "modern" and l["group"] == "Indo-Aryan"),
          ("Dravidian", lambda l: l["role"] == "modern" and l["group"] == "Dravidian"),
          ("Sino-Tibetan", lambda l: l["role"] == "modern" and l["group"] == "Sino-Tibetan"),
          ("Historical and reference", lambda l: l["role"] != "modern")]
short = {"Old Indo-Aryan (CDIAL headwords)": "Old Indo-Aryan (CDIAL)"}
rows = []
for g, f in groups:
    ls = sorted([l for l in langs if f(l)], key=lambda l: -res.get(l["id"], 0))
    rows.append(("group", g, None, None))
    for l in ls:
        rows.append(("lang", short.get(l["name"], l["name"]), pub.get(l["id"], 0), res.get(l["id"], 0)))

W, LBL, PADR = 880, 190, 150
ROW, GH, TOP = 22, 30, 92
plot = W - LBL - PADR
vals = sorted((max(r[2], r[3]) for r in rows if r[0] == "lang"), reverse=True)
mx = vals[1] if vals[0] > 2 * vals[1] else vals[0]  # an outlier bar is drawn broken
step = next(st for st in (1000, 2000, 2500, 5000, 10000, 20000, 25000, 50000, 100000, 200000, 250000) if mx / st <= 5)
nt = -(-mx // step)
mx = nt * step
H = TOP + sum(ROW if r[0] == "lang" else GH for r in rows) + 34
o = []
o.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" role="img" aria-labelledby="t d">')
o.append('<title id="t">Words per language: open public seed vs research database</title>')
o.append('<desc id="d">Horizontal bars per configured language, grouped by family. ' + html.escape("; ".join(f"{r[1]}: open {r[2]}, research {r[3]}" for r in rows if r[0] == "lang")) + '</desc>')
o.append('''<style>
.bg{fill:#fcfcfb}.t1{fill:#0b0b0b}.t2{fill:#52514e}.grid{stroke:#e4e3df}.open{fill:#2a78d6}.res{fill:#eb6834}
@media (prefers-color-scheme: dark){.bg{fill:#1a1a19}.t1{fill:#f0efec}.t2{fill:#c3c2b7}.grid{stroke:#3a3936}.open{fill:#3987e5}.res{fill:#d95926}}
</style>''')
o.append(f'<rect class="bg" width="{W}" height="{H}" rx="10"/>')
o.append(f'<text class="t1" x="20" y="32" font-size="17" font-weight="600">Words per language</text>')
o.append(f'<rect class="open" x="20" y="50" width="12" height="12" rx="2"/><text class="t2" x="38" y="60" font-size="13">Open public seed</text>')
o.append(f'<rect class="res" x="170" y="50" width="12" height="12" rx="2"/><text class="t2" x="188" y="60" font-size="13">Research database (open + research-use sources)</text>')
o.append(f'<text class="t2" x="{W-20}" y="60" font-size="12" text-anchor="end">labels: open / research</text>')
y = TOP
# grid
body_top = TOP
for i in range(0, nt + 1):
    v = step * i
    x = LBL + plot * i / nt
    o.append(f'<line class="grid" x1="{x:.1f}" x2="{x:.1f}" y1="{body_top-8}" y2="{H-30}" stroke-width="1"/>')
    o.append(f'<text class="t2" x="{x:.1f}" y="{H-14}" font-size="11" text-anchor="middle">{int(v):,}</text>')
for kind, name, p, r in rows:
    if kind == "group":
        o.append(f'<text class="t1" x="20" y="{y+20}" font-size="13" font-weight="600">{html.escape(name)}</text>')
        y += GH
        continue
    o.append(f'<text class="t2" x="{LBL-10}" y="{y+14}" font-size="12" text-anchor="end">{html.escape(name)}</text>')
    brk = max(r, p) > mx
    wr = max(plot * min(r, mx * 1.06) / mx, 2 if r else 0); wp = max(plot * min(p, mx * 1.06) / mx, 2 if p else 0)
    o.append(f'<rect class="res" x="{LBL}" y="{y+3}" width="{wr:.1f}" height="8" rx="2"><title>{html.escape(name)}: {r:,} words (research database)</title></rect>')
    o.append(f'<rect class="open" x="{LBL}" y="{y+12}" width="{wp:.1f}" height="6" rx="2"><title>{html.escape(name)}: {p:,} words (open seed)</title></rect>')
    if brk:
        bx = LBL + plot * 1.0 + 6
        o.append(f'<path class="bg" d="M{bx:.1f} {y+1} l6 0 l-4 19 l-6 0 z"/>')
    o.append(f'<text class="t2" x="{LBL+max(wr,wp)+6:.1f}" y="{y+15}" font-size="11">{p:,} / {r:,}</text>')
    y += ROW
broken = [r[1] for r in rows if r[0] == "lang" and max(r[2], r[3]) > mx]
if broken:
    o.append(f'<text class="t2" x="20" y="{H-14}" font-size="11">Bars cut at the break: {", ".join(broken)}</text>')
o.append('</svg>')
open(sys.argv[2], "w").write("\n".join(o) + "\n")
print("ok", H, mx)
