from pathlib import Path
import re, collections, json, hashlib

ROOT=Path(__file__).resolve().parents[1]
ARRAYS='CFLAG TALENT DAY ABL BASE MAXBASE EXP PALAM SOURCE TCVAR TFLAG FLAG CSTR EX NOWEX JUEL GOTJUEL TIME STAIN EQUIP TEQUIP MARK UP DOWN CUP CDOWN LOSEBASE DOWNBASE MAXPALAM'.split()
PAT=re.compile(r'(?<![\w])('+ '|'.join(ARRAYS)+r'):',re.I)

def refs(text):
    for m in PAT.finditer(text):
        i=m.end(); parts=[]
        while True:
            start=i
            if i<len(text) and text[i]=='(':
                depth=1; i+=1
                while i<len(text) and depth:
                    if text[i]=='(':depth+=1
                    elif text[i]==')':depth-=1
                    i+=1
            elif i<len(text) and text[i]=='"':
                i+=1
                while i<len(text) and text[i]!='"':i+=1
                if i<len(text):i+=1
            else:
                k=re.match(r'[\w]+',text[i:])
                if not k:break
                i+=len(k.group())
            parts.append((start,i,text[start:i]))
            if i>=len(text) or text[i]!=':':break
            i+=1
        if parts:yield m.group(1).upper(),parts,m.start(),i

def inventory():
    report={}
    for p in sorted(ROOT.glob('*.ERB')):
        for no,line in enumerate(p.read_text(encoding='utf-8-sig').splitlines(),1):
            for arr,parts,_,_ in refs(line):
                token=parts[-1][2]
                if token.endswith('_AMER') or token.startswith('AME36_'):continue
                key=arr+':'+token
                item=report.setdefault(key,{'count':0,'active':0,'samples':[]})
                item['count']+=1
                item['active']+=not line.lstrip().startswith(';')
                if len(item['samples'])<4:item['samples'].append(f'{p.name}:{no}: {line.strip()}')
    out=ROOT/'tmp'/'属性索引盘点.json'
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    for k,v in sorted(report.items()):
        print(k,v['count'],v['active'])
    print('完整位置已存',out.name)

def load_defs():
    return json.loads((ROOT/'tmp/属性索引定义.json').read_text(encoding='utf-8'))

NEW={
 'CFLAG':{13:'DATE_EVENT_FLAGS_AMER',20:'BANQUET_PARTICIPATION_AMER',379:'VISIT_BLOCKED_AMER',998:'SCRIPT_SELECTOR_AMER'},
 'EXP':{22:'MASTURBATIONXP_AMER'},
 'FLAG':{9021:'HYPNOSIS_STRENGTH_AMER'},
 'PALAM':{10:'PALAM_OBEDIENCE_AMER',11:'PALAM_LUST_AMER',12:'PALAM_SUBJUGATION_AMER',13:'PALAM_LEARNING_AMER',14:'PALAM_SHAME_AMER',15:'PALAM_PAIN_AMER',16:'PALAM_FEAR_AMER',20:'PALAM_FAVOR_AMER',21:'PALAM_SUPERIORITY_AMER',30:'PALAM_RESENTMENT_AMER',31:'PALAM_DISCOMFORT_AMER',32:'PALAM_DEPRESSION_AMER',33:'PALAM_SLEEP_ASSAULT_AMER'},
 'TALENT':{4:'LEWD_AMER',142:'FLIRTATIOUS_AMER'},
 'EX':{70:'VIRGIN_LOSS_MARK_AMER'},
 'TFLAG':{100:'TRAIN_COMABLE_AMER',192:'KOJO_COM_RESULT_AMER',193:'COM_BRANCH_AMER',194:'COM_DETAIL_AMER',209:'PUBLIC_BATH_FLAGS_AMER',211:'OLD_HELL_SPRING_FLAGS_AMER'},
}

def parse_aliases(text):
    group=None; aliases={}; values={}
    for line in text.splitlines():
        m=re.match(r';('+ '|'.join(ARRAYS)+r')系',line)
        if m:group=m[1]
        m=re.match(r'#DIM CONST (\w+_AMER)\s*=\s*(\d+)\s*(?:;.*)?$',line)
        if m and group:
            name,value=m[1],int(m[2]); values[name]=value
            aliases.setdefault(group,{}).setdefault(value,name)
    return aliases,values

