#!/usr/bin/env python3
"""Offline census and safe authored report. Run from any directory; stdlib only.
Raw bodies, titles, authors, labels, comments, release prose never enter reports.
Keywords select overlapping candidates; they do not confirm defects/fixes.
"""
import argparse
import collections
import datetime as dt
import hashlib
import html
import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
PIN = '96f4c115c9749078f90cbf210a01d39baf3f53b6'
BASE = 'https://github.com/Wei-Shaw/sub2api'
PATTERNS = {
    'native_protocols': r'stream|流式|tool.?call|tool.?id|responses|messages|工具',
    'oauth_provider': r'oauth|refresh|刷新|封号|封禁|\bban\b|quota|额度',
    'scheduling': r'并发|调度|sticky|failover|粘性|亲和|切换|重试',
    'security_custody': r'ssrf|security|安全|泄露|跨租户|越权|密钥',
    'billing': r'计费|扣费|扣款|double.?charg|billing|余额|退款',
    'deployment': r'重启|redis|postgres|数据库|升级|部署|migration|backup|备份',
}
VERSION = re.compile(r'(?<![\d.])v?(0\.[12]\.\d{1,3})(?![\d.])')
BUCKETS = ('0–7', '8–30', '31–90', '91–180', '181+')

def read(p):
    return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))

