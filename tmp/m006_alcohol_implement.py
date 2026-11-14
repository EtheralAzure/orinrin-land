"""One-task, guarded edits. Only writes inside this project."""
from pathlib import Path
import hashlib, json, re

ROOT = Path(__file__).resolve().parents[1]
FILES = ['M_KOJO_K36_3_DIM变量用.ERH', 'M_KOJO_K36_3_工具函数.ERB',
         'M_KOJO_K36_3_自定义机制_SOURCE相关.ERB', 'M_KOJO_K36_3_自定义机制_指令.ERB']
raw = {name: (ROOT / name).read_bytes() for name in FILES}
baseline = ROOT / 'tmp/m006_alcohol_before'
baseline.mkdir(exist_ok=False)
for name, data in raw.items():
    (baseline / (name + '.snapshot')).write_bytes(data)
texts = {name: data.decode('utf-8-sig').replace('\r\n', '\n') for name, data in raw.items()}

def replace(name, old, new):
    assert texts[name].count(old) == 1, (name, old[:100])
    texts[name] = texts[name].replace(old, new)

def function(description, name, decl, body):
    return (';==================================================\n;' + description +
            '\n;==================================================\n@' + name +
            '\n\t#LOCALSIZE 1\n\t#LOCALSSIZE 1\n' + decl + body + '\n\n')

dim, tool, source, ui = FILES
replace(dim, ';1201 ~ 1250 日常系COM（非涩涩都算）', ';1201 ~ 1246 日常系COM（非涩涩都算）；1247～1249保留')
replace(dim, ';1251 - 喝过酒的种类的记录\n;--------------------------------------------------\n#DIM CONST AME36_ALCOHOL_TYPE = 1251',
''' ;1250 ~ 1251 - 饮酒历史，每槽使用bit0～62，按本体酒数据ID自动寻址
;酒数据ID1～126分别映射到两块；物品编号须先转换，不保存名称或次数
;--------------------------------------------------
#DIM CONST AME36_ALCOHOL_HISTORY_BEGIN = 1250
#DIM CONST AME36_ALCOHOL_HISTORY_BLOCKS = 2
#DIM CONST AME36_ALCOHOL_HISTORY_BITS = 63
#DIM CONST AME36_ALCOHOL_HISTORY_FIRST_ID = 1
#DIM CONST AME36_ALCOHOL_HISTORY_LAST_ID = AME36_ALCOHOL_HISTORY_FIRST_ID + AME36_ALCOHOL_HISTORY_BLOCKS * AME36_ALCOHOL_HISTORY_BITS - 1'''.lstrip())
replace(tool, ';酒共31种', ';按饮酒历史计数，原贡献公式及阶段封顶保持')
replace(tool, 'LOCAL = AME36_BINARY_SUM(CFLAG:AME36_ALCOHOL_TYPE)', 'LOCAL = AME36_ALCOHOL_HISTORY_COUNT(TARGET)')

catalog = function('将本体酒数据ID对应到可饮用物品，非法或非酒返回-1\n;目录与可饮用判定沿用本体接口，不使用物品持有数作为收集条件',
    'AME36_ALCOHOL_ITEM_INDEX(ALCOHOL_ID)', '\t#FUNCTION\n\t#DIM ALCOHOL_ID\n',
'''\tSIF !INRANGE(ALCOHOL_ID, AME36_ALCOHOL_HISTORY_FIRST_ID, AME36_ALCOHOL_HISTORY_LAST_ID)
\t\tRETURNF -1
\tLOCALS '= ALC_NAME(ALCOHOL_ID)
\tSIF LOCALS == ""
\t\tRETURNF -1
\tLOCAL = GETNUM(ITEM, LOCALS)
\tSIF LOCAL < 0
\t\tRETURNF -1
\tSIF ALC_ID(ITEMNAME:LOCAL) != ALCOHOL_ID
\t\tRETURNF -1
\tSIF !IS_ALC(LOCAL)
\t\tRETURNF -1
\tRETURNF LOCAL''')

