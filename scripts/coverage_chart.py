"""Render docs/media/coverage-by-language.svg: words per language in the research database,
split into open-licensed and research-use sources (read-only queries through psql).

Three sections, each on its own scale: the steppe corridor (Slavic, Baltic, Iranian, Turkic,
Mongolic, Uralic and their proto-languages), the configured South Asian languages
(data/config/languages.csv), and the largest languages elsewhere.

    python3 scripts/coverage_chart.py data/config/languages.csv docs/media/coverage-by-language.svg [db]
"""
import csv, html, subprocess, sys, datetime

DB = sys.argv[3] if len(sys.argv) > 3 else "lsg"


def q(sql):
    out = subprocess.run(["psql", "-h", "localhost", "-U", "postgres", "-d", DB, "-At", "-F", "\t", "-c", sql],
                         check=True, capture_output=True, text=True).stdout
    return [l.split("\t") for l in out.strip().splitlines() if l]


COUNTS = {r[0]: (r[1], int(r[2]), int(r[3]), int(r[4])) for r in q("""
    with c as (select l.language_id,
                      count(*) filter (where a.decision <> 'RESEARCH USE') o,
                      count(*) filter (where a.decision = 'RESEARCH USE') r
               from lexeme l join dataset_audit a on a.id = l.dataset group by 1)
    select c.language_id, g.name, c.o, c.r, coalesce(s.linked_count, 0)
    from c join language g on g.id = c.language_id
    left join language_stats s on s.language_id = c.language_id""")}

STEPPE = ["gl-russ1263", "gl-ukra1253", "gl-bela1254", "gl-oldr1238", "wkt-cu", "wkt-sla-pro",
          "wkt-ine-bsl-pro", "gl-lith1251", "gl-latv1249", "wkt-ine-pro", "wkt-iir-pro", "wkt-ira-pro",
          "gl-west2369", "gl-aves1237", "gl-oldp1254", "gl-osse1243", "gl-sogd1245",
          "wkt-trk-pro", "gl-nucl1301", "gl-kaza1248", "gl-kirg1245", "gl-tata1255", "gl-bash1264",
          "gl-chuv1255", "gl-halh1238", "wkt-urj-pro", "gl-finn1318", "gl-hung1274", "gl-udmu1245",
          "gl-komi1268", "gl-erzy1239", "gl-east2328"]
configured = [r["id"] for r in csv.DictReader(open(sys.argv[1], encoding="utf-8"))]
taken = set(STEPPE) | set(configured)
elsewhere = [k for k, _ in sorted(COUNTS.items(), key=lambda kv: -(kv[1][1] + kv[1][2]))
             if k not in taken][:12]
short = {"Old Indo-Aryan (CDIAL headwords)": "Old Indo-Aryan (CDIAL)",
         "Old Persian (ca. 600-400 B.C.)": "Old Persian", "Western Farsi": "Persian (Western Farsi)"}


def section(title, ids, sort=True):
    langs = [(i, *COUNTS[i]) for i in ids if i in COUNTS]
    if sort:
        langs.sort(key=lambda x: -(x[2] + x[3]))
    return title, langs


SECTIONS = [section("Steppe corridor: Slavic, Baltic, Iranian, Turkic, Mongolic, Uralic and their ancestors", STEPPE),
            section("South Asia: the 25 configured languages", configured),
            section("Largest elsewhere", elsewhere)]

W, LBL, PADR = 900, 200, 190
ROW, GH, TOP = 21, 40, 96
plot = W - LBL - PADR
H = TOP + sum(GH + ROW * len(ls) for _, ls in SECTIONS) + 40
o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
     'font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" role="img" aria-labelledby="t d">',
     '<title id="t">Words per language in the research database, open-licensed and research-use sources</title>',
     '<desc id="d">' + html.escape("; ".join(
         f"{short.get(n, n)}: {o_ + r:,} words ({r:,} research-use), {ln:,} with links"
         for _, ls in SECTIONS for _, n, o_, r, ln in ls)) + '</desc>',
     '''<style>
.bg{fill:#fcfcfb}.t1{fill:#0b0b0b}.t2{fill:#52514e}.grid{stroke:#e4e3df}.open{fill:#2a78d6}.res{fill:#eb6834}
@media (prefers-color-scheme: dark){.bg{fill:#1a1a19}.t1{fill:#f0efec}.t2{fill:#c3c2b7}.grid{stroke:#3a3936}.open{fill:#3987e5}.res{fill:#d95926}}
</style>''',
     f'<rect class="bg" width="{W}" height="{H}" rx="10"/>',
     '<text class="t1" x="20" y="32" font-size="17" font-weight="600">Words per language, research database</text>',
     '<rect class="open" x="20" y="50" width="12" height="12" rx="2"/>'
     '<text class="t2" x="38" y="60" font-size="13">Open-licensed sources</text>',
     '<rect class="res" x="190" y="50" width="12" height="12" rx="2"/>'
     '<text class="t2" x="208" y="60" font-size="13">Research-use sources (cited, not redistributed)</text>',
     f'<text class="t2" x="20" y="80" font-size="11">Each section has its own scale. Labels: words · words with at least one documented link. '
     f'{datetime.date.today().isoformat()}.</text>']
y = TOP
for title, langs in SECTIONS:
    o.append(f'<text class="t1" x="20" y="{y + 22}" font-size="13" font-weight="600">{html.escape(title)}</text>')
    y += GH
    mx = max(a + b for _, _, a, b, _ in langs)
    for _, name, op, rs, linked in langs:
        name = short.get(name, name)
        wo = plot * op / mx
        wr = plot * rs / mx
        o.append(f'<text class="t2" x="{LBL - 10}" y="{y + 14}" font-size="12" text-anchor="end">{html.escape(name)}</text>')
        o.append(f'<rect class="open" x="{LBL}" y="{y + 4}" width="{max(wo, 1.5 if op else 0):.1f}" height="11" rx="2">'
                 f'<title>{html.escape(name)}: {op:,} words from open sources</title></rect>')
        if rs:
            o.append(f'<rect class="res" x="{LBL + wo:.1f}" y="{y + 4}" width="{max(wr, 1.5):.1f}" height="11" rx="2">'
                     f'<title>{html.escape(name)}: {rs:,} words from research-use sources</title></rect>')
        o.append(f'<text class="t2" x="{LBL + max(wo + wr, 2) + 6:.1f}" y="{y + 14}" font-size="11">'
                 f'{op + rs:,} · {linked:,} linked</text>')
        y += ROW
o.append(f'<text class="t2" x="20" y="{H - 16}" font-size="11">Generated by scripts/coverage_chart.py from read-only queries; '
         'the committed open seed is smaller (see the table in the README).</text>')
o.append('</svg>')
open(sys.argv[2], "w", encoding="utf-8").write("\n".join(o) + "\n")
print("ok", H, sum(len(ls) for _, ls in SECTIONS))
