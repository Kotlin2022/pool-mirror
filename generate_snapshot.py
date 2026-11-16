#!/usr/bin/env python3
"""生成额度池镜像快照 snapshot.json（数据源：本地账本，零官方接口调用）。"""
import json, os, datetime

LEDGER = os.path.join(os.path.dirname(__file__), '..', 'switcher', 'usage.jsonl')
KEY = (open(os.path.join(os.path.dirname(__file__), '.mirror-key')).read().strip()
       if os.path.exists(os.path.join(os.path.dirname(__file__), '.mirror-key')) else 'ad99ad')

rows = []
try:
    for line in open(LEDGER, encoding='utf-8'):
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
except OSError:
    pass

latest = {}
for r in rows:
    ba = r.get('balance_after')
    if isinstance(ba, (int, float)):
        latest[r.get('account', '?')] = ba

total = sum(latest.values())
nick = lambda a: a.split('(')[0]

led = []
for r in rows[-30:]:
    credit = r.get('credit_label') or ('未知' if r.get('credit') is None else str(r.get('credit')))
    led.append({
        'ts': r.get('ts', '')[11:],
        'acct': nick(r.get('account', '?')),
        'model': r.get('model', ''),
        'credit': credit,
    })

low = [nick(a) for a, v in latest.items() if v < 20]

snap = {
    'ts': rows[-1].get('ts', '') if rows else datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    'generated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    'balances': sorted([(nick(a), v) for a, v in latest.items()], key=lambda x: -x[1]),
    'total': total,
    'low': low,
    'ledger': led,
}

out = os.path.join(os.path.dirname(__file__), 's-%s.json' % KEY)
with open(out, 'w', encoding='utf-8') as f:
    json.dump(snap, f, ensure_ascii=False, separators=(',', ':'))
print('snapshot written:', out, len(json.dumps(snap)), 'bytes,', len(led), 'ledger rows')