helpers = catalog
for op in ['RECORD', 'HAS']:
    record = op == 'RECORD'
    fail = '-1' if record else '0'
    body = f'''\tSIF CHARA < 0 || CHARA >= CHARANUM
\t\tRETURNF {fail}
\tSIF NO:CHARA != 36
\t\tRETURNF {fail}
\tSIF !INRANGE(ALCOHOL_ID, AME36_ALCOHOL_HISTORY_FIRST_ID, AME36_ALCOHOL_HISTORY_LAST_ID)
\t\tRETURNF {fail}
\tLOCAL = ALCOHOL_ID - AME36_ALCOHOL_HISTORY_FIRST_ID
\t;--------------------------------------------------
\t;动态属性索引：饮酒历史1250～1251，位号始终为0～62
\t;--------------------------------------------------
'''
    address = 'CFLAG:CHARA:(AME36_ALCOHOL_HISTORY_BEGIN + LOCAL / AME36_ALCOHOL_HISTORY_BITS), LOCAL % AME36_ALCOHOL_HISTORY_BITS'
    if record:
        body += f'''\tSIF GETBIT({address})
\t\tRETURNF 0
\t;--------------------------------------------------
\t;动态属性索引：饮酒历史1250～1251，不使用符号位
\t;--------------------------------------------------
\tSETBIT {address}
\tRETURNF 1'''
    else:
        body += f'\tRETURNF GETBIT({address})'
    desc = ('记录已确认实际喝过的酒数据ID，1为新增、0为重复、-1为输入无效\n;可饮用目录与成功饮用前提由入口保证，不把物品编号直接写入' if record else
            '按本体酒数据ID读取饮酒历史，不查询目录或改变TARGET')
    helpers += function(desc, f'AME36_ALCOHOL_HISTORY_{op}(CHARA, ALCOHOL_ID)',
                        '\t#FUNCTION\n\t#DIM CHARA\n\t#DIM ALCOHOL_ID\n', body)
