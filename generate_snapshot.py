#!/usr/bin/env python3
"""生成额度池镜像快照 s-<key>.json（数据源：本地账本，零官方接口调用）。

显示名优先级：控制台里的自定义别名（switcher/aliases.json，uid→名字）
> 官方昵称（账本 account 字段「昵称(uid8)」的前半段）> uid8。
旧账本行没有 uid 字段，用 account 字符串里的 uid8 反查别名；
新行（2026-11-17 起）直接带 uid，匹配更稳。
"""
import json, os, datetime, urllib.request

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


# 本地控制台实时余额（uid8 → remain）。快照脚本本身不打官方接口，只是读控制台
# 内存里那份 60s TTL 的余额缓存——控制台前端每 8s 轮询 overview 会维持它。
# 账本里的 balance_after 是「最后一次请求时的余额」，低频号会陈旧（几天前），
# 直接拿它聚合会让镜像总额比控制台少几千分。所以实时优先、账本兜底。
def live_balances():
    url = 'http://127.0.0.1:8765/api/pool/overview'
    try:
        # 显式禁用代理：沙箱/某些终端会设 HTTP_PROXY，Python urllib 不总遵守 NO_PROXY，
        # 导致连 127.0.0.1 也被转发到代理而超时。本地回环必须直连。
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print('[balance] 本地控制台不可达，回落账本余额:', e)
        return {}
    result = {}
    for uid, item in (data.get('balances') or {}).items():
        bal = item.get('balance') if isinstance(item, dict) else None
        remain = (bal or {}).get('remain') if isinstance(bal, dict) else None
        if isinstance(remain, (int, float)) and uid:
            # value 里带 nickname，供账本里没出现过的新号兜底展示名
            result[uid[:8]] = (remain, (item or {}).get('nickname') or uid[:8])
    return result


live = live_balances()

# 聚合：账号集合严格跟随控制台当前账号列表（用户 11-20 定案）。
# 实时源可用 → 只统计实时源里的账号，账本中已移除/失效的老账号不再计入；
# 实时源不可用 → 才回落账本余额（不比过去更差，保证控制台没开也能出快照）。
latest, row_of = {}, {}
if live:
    for uid8, (remain, nick) in live.items():
        latest[uid8] = remain
        name = alias_by_uid8.get(uid8) or nick
        row_of[uid8] = {'uid': uid8, 'account': name + '(' + uid8 + ')'}
    src = '控制台实时源'
else:
    for r in rows:
        ba = r.get('balance_after')
        if isinstance(ba, (int, float)):
            key = key_of(r)
            latest[key] = ba
            row_of[key] = r
    src = '账本兜底'

total = sum(latest.values())
print('[balance] 数据源 %s，%d 个账号，合计 %d' % (src, len(latest), total))

def credit_text(r):
    """积分消耗展示文案：限时免费/网关截断的小额一律记为 0 分。

    历史账本行写死 '<0.01'，新版 pool_bridge 已改写为 '0'，但镜像快照会被
    反复重新生成，所以这里再兜一层，避免旧行把 '<0.01' 又带回镜像页。
    """
    lab = r.get('credit_label')
    c = r.get('credit')
    if lab:
        s = str(lab)
    elif c is None:
        return '未知'
    else:
        try:
            return '0' if float(c) <= 0 else str(c)
        except (TypeError, ValueError):
            s = str(c)
    if s == '<0.01' or s in ('≈0', '≈0.0', '≈0.00'):
        return '0'
    return s


led = []
for r in rows[-30:]:
    led.append({
        'ts': r.get('ts', '')[11:],
        'acct': disp(r),
        'model': r.get('model', ''),
        'credit': credit_text(r),
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