def snapshot():
    import base64
    data={p.name:base64.b64encode(p.read_bytes()).decode() for p in [*ROOT.glob('*.ERB'),*ROOT.glob('*.ERH')]}
    (ROOT/'tmp/属性索引整理前.json').write_text(json.dumps(data,indent=2),encoding='utf-8')

def transform():
    import base64
    snapshot_path=ROOT/'tmp/属性索引整理前.json'
    assert not snapshot_path.exists(),'本次迁移已留基线，禁止重放覆盖后续改动；请仅运行无参数盘点。'
    snapshot()
    baseline=json.loads(snapshot_path.read_text(encoding='utf-8'))
    defs=load_defs()
    header=next(ROOT.glob('*.ERH'))
    old=base64.b64decode(baseline[header.name]); text=old.decode('utf-8-sig')
    aliases,values=parse_aliases(text)
    additions=[';==================================================',';本口上内置属性数组索引别名（补充）',';数值以当前本体CSV/ALS定义核对；SOURCE与PALAM分别命名',';==================================================']
    for group,mapping in NEW.items():
        additions+=[';'+group+'系（补充）']
        reverse={n:s for s,n in defs.get(group,{}).items()}
        for value,name in mapping.items():
            assert name not in values,name
            assert value in reverse,(group,value)
            additions.append(f'#DIM CONST {name} = {value} ;{reverse[value]}')
            aliases.setdefault(group,{})[value]=name;values[name]=value
        additions.append('')
    # 新增别名插入自用CFLAG声明之前，保留原声明内容。
    anchor=';CFLAG别名，用于增加可读性'
    pos=text.index(anchor); pos=text.rfind(';※',0,pos)
    text=text[:pos]+'\r\n'.join(additions)+'\r\n'+text[pos:]
    bom=bytes.fromhex('efbbbf') if old.startswith(bytes.fromhex('efbbbf')) else b''
    pending_writes={header:bom+text.encode('utf-8')}
    aliases['MAXBASE']=aliases['BASE']
    comments=[]; changes=[]
    for p in sorted(ROOT.glob('*.ERB')):
        raw=base64.b64decode(baseline[p.name]); txt=raw.decode('utf-8-sig'); out=[]
        assert '\n' not in txt.replace('\r\n',''),p
        for no,line in enumerate(txt.splitlines(keepends=True),1):
            original=line
            # 无有效本体索引的纯注释占位，改为明确的文字说明。
            if '今日構ったフラグ' in line:
                line=line.replace('CFLAG:36:今日構ったフラグ= 0','例如在此重置“今日互动”标记（示例尚未分配CFLAG槽位，使用前另行分配）')
            if 'CFLAG:具体剧情状态' in line:
                line=line.replace('SIF CFLAG:具体剧情状态 == 1','示例条件：自定义剧情状态为1（尚未分配CFLAG槽位，使用前另行分配）')
            if 'TALENT:酒豪' in line:
                assert line.lstrip().startswith(';')
                line=line.replace('TALENT:酒豪','TALENT:ALCOHOL_TOLERANCE_AMER >= 2')
            line=line.replace('TFLAG:194不是36的时候','TFLAG:194 不是36的时候')
            replacements=[]; numeric_notes=[]
            for arr,parts,_,_ in refs(line):
                start,end,token=parts[-1]
                if token.endswith('_AMER') or token.startswith('AME36_'):continue
                if token.startswith('(') or token=='LOCAL':
                    if arr=='CFLAG' and token=='(1101 + LOCAL)':
                        numeric_notes.append('1101～1110为自定义FIRSTTIME位存储区，LOCAL为事件号/64')
                    elif arr=='CFLAG' and (token=='LOCAL' or token=='(LOCAL + 500)'):
                        if p.name.endswith('_工具函数.ERB'):
                            numeric_notes.append('测试工具批量访问CFLAG的1201～1253回忆/经历记录槽，保留原有范围')
                        else:
                            numeric_notes.append('地点探针：LOCAL访问1001～1499，LOCAL+500访问对应次数槽')
                    continue
                value=int(token) if token.isdigit() else defs.get('BASE' if arr=='MAXBASE' else arr,{}).get(token)
                if value is None and arr=='TALENT' and token=='没有接吻经验': value=6
                assert value is not None,(p.name,no,arr,token)
                name=aliases.get(arr,{}).get(value)
                if arr=='CFLAG' and value==1204:name='AME36_RECOLLECTION_303'
                if name:
                    replacements.append((start,end,name));changes.append((p.name,no,arr,token,name,value))
                else:
                    replacements.append((start,end,str(value)))
                    definitions=defs.get('BASE' if arr=='MAXBASE' else arr,{})
                    meaning=next((s for s,n in definitions.items() if n==value),None)
                    if meaning is None and arr=='CFLAG' and value in (207,208):
                        assert line.lstrip().startswith(';'),(p.name,no)
                        meaning='旧模板衣装比较槽；当前CFLAG.csv未命名，仅保留历史注释示例，含义待核对'
                    assert meaning,(p.name,no,arr,value)
                    numeric_notes.append(f'{arr}索引{value}：{meaning}')
                    changes.append((p.name,no,arr,token,str(value),value))
            for start,end,new in sorted(replacements,reverse=True):line=line[:start]+new+line[end:]
            if numeric_notes:
                indent=re.match(r'\s*',line).group().replace('\r','').replace('\n','')
                note=indent+';属性索引：'+'；'.join(dict.fromkeys(numeric_notes))+'\r\n'
                out.append(note);comments.append((p.name,no,numeric_notes))
            out.append(line)
        result=''.join(out)
        prefix=bytes.fromhex('efbbbf') if raw.startswith(bytes.fromhex('efbbbf')) else b''
        pending_writes[p]=prefix+result.encode('utf-8')
    for p,content in pending_writes.items():p.write_bytes(content)
    report={'replacements':changes,'numeric_notes':comments,'new_aliases':NEW}
    (ROOT/'tmp/属性索引修改记录.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('完成引用替换',len(changes),'处；数字/动态索引注释',len(comments),'行；新增AMER别名',sum(map(len,NEW.values())),'项。')

def verify():
    import base64,difflib
    baseline=json.loads((ROOT/'tmp/属性索引整理前.json').read_text(encoding='utf-8'))
    header=next(ROOT.glob('*.ERH'))
    current_header=header.read_text(encoding='utf-8-sig')
    values={m[1]:int(m[2]) for m in re.finditer(r'^#DIM CONST (\w+)\s*=\s*(\d+)',current_header,re.M)}
    old_header=base64.b64decode(baseline[header.name]).decode('utf-8-sig')
    old_values={m[1]:int(m[2]) for m in re.finditer(r'^#DIM CONST (\w+)\s*=\s*(\d+)',old_header,re.M)}
    assert all(values[k]==v for k,v in old_values.items())
    assert len(values)==len(old_values)+sum(map(len,NEW.values()))
    names=re.findall(r'^#DIM CONST (\w+)',current_header,re.M)
    assert len(names)==len(set(n.lower() for n in names))
    defs=load_defs()
    def canonical(txt):
        result=[]
        for line in txt.splitlines():
            if line.lstrip().startswith(';') or not line.strip():continue
            s=line.split(';',1)[0].strip();edits=[]
            for arr,parts,_,_ in refs(s):
                a,b,t=parts[-1]
                v=values.get(t)
                if v is None:v=int(t) if t.isdigit() else defs.get('BASE' if arr=='MAXBASE' else arr,{}).get(t)
                if v is not None:edits.append((a,b,str(v)))
            for a,b,t in sorted(edits,reverse=True):s=s[:a]+t+s[b:]
            result.append(s)
        return result
    for name,encoded in baseline.items():
        p=ROOT/name;old=base64.b64decode(encoded);new=p.read_bytes()
        assert old.startswith(b'\xef\xbb\xbf')==new.startswith(b'\xef\xbb\xbf'),name
        assert old.count(b'\n')==old.count(b'\r\n') and new.count(b'\n')==new.count(b'\r\n'),name
        if p.suffix.upper()=='.ERB':
            a=canonical(old.decode('utf-8-sig'));b=canonical(new.decode('utf-8-sig'))
            assert a==b,'\n'.join(difflib.unified_diff(a,b,fromfile=name+' before',tofile='after'))
    for p in ROOT.glob('*.ERB'):
        lines=p.read_text(encoding='utf-8-sig').splitlines()
        for no,line in enumerate(lines,1):
            for arr,parts,_,_ in refs(line):
                token=parts[-1][2]
                assert token.isascii(),(p.name,no,token)
                if token.isdigit():
                    assert no>1 and '属性索引：' in lines[no-2],(p.name,no,token)
    print('通过：索引还原后7个ERB逐行内容一致（忽略注释/首尾空白）；8文件BOM/CRLF保留；原常量值不变；新增别名无重名；数字索引有邻近注释；无中文索引名残留。')

if __name__=='__main__':
    import sys
    if '--apply' in sys.argv:transform()
    elif '--verify' in sys.argv:verify()
    else:inventory()
