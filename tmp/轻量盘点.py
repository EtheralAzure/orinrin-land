from pathlib import Path
import re, hashlib

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / '机制'
TEMPLATE = Path(r'F:\eratw\原版+前人整合等各种readme（口上模板及口上教程在内）\改造とかしてみたい人のためのあれこれ\口上関連\TW口上汉化精修模版(4.954-4.97X)')

def scan(path):
    lines = path.read_text(encoding='utf-8-sig').splitlines()
    functions = []
    current = None
    skipped = False
    for no, line in enumerate(lines, 1):
        s = line.strip()
        if s == '[SKIPSTART]': skipped = True
        if s.startswith('@'):
            current = {'name': re.split(r'[（(\s]', s[1:])[0], 'line': no, 'skip': skipped, 'body': []}
            functions.append(current)
        elif current and s and not s.startswith((';', '#', '[')):
            current['body'].append(s.split(';', 1)[0].strip())
        if s == '[SKIPEND]': skipped = False
    return lines, functions

def normal(body, template=False):
    s = '\n'.join(body)
    if template: s = s.replace('XXX', 'AME').replace('KX', 'K36')
    return re.sub(r'\s', '', s)

templates = {}
for p in TEMPLATE.glob('*.ERB'):
    for f in scan(p)[1]:
        key = f['name'].replace('XXX', 'AME').replace('KX', 'K36')
        templates.setdefault(key, []).append((p.name, f))

files = sorted([*ROOT.glob('*.ERB'), *ROOT.glob('*.ERH')])
all_code = []
parts = ['# 轻量盘点源码索引', '', '日期：2026-11-12。覆盖本口上根目录全部 8 个 ERB/ERH；仅静态盘点，未运行游戏。', '', '本索引记录所有标签、跳过标记、局部模板比较和 AME36 声明的词面使用位置。动态拼名、数字槽位访问及本体调用需在详细审查中核对；未发现词面引用不等于不可达。', '', '模板比较仅归一化 XXX/AME、KX/K36，去除注释、声明行和空白后比较函数体，不表示参数签名一致或行为等价。空体与固定返回值另行标出。SHA-256 用于定位本次源码快照。', '']
total = 0
for p in files:
    lines, funcs = scan(p)
    all_code += [(p.name, no, line.split(';',1)[0]) for no,line in enumerate(lines,1) if not line.lstrip().startswith(';')]
    raw = p.read_bytes()
    parts += ['## ' + p.name, '', f'- 行数：{len(lines)}；标签数：{len(funcs)}；UTF-8 可解码；BOM：{raw.startswith(bytes.fromhex("efbbbf"))}；CRLF：{raw.count(bytes.fromhex("0d0a"))}。', f'- SHA-256：`{hashlib.sha256(raw).hexdigest().upper()}`。', '']
    if funcs:
        parts += ['| 行 | 函数标签 | 结构特征 | 当前中文模板的比较线索 |', '| --- | --- | --- | --- |']
    for f in funcs:
        total += 1
        body = f['body']
        feature = 'SKIP 跳过区' if f['skip'] else ('空体' if not body else ('仅固定返回' if all(re.fullmatch(r'RETURNF?\s+-?\d+', x) for x in body) else '有代码/分支'))
        same = [(pn,tf) for pn,tf in templates.get(f['name'],[]) if normal(body)==normal(tf['body'],True)]
        ref = ('函数体归一化相同：' + '、'.join(f'{pn}:{tf["line"]}' for pn,tf in same)) if same else ('有同名归一化标签，函数体不同' if f['name'] in templates else '未匹配到同名归一化标签')
        parts.append(f'| {f["line"]} | `{f["name"]}` | {feature} | {ref} |')
    parts.append('')

parts += ['## AME36 声明与词面引用', '', '次数为去掉行注释后的词面出现次数，包含声明，不排除 SKIP 区；不等于实际执行次数。首次定义后的最多 5 个位置仅供追踪。', '', '| 声明行 | 名称 | 声明尾部 | 词面次数 | 非声明位置举例 |', '| --- | --- | --- | --- | --- |']
header = next(p for p in files if p.suffix.upper()=='.ERH')
for no,line in enumerate(scan(header)[0],1):
    m = re.search(r'^#DIMS?\s+(?:CONST\s+)?(AME36_\w+)(.*)',line)
    if not m: continue
    name,tail=m.groups()
    refs=[(pn,n) for pn,n,s in all_code if re.search(r'\b'+re.escape(name)+r'\b',s)]
    examples=[f'{pn}:{n}' for pn,n in refs if not (pn==header.name and n==no)][:5]
    parts.append(f'| {no} | `{name}` | `{tail.strip()}` | {len(refs)} | {"、".join(examples) or "未见词面引用，数字访问待查"} |')
(OUT/'轻量盘点源码索引.md').write_text('\n'.join(parts)+'\n',encoding='utf-8')
print(f'已索引 {len(files)} 个文件、{total} 个标签；未修改源文件。')