def digest(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()

def date(s):
    return dt.datetime.fromisoformat(s.replace('Z', '+00:00'))

def stamp(d):
    return d.isoformat(timespec='seconds').replace('+00:00', 'Z')

def bucket(days):
    # Continuous elapsed-day intervals [0,8), [8,31), [31,91), [91,181), [181,+inf).
    for limit, label in zip((8, 31, 91, 181, float('inf')), BUCKETS):
        if days < limit:
            return label

def counts(values):
    return dict(sorted(collections.Counter(values).items()))

def safe(value):
    """Escape authored text too; consumers must use textContent, never innerHTML."""
    if isinstance(value, str):
        return html.escape(value, quote=True)
    if isinstance(value, dict):
        return {str(k): safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [safe(v) for v in value]
    return value

def kind_candidate(i):
    labels = {l.get('name', '').lower() if isinstance(l, dict) else str(l).lower() for l in i['labels']}
    t = i['title'].lower()
    # Prioritise explicit category, retaining mixed bug/feature as mixed.
    defect = bool(re.search(r'\bbug\b|\bfix\b|缺陷|漏洞|\[security\]', t)) or 'bug' in labels
    feature = bool(re.search(r'\bfeat(?:ure)?\b|enhancement|功能请求|功能建议|希望|建议', t)) or 'enhancement' in labels
    if i.get('state_reason') == 'duplicate' or 'duplicate' in labels or re.search(r'\[duplicate\]|重复issue', t):
        return 'duplicate_candidate'
    if defect and feature:
        return 'mixed_defect_enhancement_candidate'
    if feature:
        return 'enhancement_candidate'
    if 'question' in labels or re.search(r'求助|咨询|怎么|如何|是否|\[question\]', t):
        return 'support_question_candidate'
    if defect:
        return 'defect_candidate'
    return 'unclassified'

def comments_metadata(path, reviewed):
    """Accept list of GitHub comment objects carrying issue_number/number, or
    {issues:[{number,comments:[...],complete:true}]}, or numeric-key mapping.
    No content or usernames are exported. No automatic fix adjudication.
    """
    if not path.exists():
        return {'status': 'NOT SUPPLIED', 'complete_pages_proven': False, 'reviewed_issue_metadata': []}
    raw = read(path)
    manual = read(HERE / 'comment-notes.json')
    interpretation_current = digest(path) == manual.get('interpreted_input_sha256')
    grouped = collections.defaultdict(list)
    complete = set()
    if isinstance(raw, dict) and 'issues' in raw:
        for entry in raw['issues']:
            n = int(entry['number']); grouped[n].extend(entry['comments'])
            if entry.get('complete') is True:
                complete.add(n)
    elif isinstance(raw, dict):
        for key, entries in raw.items():
            if str(key).isdigit() and isinstance(entries, list):
                grouped[int(key)].extend(entries)
    elif isinstance(raw, list):
        for entry in raw:
            n = entry.get('issue_number', entry.get('number'))
            if n is None:
                raise ValueError('comment is missing issue_number; cannot associate evidence')
            if 'comments' in entry and isinstance(entry['comments'], list):
                grouped[int(n)].extend(entry['comments'])
                if entry.get('complete') is True:
                    complete.add(int(n))
            else:
                grouped[int(n)].append(entry)
    else:
        raise ValueError('unsupported comments envelope')
    result = []
    for n in sorted(reviewed):
        cs = grouped.get(n, [])
        result.append({'number': n, 'supplied_comment_count': len(cs),
                       'complete_explicitly_asserted_by_stager': n in complete,
                       'maintainer_association_comment_count': sum(c.get('author_association') in ('OWNER','MEMBER','COLLABORATOR') for c in cs)})
    return {'status': ('SUPPLIED and interpreted; completeness bounded to snapshot counts' if interpretation_current else 'SUPPLIED but changed since manual interpretation; authored comment conclusions withheld'),
            'manual_interpretation_current': interpretation_current,
            'interpreted_input_sha256': manual.get('interpreted_input_sha256'),
            'association_counts': counts(c.get('author_association') if c.get('author_association') in ('OWNER','MEMBER','COLLABORATOR','CONTRIBUTOR','FIRST_TIMER','FIRST_TIME_CONTRIBUTOR','NONE') else 'unspecified' for cs in grouped.values() for c in cs),
            'supplied_issue_count': len(grouped), 'supplied_comment_count': sum(len(cs) for cs in grouped.values()),
            'sha256': digest(path), 'complete_pages_proven': False,
            'reviewed_issue_metadata': result}

def analyze(args):
    issues_path, releases_path = args.inputs / 'issues.json', args.inputs / 'releases.json'
    issues, releases = read(issues_path), read(releases_path)
    if not isinstance(issues, list) or not isinstance(releases, list):
        raise ValueError('expected issue/release arrays')
    ns = [i['number'] for i in issues]
    if len(set(ns)) != len(ns):
        raise ValueError('duplicate issue number; census would double count')
    if any('pull_request' in i for i in issues):
        raise ValueError('PR present in purported non-PR census')
    if len(issues) != args.expect_count:
        raise ValueError(f'expected {args.expect_count} non-PR issues, got {len(issues)}')
    if any(i['state'] not in ('open', 'closed') for i in issues):
        raise ValueError('unrecognized issue state')
    for i in issues:
        n = i['number']
        if not isinstance(n, int) or n <= 0 or i['html_url'] != f'{BASE}/issues/{n}':
            raise ValueError('invalid issue identity/URL')
        if i.get('state_reason') not in (None, 'completed', 'not_planned', 'reopened', 'duplicate'):
            raise ValueError('unrecognized state_reason; review schema')
        for key in ('created_at','updated_at','closed_at'):
            if i.get(key):
                date(i[key])
        if i['state'] == 'closed' and not i['closed_at']:
            raise ValueError('closed issue lacks closed_at')
    latest = max(date(i[k]) for i in issues for k in ('created_at','updated_at','closed_at') if i.get(k))
    reference = date(args.cutoff) if args.cutoff else latest
    if reference < latest:
        raise ValueError('analysis cutoff precedes observed issue event')
    by_number = {i['number']:i for i in issues}
    reviews = read(HERE / 'reviews.json')['issues']
    manual_comment_notes = read(HERE / 'comment-notes.json')
    comment_notes = {e['number']: e for e in manual_comment_notes['notes']}
    comment_path = args.inputs / 'comments.json'
    staged_comments = {}
    comment_interpretation_current = comment_path.exists() and digest(comment_path) == manual_comment_notes.get('interpreted_input_sha256')
    if comment_path.exists():
        envelope = read(comment_path)
        if isinstance(envelope,dict) and isinstance(envelope.get('issues'),list):
            staged_comments = {e['number']: e['comments'] for e in envelope['issues']}
    comment_reconciliation = []
    if len({r['number'] for r in reviews}) != len(reviews) or len(reviews) < 40:
        raise ValueError('need at least 40 unique reviewed issues')
    for r in reviews:
        i = by_number[r['number']]
        r.update({'url': i['html_url'], 'state': i['state'], 'state_reason': i['state_reason'],
                  'created_at': i['created_at'], 'closed_at': i['closed_at'],
                  'comment_count_at_snapshot': i['comments'], 'independently_reproduced': False,
                  'maintainer_fix_confirmed': False})
        cs = staged_comments.get(r['number'], [])
        ids = {c['id'] for c in cs}
        note = comment_notes.get(r['number'])
        if note and cs and comment_interpretation_current:
            if not set(note['ids']).issubset(ids):
                raise ValueError('authored comment note cites absent ID')
            r['comment_analysis'] = note['note']
            r['cited_comments'] = [{'id': c['id'], 'url': c['html_url'], 'author_association': c.get('author_association'), 'created_at': c['created_at']} for c in cs if c['id'] in note['ids']]
            for c in r['cited_comments']:
                if c['url'] != f"{BASE}/issues/{r['number']}#issuecomment-{c['id']}":
                    raise ValueError('unexpected comment URL')
        else:
            r['comment_analysis'] = ('Current comment bytes differ from manually interpreted input; prior authored comment conclusions withheld, manual review required.' if cs and not comment_interpretation_current else 'No substantive staged comment evidence; no fix inferred.')
            r['cited_comments'] = []
        comment_reconciliation.append({'number':r['number'], 'snapshot_count':i['comments'], 'staged_count':len(cs), 'count_matches':len(cs)==i['comments'], 'present_in_envelope':r['number'] in staged_comments})
    census = {'total': len(issues), 'states': counts(i['state'] for i in issues),
              'state_reasons': counts(i['state_reason'] or 'unspecified' for i in issues),
              'unique_authors': len({i['author'] for i in issues if i['author']}),
              'missing_authors': sum(not i['author'] for i in issues),
              'author_identity_limit': 'Distinct nonempty snapshot author strings; renamed/deleted identities can skew this count. No identities exported.',
              'with_labels': sum(bool(i['labels']) for i in issues),
              'label_assignments': sum(len(i['labels']) for i in issues),
              'label_counts': counts((l.get('name') if isinstance(l,dict) else l) if (l.get('name') if isinstance(l,dict) else l) in {'bug','enhancement','invalid','question','duplicate'} else 'other_label' for i in issues for l in i['labels'])}
    census['without_labels'] = len(issues) - census['with_labels']
    census['without_labels_percent'] = round(100*census['without_labels']/len(issues), 3)
    for state in ('open','closed'):
        xs = [i for i in issues if i['state'] == state]
        census[f'{state}_age_since_creation_days'] = dict.fromkeys(BUCKETS,0)
        for i in xs:
            census[f'{state}_age_since_creation_days'][bucket((reference-date(i['created_at'])).total_seconds()/86400)] += 1
    census['closed_duration_days'] = dict.fromkeys(BUCKETS,0)
    for i in issues:
        if i['state'] == 'closed':
            days = (date(i['closed_at'])-date(i['created_at'])).total_seconds()/86400
            if days < 0:
                raise ValueError('closure precedes creation')
            census['closed_duration_days'][bucket(days)] += 1
    census['age_bucket_definition'] = '[0,8), [8,31), [31,91), [91,181), [181,infinity) elapsed days; closed age and time-to-close are distinct.'
    census['windows'] = {}
    for days in (30,90):
        start = reference-dt.timedelta(days=days)
        opened = [i for i in issues if start <= date(i['created_at']) <= reference]
        closed = [i for i in issues if i['closed_at'] and start <= date(i['closed_at']) <= reference]
        census['windows'][str(days)] = {'start_inclusive': stamp(start), 'end_inclusive': stamp(reference),
            'opened': len(opened), 'closed': len(closed), 'net_snapshot_flow': len(opened)-len(closed),
            'opened_per_day': round(len(opened)/days,3), 'closed_per_day': round(len(closed)/days,3),
            'closure_to_opening_ratio': round(len(closed)/len(opened),3) if opened else None,
            'opened_cohort_current_states': counts(i['state'] for i in opened),
            'limitation': 'closed_at is last closure in snapshot; reopen/reclose events unavailable. Flows use different cohorts; not fix/success/failure rates.'}
    candidates = {k:{'total':sum(bool(re.search(p,(i['title'] or '')+'\n'+(i['body'] or ''),re.I)) for i in issues),
                     'states':counts(i['state'] for i in issues if re.search(p,(i['title'] or '')+'\n'+(i['body'] or ''),re.I))}
                  for k,p in PATTERNS.items()}
    versions = collections.Counter()
    no_version = 0
    for i in issues:
        vs = {'v'+m for m in VERSION.findall((i['title'] or '')+'\n'+(i['body'] or ''))}
        no_version += not bool(vs)
        versions.update(vs)
    source = read(HERE / 'source-notes.json')
    for s in source:
        p = args.inputs / 'upstream' / s['path']
        s['available'] = p.is_file()
        if not s['available']:
            raise ValueError('inspected source evidence file is missing')
        if p.is_file():
            s['sha256'] = digest(p)
            if s['sha256'] != s.get('inspected_sha256'):
                raise ValueError('source bytes differ from inspected evidence; review source observation before regeneration')
            if not 1 <= s['line'] <= len(p.read_text().splitlines()):
                raise ValueError('source citation line out of bounds')
        s['url'] = f"{BASE}/blob/{PIN}/{s['path']}#L{s['line']}"
    release_meta = []
    for r in releases:
        tag = r['tag_name']
        if not re.fullmatch(r'v0\.[12]\.\d{1,3}',tag):
            raise ValueError('unexpected release tag; review safe schema')
        if r['html_url'] != f'{BASE}/releases/tag/{tag}':
            raise ValueError('unexpected release URL')
        release_meta.append({'tag':tag,'url':r['html_url'],'published_at':r['published_at'],
            'draft':r['draft'],'prerelease':r['prerelease'],
            'candidate_topics':[k for k,p in PATTERNS.items() if re.search(p,r['body'] or '',re.I)]})
    pub = sorted(date(r['published_at']) for r in releases if r['published_at'])
    gaps = [(b-a).total_seconds()/86400 for a,b in zip(pub,pub[1:])]
    recommendations = [
        {'mode':'BYOK native API','verdict':'CONDITIONAL GO for isolated validation; production gate pending','fragility_out_of_10':5,'confidence':'medium-low',
         'rationale':'Fewer identity lifecycle dependencies than subscription pool, but real Responses/Messages tool semantics, SSE error handling and custody/tenant isolation are unproven on the operator runtime.'},
        {'mode':'OAuth subscription pool','verdict':'NO-GO for production adoption now; continue test-only spike','fragility_out_of_10':8,'confidence':'medium',
         'rationale':'Rotating tokens, provider bans/quotas, sticky state and encrypted history portability compound gateway risk. Source mitigations exist; test-only identity and normalized live receipts are absent.'},
        {'mode':'Our UI + private backend','verdict':'CONDITIONAL GO as chosen topology; production boundary gate pending','fragility_out_of_10':6,'confidence':'medium',
         'rationale':'Own workspace ownership ledger, capability broker, admin network isolation, egress allowlist and hard budgets are required. Groups are routing constraints, not proof of tenant account ownership; built-in payment/UI is outside this decision.'}]
    return {'schema_version':1,'dataset':{'issues_sha256':digest(issues_path),'releases_sha256':digest(releases_path),
            'analysis_reference_utc':stamp(reference),'latest_observed_issue_event_utc':stamp(latest),
            'snapshot_capture_utc':'not supplied; latest observed event is a lower bound, not capture timestamp',
            'first_created_at':min(i['created_at'] for i in issues),'last_created_at':max(i['created_at'] for i in issues),
            'non_pr_census_assertion':'3935 all non-PR issues per supplied snapshot contract; unique numbers and absence of PR marker verified offline; no independent GitHub completeness proof',
            'source_version':'v0.2.11','requested_source_pin':PIN,
            'source_pin_provenance':'operator supplied; git metadata unavailable, immutable commit not independently authenticated; cited file fingerprints recorded',
            'release_snapshot_count':len(releases),'release_scope':'latest 30 only; not full release history'},
            'census':census,'candidate_topics':candidates,'candidate_kind_counts':counts(kind_candidate(i) for i in issues),
            'manual_reviewed_reporter_versions':counts(r['version'] for r in reviews),
            'version_mentions':{'counts':dict(sorted(versions.items(),key=lambda kv:(-kv[1],kv[0]))),'issues_without_explicit_v0_1_or_v0_2_version':no_version,
              'limitation':'Distinct mention per issue, may include requested/fixed/other-component versions, overlapping and not reporter-version distribution. Manual reporter versions below.'},
            'reviewed_issue_count':len(reviews),'reviewed_current_states':counts(r['state'] for r in reviews),
            'reviewed_kind_counts':counts(r['kind'] for r in reviews),'reviewed_assessment_counts':counts(r['assessment'] for r in reviews),
            'reviewed_issues':reviews,'source_findings':source,'comments':comments_metadata(args.inputs/'comments.json', {r['number'] for r in reviews}),
            'comment_reconciliation':comment_reconciliation,
            'pending_comment_issue_numbers':[e['number'] for e in comment_reconciliation if not e['present_in_envelope']],
            'releases':release_meta,'release_activity':{'first':stamp(pub[0]),'last':stamp(pub[-1]),'span_days':round((pub[-1]-pub[0]).total_seconds()/86400,3),
                 'mean_inter_release_days':round(sum(gaps)/len(gaps),3),'in_last_30_days':sum(reference-dt.timedelta(days=30)<=d<=reference for d in pub),
                 'limit':'Release frequency indicates maintenance/change surface, not availability or failure rate.'},
            'recommendations':recommendations,
            'limitations':['All 3935 metadata/bodies included in machine aggregation; 52 relevant issues studied, not all manually read.',
                'Keyword selection/classification is heuristic and overlapping; support/enhancement/duplicates cannot be reliably separated using near-empty labels alone.',
                'Screenshots/videos not fetched; raw credentials/config snippets deliberately excluded from report; reporter claims are not independent reproduction.',
                'Closed/completed is workflow state, not fix proof. Original 48-issue staged comments have NONE/CONTRIBUTOR associations only; focused follow-ups pending, no independently authenticated maintainer confirmation.',
                'No upstream tests, container, agent E2E, OAuth refresh, MiMo/OpenRouter or security exploit executed by audit lane.',
                'Fragility scores are ordinal engineering judgment, not calibrated failure probabilities. No request/operator exposure denominator, no star-based reliability claim.',
                'Source/test presence corroborates mechanism or mitigation; does not prove deployed image or client lifecycle success.']}

def report(f):
    c=f['census']; w=c['windows']; d=f['dataset']
    out=['# Sub2API: аудит стабильности для ReviewRouter', '',
      'BYOK и наша UI + private backend: **CONDITIONAL GO для изолированной проверки**, не production approval. OAuth pool: **NO-GO для production сейчас**; продолжить test-only spike. Источник решения — совместимость native agent lifecycle, custody, tenant boundaries и бюджетные ограничения, а не само число открытых issues.', '',
      f"Данные: **{c['total']} non-PR**, {c['states']['open']} open / {c['states']['closed']} closed; latest observed event **{d['latest_observed_issue_event_utc']}**. Точный capture timestamp не предоставлен. Расчётный cutoff = последний наблюдаемый event. Source v0.2.11, supplied pin `{PIN}`; Git metadata недоступны, provenance pin не аутентифицирован независимо. 30 последних releases, не вся история. Машинный census полный по staged contract; вручную разобраны {f['reviewed_issue_count']} целевых issues, не все 3935.", '',
      f"За 30 дней opened/closed: **{w['30']['opened']}/{w['30']['closed']}**, за 90: **{w['90']['opened']}/{w['90']['closed']}**. Opened/day: {w['30']['opened_per_day']} / {w['90']['opened_per_day']}; closed/day: {w['30']['closed_per_day']} / {w['90']['closed_per_day']}. Это потоки разных когорт; повторные закрытия не видны, closure не означает fix. Без request denominator issue count нельзя перевести в failure rate.", '',
      f"Уникальных непустых author strings: **{c['unique_authors']}**; без labels **{c['without_labels']} ({c['without_labels_percent']}%)**, всего assignments {c['label_assignments']}. Поэтому автоматическое отделение defect/support/enhancement/duplicate слабое. Версия обнаружена лишь как упоминание: данные `version_mentions` не являются установленной версией репортёра.", '',
      '| Режим | Fragility /10 (хуже выше) | Уверенность | Решение |', '|---|---:|---|---|']
    for r in f['recommendations']:
        out.append(f"| {r['mode']} | {r['fragility_out_of_10']} | {r['confidence']} | {r['verdict']} |")
    out += ['', 'Оценки порядковые, не вероятность отказа. BYOK исключает refresh/ban lifecycle pool, но не SSE false-green и tool integrity. Наша UI уменьшает открытый admin surface только при собственном ownership ledger и capability checks; добавляет adapter/cache сложность. OAuth дополнительно зависит от provider policy, token rotation, quota и переносимости encrypted history.', '',
      '## Критические adoption gates', '',
      '- **Tenant/custody:** C02/C05/C07/D04/D06/D07. Group routing не доказывает ownership account; JSONB credential map и Redis projection не дают оснований обещать application encryption. Admin/export/backup только operator; UI выдаёт filtered DTO, runner получает короткую capability. #3086 — слабый historical report, #6169/#6112 — конкретные source risks, не исполненные exploits.',
      '- **False-green/native tools:** A01–A10/E02–E04/E10–E11. #7285 показывает reported HTTP 200 без настоящих tools; #7708 — ошибка внутри SSE 200; #7506 — encrypted history при смене account. Требуются реальные Codex/Claude reads, tool IDs/results и terminal outcome. Ни MiMo, ни OpenRouter E2E здесь не доказан.',
      '- **Refresh/scheduling:** F02–F06/G01/G06. Unified refresh и RPM projection уже имеют source mitigations; Redis lock failure деградирует до local mutex. Pause/sticky и account-change encrypted state требуют transport/lifecycle proof, двух процессов и failure injection.',
      '- **Hard budget:** H05/E06/E11/G05. v0.2.11 reservation — значимое улучшение concurrent admission, но estimation, unpriced/Redis fail-open и final overdraft сохраняют риски. ReviewRouter должен иметь собственный atomic budget/run cap и не выдавать engine balance за строгий финансовый лимит. Built-in payments/refunds не нужны нашему UI.',
      '- **Recovery/upgrades:** G01–G04/G07. Cloned DB restore вместе с schema_migrations, readiness delay, restart active stream, bounded RSS. #7030 относится к потере migration ledger/partial restore; не ко всем обычным upgrades.', '',
      '## Release patterns и maintenance', '',
      f"В latest-30 окне {f['release_activity']['span_days']} дня, средний gap {f['release_activity']['mean_inter_release_days']} дня, {f['release_activity']['in_last_30_days']} release за последние 30 дней. Release notes активно закрывают protocol/billing/scheduler gaps; это maintenance signal и большой change surface, не доказательство SLA. Sponsor text/stars не используются как reliability evidence.", '',
      '- v0.2.11: default-enabled inflight balance reservation; upgrade меняет admission low-balance concurrency. Проверить estimate/actual, unpriced, Redis failure, subscription bypass и cancel handoff. Новое #7770 относится к той же v0.2.11: compounded tier accounting остаётся reported risk.',
      '- v0.2.9: structured-output beta и role-item conversion; #7633/#7629 совпадают с release claims. #7700/#7708/#7506 показывают иные формы encrypted errors, не опровергаемые этими fix claims.',
      '- v0.2.8: RPM metadata projection, previous_response affinity и завершение stream на terminal event. #7225 получает scoped release/source/test corroboration; #7758 демонстрирует другую отсутствующую пару полей, её нельзя считать исправленной заодно.',
      '- v0.2.4: persistent cooldown/runtime block semantics (#6319 related); v0.1.179: long-context pricing gating AND→OR, после upgrade меняется price и нужен config review.',
      '- v0.1.172: release прямо заявляет regression quota reset, введённую v0.1.170. v0.1.182: release claim исправления duplicate cache-create accounting. Данные показывают реальные категории churn, но не частоту сбоев на наших workloads.', '',
      '## Лицензия, границы и недостающая информация', '',
      'LICENSE содержит LGPL v3; README указывает v3 или позже. Зафиксировать notices/изменения и проверить обязанности выбранного способа распространения/linking отдельно; это не юридическое заключение. Browser OIDC реализует human login/bind/registration, не наши GitHub Actions claims. Нельзя переносить существующий production subscription pool в этот эксперимент.', '',
      f"Comments: **{f['comments']['status']}**. Ранний `NEEDED-COMMENTS.json` содержит 52 приоритетных номера (лимит 60), URL, категории и причины. Первый batch (48 issues) получен; ещё 4 focused tool-ID/session issues добавлены в запрос. Формат staging описан в README. Первоначальный batch из 66 comments прочитан: NONE=56, CONTRIBUTOR=10, OWNER/MEMBER/COLLABORATOR отсутствуют. Counts первого batch совпадают со snapshot по всем 48 issues; pagination-complete assertion отдельно не предоставлен. Нет maintainer-confirmed fix; есть scoped reporter/release/source corroboration, особенно #7633. #6877 после comments исключён как likely off-project support. Live operator receipts и test OAuth identity остаются pending input; это не мешает завершить данный offline audit.", '',
      '## Приложение: воспроизводимый census', '',
      '| Age, elapsed days | Open since creation | Closed since creation | Closed time-to-close |', '|---|---:|---:|---:|']
    for b in BUCKETS:
        out.append(f"| {b} | {c['open_age_since_creation_days'][b]} | {c['closed_age_since_creation_days'][b]} | {c['closed_duration_days'][b]} |")
    out += ['', 'Buckets: [0,8), [8,31), [31,91), [91,181), [181,∞). Closed age и time-to-close измеряют разные величины. Current state/last closed_at не восстанавливают event history.', '',
      '| Keyword category (overlapping candidates only) | Count | Open | Closed |', '|---|---:|---:|---:|']
    for k,v in f['candidate_topics'].items():
        out.append(f"| {k} | {v['total']} | {v['states'].get('open',0)} | {v['states'].get('closed',0)} |")
    out += ['', 'Heuristic issue kinds: '+', '.join(f'{k}={v}' for k,v in f['candidate_kind_counts'].items())+'. Unclassified не означает absence of defect; explicit duplicate label крайне редок/отсутствует, текстовый match не даёт deduplication.', '',
      'Top explicit version mentions (может быть affected/fixed/requested version, overlap): '+', '.join(f'{k}: {v}' for k,v in list(f['version_mentions']['counts'].items())[:15])+f". Без такого упоминания: {f['version_mentions']['issues_without_explicit_v0_1_or_v0_2_version']}.", '',
      f"## Приложение: {f['reviewed_issue_count']} содержательных разборов", '',
      'Purposive sample по шести risk domains, open/closed и recent regressions. Это не случайная выборка и не оценка prevalence. Inspected supplied narrative/metadata; screenshots/video не просмотрены. Config/credential блоки не публикуются. Каждый пункт — reported evidence + next observable boundary; ни один failure здесь независимо не воспроизведён. `release_source_fix_support` означает scoped corroboration, не maintainer/live подтверждение.', '']
    for r in f['reviewed_issues']:
        out += [f"### [#{r['number']}]({r['url']}) — {r['state']}; state_reason={r['state_reason'] or 'null'}", '',
          f"Reporter version: {r['version']}. Kind: {r['kind']}; attribution: {r['attribution']}; assessment: {r['assessment']}; snapshot comments: {r['comment_count_at_snapshot']}.", '', r['summary'], '', '**Comments:** '+r['comment_analysis'], '',
          'Comment citations: '+(', '.join(f"[{c['id']}]({c['url']}) ({c['author_association']})" for c in r['cited_comments']) or 'none'), '',
          '**Наблюдаемая проверка:** '+r['scenario'], '']
    out += ['## Приложение: source/test evidence', '', 'Upstream tests только прочитаны; отдельного PASS нет. Каждый source fingerprint включён в findings.json, ссылки используют supplied immutable SHA, который не проверен через Git metadata.', '']
    for s in f['source_findings']:
        out += [f"- [{s['id']} {s['path']}:{s['line']}]({s['url']}): {s['observation']} ({s['evidence']})."]
    out += ['', '## Воспроизведение и handoff', '',
      'Из repository root: `python3 sub2api-issues-audit/analyze.py`; затем `python3 sub2api-issues-audit/verify.py`. Input SHA-256, formulas, весь census, короткие безопасные dashboard поля и source hashes находятся в findings.json/dashboard.json. `verification.json` фиксирует реально выполненные проверки этого analyzer, не upstream engine.', '',
      'Ownership: только sub2api-issues-audit/. Git lock preflight выполнен один раз: .git — linked-worktree файл, index.lock недоступен; обходов, commits/push не было. Bifrost и implementation lane не изменялись. Comments/live evidence не фабрикуются; рекомендации пересмотреть после normalized receipts и полного comment review.', '']
    return '\n'.join(out)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs',type=pathlib.Path,default=ROOT/'.spike-inputs')
    p.add_argument('--output',type=pathlib.Path,default=HERE)
    p.add_argument('--cutoff',help='UTC ISO reference, defaults to latest observed issue event, not claimed snapshot capture')
    p.add_argument('--expect-count',type=int,default=3935)
    args=p.parse_args()
    f=analyze(args)
    args.output.mkdir(parents=True,exist_ok=True)
    payload=safe(f)
    # Escape HTML metacharacters in JSON serialization as well, for safe script embedding.
    def write_json(name,obj):
        text=json.dumps(obj,ensure_ascii=False,indent=2).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
        (args.output/name).write_text(text+'\n',encoding='utf-8')
    write_json('findings.json',payload)
    write_json('dashboard.json',safe({'schema_version':1,'dataset':f['dataset'],'counts':{k:f['census'][k] for k in ('total','states','unique_authors','without_labels_percent','windows')},
        'reviewed':f['reviewed_issue_count'],'recommendations':f['recommendations'],
        'critical_gates':['tenant and credential custody','native tool/terminal outcome','rotating refresh under Redis failure','hard spend limits','DB restore and multi-process invalidation'],
        'pending_inputs':['4 focused tool-ID/session comment follow-ups and pagination-completeness assertion','normalized live operator receipts','test-only OAuth identity'],
        'live_e2e_status':'NOT RUN by audit lane','limitations':f['limitations']}))
    (args.output/'AUDIT.md').write_text(report(payload),encoding='utf-8')
    print(json.dumps({'issues':f['census']['total'],'reviewed':f['reviewed_issue_count'],'comments':f['comments']['status'],'output':str(args.output)},ensure_ascii=False))

if __name__ == '__main__':
    main()
