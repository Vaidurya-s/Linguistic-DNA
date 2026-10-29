"""Per-language coverage of a Jambu CLDF snapshot.

Usage: python scripts/jambu_coverage.py data/raw/jambu/cldf/forms.csv data/raw/jambu/cldf/form_concepts.csv
"""
import csv, sys, collections, json
csv.field_size_limit(10**9)
forms, fc = sys.argv[1], sys.argv[2]
T = {'A':'Assamese','B':'Bengali','G':'Gujarati','H':'Hindi-Urdu','M':'Marathi','Or':'Odia','P':'Punjabi',
     'Tamil':'Tamil','Telugu':'Telugu','Kannada':'Kannada','Malayalam':'Malayalam',
     'Sk':'Sanskrit','IA':'Old Indo-Aryan','Pa':'Pali','Pk':'Prakrit','Ap':'Apabhramsha','As':'Ashokan Prakrit','jmh':'Jaina Maharastri','jmag':'Jaina Magadhi'}
st = {k: collections.Counter() for k in T}
src = {k: collections.Counter() for k in T}
status = collections.Counter(); langs = collections.Counter(); ids = {}
for r in csv.DictReader(open(forms, encoding='utf-8')):
    langs[r['Language_ID']] += 1
    status[r['Status']] += 1
    k = r['Language_ID']
    if k not in T: continue
    ids[r['ID']] = k
    c = st[k]; c['forms'] += 1
    if r['Status']: c['status:'+r['Status']] += 1
    if r['Redirect']: c['redirect'] += 1
    if r['Gloss']: c['gloss'] += 1
    if r['Native']: c['native_script'] += 1
    if r['Phonemic']: c['phonemic'] += 1
    if r['Cognateset']: c['cognateset'] += 1
    if r['Form'].startswith('*'): c['starred'] += 1
    for s in r['Source'].split(';'):
        src[k][s.split('[')[0].strip()] += 1
concepts = collections.defaultdict(set)
for r in csv.DictReader(open(fc, encoding='utf-8')):
    k = ids.get(r['Form_ID'])
    if k: concepts[k].add(r['Concept_ID'])
out = {}
for k, n in T.items():
    out[k] = dict(name=n, **st[k], concepts=len(concepts[k]), top_sources=src[k].most_common(8))
print(json.dumps(dict(languages=out, status=status.most_common(), total_forms=sum(langs.values()),
                      top_langs=langs.most_common(15)), ensure_ascii=False, indent=1))
