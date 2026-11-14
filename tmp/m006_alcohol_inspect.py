from pathlib import Path
import re, json, hashlib, sqlite3

ROOT = Path(__file__).resolve().parents[1]
GAME = Path('F:/eratw')
s = (GAME / 'ERB/コマンド関連/COMF/日常系/酒関連F.ERB').read_text(encoding='utf-8-sig')
rows = []
for n, body in re.findall(r'^@F酒データ(\d+)\([^\n]*\)\s*\n(.*?)(?=^@|\Z)', s, re.M | re.S):
    name = re.search(r'^CASE "名前"\s*\n\s*RETURNF "([^"]+)"', body, re.M)
    alc = re.search(r'^CASE "酒気増加量"\s*\n(.*?)(?=^CASE |^ENDSELECT)', body, re.M | re.S)
    rows.append({'id': int(n), 'name': name[1] if name else '', 'alcohol': alc[1].strip() if alc else ''})
items = {}
for line in (GAME / 'CSV/Item.csv').read_text(encoding='utf-8-sig').splitlines():
    fields = line.split(',')
    if len(fields) > 1 and fields[0].isdigit():
        items[fields[1]] = int(fields[0])
valid = []
for row in rows:
    row['item'] = items.get(row['name'], -1)
    if row['alcohol'] and row['item'] >= 0:
        valid.append(row)
report = {'definitions': rows, 'valid': valid}
(ROOT / 'tmp/m006_alcohol_catalog_static.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'functions': len(rows), 'max_id': max(r['id'] for r in rows), 'catalog_count': len(valid), 'catalog': [(r['id'], r['item'], r['name']) for r in valid], 'alcohol_bodies': sorted(set(r['alcohol'] for r in valid))}, ensure_ascii=True))
