#!/usr/bin/env python3
"""生成额度池镜像快照 s-<key>.json（数据源：本地账本，零官方接口调用）。

显示名优先级：控制台里的自定义别名（switcher/aliases.json，uid→名字）
> 官方昵称（账本 account 字段「昵称(uid8)」的前半段）> uid8。
旧账本行没有 uid 字段，用 account 字符串里的 uid8 反查别名；
新行（2026-11-17 起）直接带 uid，匹配更稳。
"""
import json, os, datetime

HERE = os.path.dirname(__file__)
LEDGER = os.path.join(HERE, '..', 'switcher', 'usage.jsonl')
ALIASES = os.path.join(HERE, '..', 'switcher', 'aliases.json')
KEY = (open(os.path.join(HERE, '.mirror-key')).read().strip()
       if os.path.exists(os.path.join(HERE, '.mirror-key')) else 'ad99ad')

rows = []
try:
    for line in open(LEDGER, encoding='utf-8'):
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
except OSError:
    pass

# uid 全串 → 别名；再派生 uid8 → 别名（旧账本行只有 uid8 可用）
alias_by_uid, alias_by_uid8 = {}, {}
try:
    with open(ALIASES, encoding='utf-8') as f:
        for uid, name in json.load(f).items():
            name = (name or '').strip()
            if uid and name:
                alias_by_uid[uid] = name
                alias_by_uid8[uid[:8]] = name
except Exception:
    pass


def key_of(r):
    """聚合键统一为 uid8：新行取 uid 前 8 位；旧行无 uid，从「昵称(uid8)」里取。

    不能直接用「uid or account 串」当 key——2026-11-17 起新行带 uid、旧行没有，
    同一账号会被拆成两个桶，镜像页出现重名账号。
    """
    uid = r.get('uid') or ''
    if uid:
        return uid[:8]
    acct = r.get('account', '?')
    if '(' in acct:
        u8 = acct.rsplit('(', 1)[-1].rstrip(')')
        if u8:
            return u8
    return acct


def disp(r):
    """单条账本行的展示名：uid/uid8 命中别名用别名，否则取官方昵称。"""
    uid = r.get('uid') or ''
    if uid[:8] in alias_by_uid8:
        return alias_by_uid8[uid[:8]]
    acct = r.get('account', '?')
    uid8 = acct.rsplit('(', 1)[-1].rstrip(')') if '(' in acct else ''
    if uid8 in alias_by_uid8:
        return alias_by_uid8[uid8]
    return acct.split('(')[0]


latest, row_of = {}, {}
for r in rows:
    ba = r.get('balance_after')
    if isinstance(ba, (int, float)):
        key = key_of(r)
        latest[key] = ba
        row_of[key] = r

total = sum(latest.values())

led = []
for r in rows[-30:]:
    credit = r.get('credit_label') or ('未知' if r.get('credit') is None else str(r.get('credit')))
    led.append({
        'ts': r.get('ts', '')[11:],
        'acct': disp(r),
        'model': r.get('model', ''),
        'credit': credit,
    })

low = [disp(row_of[k]) for k, v in latest.items() if v < 20]

snap = {
    'ts': rows[-1].get('ts', '') if rows else datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    'generated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    'balances': sorted([(disp(row_of[k]), v) for k, v in latest.items()], key=lambda x: -x[1]),
    'total': total,
    'low': low,
    'ledger': led,
}

out = os.path.join(HERE, 's-%s.json' % KEY)
with open(out, 'w', encoding='utf-8') as f:
    json.dump(snap, f, ensure_ascii=False, separators=(',', ':'))
print('snapshot written:', out, len(json.dumps(snap)), 'bytes,',
      len(led), 'ledger rows,', len(alias_by_uid), 'aliases')