helpers += function('统计指定酒数据ID区间的饮酒历史，不查询数据库或重新判定饮用资格',
    'AME36_ALCOHOL_HISTORY_COUNT(CHARA, FIRST_ID = AME36_ALCOHOL_HISTORY_FIRST_ID, LAST_ID = AME36_ALCOHOL_HISTORY_LAST_ID)',
    '\t#FUNCTION\n\t#DIM CHARA\n\t#DIM FIRST_ID\n\t#DIM LAST_ID\n\t#DIM DYNAMIC ALCOHOL_ID\n',
'''\tSIF CHARA < 0 || CHARA >= CHARANUM
\t\tRETURNF 0
\tSIF NO:CHARA != 36
\t\tRETURNF 0
\tFIRST_ID = MAX(FIRST_ID, AME36_ALCOHOL_HISTORY_FIRST_ID)
\tLAST_ID = MIN(LAST_ID, AME36_ALCOHOL_HISTORY_LAST_ID)
\tSIF FIRST_ID > LAST_ID
\t\tRETURNF 0
\tLOCAL = 0
\tFOR ALCOHOL_ID, FIRST_ID, LAST_ID + 1
\t\tLOCAL += AME36_ALCOHOL_HISTORY_HAS(CHARA, ALCOHOL_ID)
\tNEXT
\tRETURNF LOCAL''')
helpers += function('在COM332饮用分支登记历史，负分支表示拒绝或中止，不记录\n;ITEM_ID为本体物品编号，转换后才按酒数据ID写入',
    'AME36_ALCOHOL_RECORD_COM332(CHARA, ITEM_ID, BRANCH)',
    '\t#FUNCTION\n\t#DIM CHARA\n\t#DIM ITEM_ID\n\t#DIM BRANCH\n',
'''\tSIF CHARA < 0 || CHARA >= CHARANUM
\t\tRETURNF -1
\tSIF NO:CHARA != 36
\t\tRETURNF -1
\tSIF !GROUPMATCH(BRANCH, 0, 1)
\t\tRETURNF -1
\tSIF ITEM_ID < 0 || ITEM_ID >= VARSIZE("ITEM")
\t\tRETURNF -1
\tSIF !IS_ALC(ITEM_ID)
\t\tRETURNF -1
\tLOCAL = ALC_ID(ITEMNAME:ITEM_ID)
\tRETURNF AME36_ALCOHOL_HISTORY_RECORD(CHARA, LOCAL)''')
anchor = ';==================================================\n;对回忆值的料理经历部分计算的包装'
replace(tool, anchor, helpers + anchor)
replace(tool, ';测试用，提高回忆记录并填满当前目录的料理历史', ';测试用，提高COM回忆记录并填满当前目录的酒与料理历史')
replace(tool, 'FOR LOCAL, 1201, AME36_DISH_HISTORY_BEGIN', 'FOR LOCAL, 1201, AME36_ALCOHOL_HISTORY_BEGIN')
replace(tool, ';属性索引：测试工具访问1201～1251，料理历史另按目录记录', ';属性索引：测试工具访问1201～1249，酒与料理历史另按目录记录')
replace(tool, '\tCFLAG:AME36_RECOLLECTION_303 = 0\n', '''\tCFLAG:AME36_RECOLLECTION_303 = 0
\t;--------------------------------------------------
\t;酒按本体可饮用目录记录，不将普通整数当作历史位图写入
\t;--------------------------------------------------
\tFOR LOCAL, AME36_ALCOHOL_HISTORY_FIRST_ID, AME36_ALCOHOL_HISTORY_LAST_ID + 1
\t\tSIF AME36_ALCOHOL_ITEM_INDEX(LOCAL) < 0
\t\t\tCONTINUE
\t\tCALLF AME36_ALCOHOL_HISTORY_RECORD, TARGET, LOCAL
\tNEXT
''')
old = re.search(r'            SELECTCASE TFLAG:COM_DETAIL_AMER\n.*?            ENDSELECT', texts[source], re.S)[0]
assert 'AME36_ALCOHOL_TYPE' in old
replace(source, ';喝过酒种类的记录', ';只登记实际饮用的分支，物品编号在接口内转换为酒数据ID')
replace(source, old, '            CALLF AME36_ALCOHOL_RECORD_COM332, TARGET, TFLAG:COM_DETAIL_AMER, TFLAG:COM_BRANCH_AMER')
old = re.search(r'    \{\n    #DIMS ALCOHOL_NAMES.*?\n    \}\n', texts[ui], re.S)[0]
replace(ui, old, '')
old = re.search(r'            FOR LOCAL, 0, 34\n.*?            PRINTL\n            PRINTW', texts[ui], re.S)[0]
replace(ui, old, '            CALL AME36_ALCOHOL_HISTORY_PRINT(TARGET)\n            PRINTW')
display = function('按本体可饮用目录显示酒名，标记按酒数据ID查询\n;沿用本体ITEMNAME_TR翻译，不维护额外赋名表',
    'AME36_ALCOHOL_HISTORY_PRINT(CHARA)', '\t#DIM CHARA\n\t#DIM DYNAMIC ALCOHOL_ID\n\t#DIM DYNAMIC ITEM_ID\n',
'''\tSIF CHARA < 0 || CHARA >= CHARANUM
\t\tRETURN 0
\tSIF NO:CHARA != 36
\t\tRETURN 0
\tLOCAL = 0
\tFOR ALCOHOL_ID, AME36_ALCOHOL_HISTORY_FIRST_ID, AME36_ALCOHOL_HISTORY_LAST_ID + 1
\t\tITEM_ID = AME36_ALCOHOL_ITEM_INDEX(ALCOHOL_ID)
\t\tSIF ITEM_ID < 0
\t\t\tCONTINUE
\t\tLOCALS '= ITEMNAME_TR(ITEM_ID)
\t\tSIF LOCALS == ""
\t\t\tCONTINUE
\t\tSIF AME36_ALCOHOL_HISTORY_HAS(CHARA, ALCOHOL_ID)
\t\t\tSETCOLOR C_GREEN
\t\tSTRLENFORM %LOCALS%
\t\tPRINTFORM %LOCALS%%"　" * MAX(8 - RESULT / 2, 1)%
\t\tRESETCOLOR
\t\tLOCAL += 1
\t\tSIF LOCAL % 3 == 0
\t\t\tPRINTL
\tNEXT
\tSIF LOCAL % 3
\t\tPRINTL
\tRETURN LOCAL''').replace('\t', '    ')
replace(ui, ';==================================================\n;按本体目录显示料理', display + ';==================================================\n;按本体目录显示料理')

for name, text in texts.items():
    data = (b'\xef\xbb\xbf' if raw[name].startswith(b'\xef\xbb\xbf') else b'') + text.replace('\n', '\r\n').encode('utf-8')
    assert data != raw[name]
    (ROOT / name).write_bytes(data)
(baseline / 'manifest.json').write_text(json.dumps({name: hashlib.sha256(data).hexdigest() for name, data in raw.items()}, indent=2), encoding='utf-8')
print('Updated four production files; original bytes saved in tmp/m006_alcohol_before.')
