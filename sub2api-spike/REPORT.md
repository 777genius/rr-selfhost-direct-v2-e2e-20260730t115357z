# Sub2API: результат изолированного adoption spike

Завершено 2026-09-30 UTC / 2026-10-01 Europe/Kiev. Наш UI + workspace authorization остаются выбранной архитектурой. **Универсальный production cutover на Sub2API: NO-GO по текущим доказательствам.** Готовый движок полезен, но не снимает необходимость нашего OIDC, ownership, custody и проверки агентских протоколов.

## Короткий результат

| Сочетание | Настоящий GitHub Actions | Что доказано |
|---|---|---|
| Codex 0.159.2 + OpenRouter GPT-4.1 | [36775051456, SUCCESS](https://github.com/777genius/rr-selfhost-direct-v2-e2e-20260730t115357z/actions/runs/36775051456) | Раздельные reads кода/правил, financial finding, собственный numeric tool и независимое воспроизведение |
| Claude Code 2.1.285 + MiMo native Messages | [36775055709, SUCCESS](https://github.com/777genius/rr-selfhost-direct-v2-e2e-20260730t115357z/actions/runs/36775055709) | Настоящие Read, financial finding, successful terminal; числа перепроверил harness |
| Codex + MiMo native Responses | [36778603368, FAIL](https://github.com/777genius/rr-selfhost-direct-v2-e2e-20260730t115357z/actions/runs/36778603368) | Reads и два numeric tools выполнены, turn.completed есть, финальный assistant answer отсутствует, review.txt пуст. Подмена tool stdout финальным ответом запрещена |

Первые два SUCCESS относятся к harness `222c6d89900e06e38586100ca2d1cfb978a915a7`. Финальный MiMo FAIL и **45/45 контрактов** относятся к `f05e6a4f451a45681c0bbc7b4b0ced17199ff339`. Между ними добавлена фильтрация ошибочных SSE; здоровые frames сохраняются байтами и проверены контрактом. Живой повтор первых двух сочетаний на f05 не выполнялся: весь финальный код не объявляется live-proven.

Причина пустого MiMo результата не изолирована между provider, engine и client. Это наблюдаемая несовместимость конкретной цепочки, а не доказанное обвинение Sub2API. Автоматического платного retry не было.

Предыдущий MiMo [36775047872](https://github.com/777genius/rr-selfhost-direct-v2-e2e-20260730t115357z/actions/runs/36775047872) дал настоящий finding, но старый validator отверг валидный JSON array. Строгая поддержка array/object добавлена. Исходный Actions остаётся FAIL. [36777060737](https://github.com/777genius/rr-selfhost-direct-v2-e2e-20260730t115357z/actions/runs/36777060737) отменён до runner/provider после обнаружения custody проблемы. При setup engine автоматически отправил ещё два Responses probe; они учтены отдельно от четырёх запущенных canary.

## Что действительно проверили

- **77 сценариев:** 58 PASS на явно указанной границе, 5 FAIL, 14 NOT RUN/частично. Контрактный PASS не является production acceptance, доля строк не является процентом готовности. Полная [матрица](results.json).
- Два workspace в настоящем private admin API: CRUD/pause/export/delete, чужой account ID -> 404, member -> 403, sanitized metadata. Identity adapter тестовый; ReviewRouter SSO и готовый frontend здесь не интегрированы.
- Native Responses/Messages: multi-turn tool IDs, UTF-8, beta query, HTTP 400/401/403/404/429/500/502/503, failed/error terminal, malformed/truncated/reset/slow streams.
- После гарантированного partial stream (первые 5 frames + 150 ms flush barrier) upstream reset дал downstream failure, **1 upstream / 0 retry**. Ранняя fixture без flush barrier дала 2 attempts до доказанного stream commit; её FAIL сохранён, а не назван дубликатом после commit.
- Engine restart оборвал активный stream без дополнительного inference. PostgreSQL + Redis outage -> HTTP 500 / 0 upstream. После восстановления все четыре synthetic scopes снова работают с сохранёнными accounts/groups/keys.
- Отдельный networkless PostgreSQL restore: accounts 10, groups 10, keys 9, users 10, group links 8, migrations 289 совпали. Root-only dump удалён. Полная цепочка restored engine + stale capability NOT RUN; broker ledger отдельно сохраняет tombstones.
- Concurrency 1/5/20: 0 errors; для 20 p50=46 ms, p95=231 ms. Bounded 30 s soak: **485 запросов / 0 errors / 0 retries / 0 stuck**, p50=10 ms, p95=12 ms. Это local synthetic upstream, не provider SLA. Engine peak RSS не измерялся; после нагрузки 60.07 MiB, что не является peak.
- Медленный consumer получил 8.39 MB за 29.15 s, 1 upstream. Client RSS вырос на 27.68 MB; общий engine memory gate поэтому не повышен до PASS.
- Четыре полных residual runner filesystem exports, mounted work, Docker env/config/logs, private captures и четыре Actions logs: **zero matches настоящих MiMo/OpenRouter master keys**, ~9.93 GB / 99 052 runner files. После terminal snapshot; не continuous memory capture. Run-scoped capability/OIDC не считаются master keys.
- На runner bridge broker доступен, IP engine/admin/PostgreSQL/Redis недоступны. Host ports не публиковались. Docker socket/auth homes/master-key mounts в runner отсутствуют.

## Критические находки

1. **HTTP 200 SSE может содержать секрет в error body.** Через настоящий engine upstream с фиктивным API key смог вернуть его run client. Это воспроизведённый sentinel leak, не утечка настоящего ключа. После нашего native error fence тот же actual-engine тест PASS: ошибка сохранена, произвольный diagnostic удалён, sentinel отсутствует. Nonstream escape запрещён. Healthy frames/tool IDs не преобразуются. Private Sub2API logs/ops остаются отдельной custody поверхностью и могут содержать raw upstream errors.
2. **Cancel не равен stop spend.** Messages upstream не отменился за 1.2 s; Responses продолжал до 6 s и завершил stream. Source использует usage drain / WithoutCancel. Broker revoke/expiry не обещает мгновенную отмену inference через engine.
3. **Account create может оставить orphan authority.** При ambiguous response local binding скрыт через recovery_required, но remote account уже active/schedulable в рабочей группе. Для продукта нужны quarantine group без access keys, durable publication и reconciliation.
4. **Parent OIDC env доступен тому же UID.** Provider master key отсутствует, но agent может читать CI parent environment через procfs. Нужна отдельная PID/control boundary либо явно принятая модель угроз. Scoped run capability не является безвредным токеном: в пределах TTL/лимита она позволяет запросы.
5. **OAuth pool пока не доказан.** Test-only OAuth identity не предоставлена. Refresh, rotation, distributed locking, revoke/ban, encrypted history/account switching и Codex/Claude subscription canary NOT RUN. Production pool не импортировался и не заменялся.

JSONB/cache/export/backup не объявляются application-encrypted. Общую Sub2API admin UI нельзя отдавать workspace клиентам: наш server adapter обязан проверять владение и выдавать только положительную metadata projection.

## Независимый review и исправления

Hosted reviewer проверил исходный checkpoint `078fd409ef19ff71f6062030174bb2fb5c21f3be`, 4208 source/dependency files до/после без изменений, 8 socket-free reproductions и 6 pure contracts. Его [исходный отчёт](../sub2api-review/REPORT.md) сохранён. Он не является независимым review final f05.

| Finding | Итог |
|---|---|
| R01 Claude beta query; R02 mock protocol classification | Исправлены; настоящий Claude canary и native Messages PASS |
| R03 recursive business-field denial | Исправлен: routing restriction только top level, native nested business/tool schema сохраняется |
| R04 automatic create probe | Dummy admin test с provider egress disconnected; live model_mapping pinned, два probes отдельно учтены |
| R05 rules read / wrapper evidence | Исправлен; genuine rules read в successful Actions |
| R06 invalid partial-reset fixture | Отдельный native engine lab, flush barrier; committed-reset 1 upstream PASS |
| R07 parent OIDC env | Не исправлен; product isolation requirement |
| R08 SSE custody / private logs | Public boundary actual FAIL -> PASS; private log/ops custody остаётся |
| R09 incomplete provenance | Coordinator [full source manifest](evidence/source-manifest.json) включает transitive OIDC/evidence, fixture/rules, workflow/lab; реальные receipts привязаны к фактическому SHA. Старый generic receipt validator не считается acceptance gate |
| R10 cancel usage drain | Actual-engine FAIL; ограничение не скрыто |
| R11 ambiguous create orphan | Source finding подтверждён; production reconcile/quarantine не реализованы |

## Что показали issues

Полный gh CLI census: **3935 issues без PR**, 2600 open / 1335 closed. 52 тематических разбора; последние 30 releases. За 30 дней открыто 608 и закрыто 211, разные когорты; это не failure rate и не SLA. 99.644% issues без labels, счётчик bug labels не полезен как частота дефектов.

Риски: SSE200 errors, tool IDs/delegation, encrypted history при смене аккаунта, distributed OAuth refresh/Redis, accounting/budget reservation и DB restore/version compatibility. Закрытая issue не автоматически означает исправление.

Audit worker разобрал 48 threads / 66 comments; coordinator завершил ещё 4 threads / 14 comments, итог **52 / 80** с полной gh pagination. [Аудит](../sub2api-issues-audit/AUDIT.md), [дополнение](../sub2api-issues-audit/COORDINATOR-FOLLOWUP.md). [#6146](https://github.com/Wei-Shaw/sub2api/issues/6146) связан с merged [#6078](https://github.com/Wei-Shaw/sub2api/pull/6078) и соответствующим pinned source; custom-tool replay всё ещё требует отдельного canary. [#6402](https://github.com/Wei-Shaw/sub2api/issues/6402) delegation bootstrap нашим обычным review не покрыт.

## Решение и ориентир реализации

Сохранять существующий subscription-runtime Codex pool. Наш UI, ownership и OIDC использовать как стабильный внешний контракт; engine скрыть за небольшим server adapter. Подписочные OAuth accounts подключать отдельно после test-only lifecycle проверки. Не переносить сейчас весь пул в Sub2API.

| Путь | Оценка выбора | Оставшаяся реализация, грубо |
|---|---|---|
| Bifrost для native BYOK + наш UI/OIDC | 🎯 8/10 · 🛡️ 7/10 · 🧠 4/10 | 1200–2500 рабочих строк +600–1200 тестов; 5–10 рабочих дней |
| Sub2API для native BYOK + наши fences | 🎯 7/10 · 🛡️ 5/10 · 🧠 6/10 | 2000–4000 рабочих строк +1000–2000 тестов; 10–20 рабочих дней |
| Sub2API как новый multi-provider OAuth pool | 🎯 5/10 · 🛡️ 3/10 · 🧠 8/10 | 4000–8000 рабочих строк +2000–4000 тестов; 4–8 недель, зависит от test identities/upstream нюансов |

Это инженерные ordinal judgments и диапазоны, не измеренная вероятность отказа. Для Bifrost раньше прошли три genuine Actions ([MiMo Codex](https://github.com/777genius/rr-selfhost-direct-v2-e2e-20260730t115357z/actions/runs/36741594269), [OpenRouter Codex](https://github.com/777genius/rr-selfhost-direct-v2-e2e-20260730t115357z/actions/runs/36747901266), [MiMo Claude](https://github.com/777genius/rr-selfhost-direct-v2-e2e-20260730t115357z/actions/runs/36747904837)); аналогичный полный fault/custody набор там ещё не доказан. Поэтому рекомендация Bifrost опирается на agent compatibility, не на обещание бессрочной стабильности.

Спайк до f05: **2366 добавленных строк**, из них 1528 executable harness/lab/operator, 335 tests/support, 503 docs/config. Не production LOC. План commit 19:21 UTC, финальные execution/teardown ~21:38 UTC: около 2 ч 17 мин hosted работы плюс сборка отчёта. Четыре hosted workers: implementation high, issues medium, lab medium, independent review high, все gpt-6.1-sol. Первые платные canaries: 2/3 green; повтор MiMo terminal FAIL. Worker loopback test restriction отделён от реального server test result.

## Custody, версии и завершение

Sub2API **v0.2.11 @96f4c115c9749078f90cbf210a01d39baf3f53b6**, OCI image `weishaw/sub2api@sha256:2e3b7fab1e84d2e862cde664d09c1ae84fc897093357cf200cbeb0f64b2f2390`. PostgreSQL 18.6, Redis 8, Node 24.21.0, sealed runner image `sha256:f31d9fb67f3ae84ceac42acb1560c49105b9a9033ef7131bf154c5b12f9d3942`. Images pinned, runtime standard, no moving latest.

Owner approved isolated compliance commitment, acknowledgment HTTP200. Test-only HTTP/private upstream exception не является production config.

**Удалены только свои 9 containers /4 networks /23 private paths.** Original root-only MiMo/OpenRouter files сохранены с теми же inode/size/mtime, raw DB dump/captured agent homes/key copies удалены, свой Actions workflow disabled. Logical removal не обещает secure erasure физических snapshots. Production frontend/runtime не деплоились и pool не переносился. [Teardown receipt](evidence/operator/teardown.json).

Оригинальные FAIL, исправленные harness попытки и успешные receipts сохранены в [evidence](evidence/actions-history.json); raw transcripts/master keys/provider-key hashes туда не экспортировались. Browser report: `../sub2api-adoption-report.html`; execution plan: [PLAN.md](PLAN.md).
