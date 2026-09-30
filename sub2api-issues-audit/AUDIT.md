# Sub2API: аудит стабильности для ReviewRouter

BYOK и наша UI + private backend: **CONDITIONAL GO для изолированной проверки**, не production approval. OAuth pool: **NO-GO для production сейчас**; продолжить test-only spike. Источник решения — совместимость native agent lifecycle, custody, tenant boundaries и бюджетные ограничения, а не само число открытых issues.

Данные: **3935 non-PR**, 2600 open / 1335 closed; latest observed event **2026-09-30T18:24:51Z**. Точный capture timestamp не предоставлен. Расчётный cutoff = последний наблюдаемый event. Source v0.2.11, supplied pin `96f4c115c9749078f90cbf210a01d39baf3f53b6`; Git metadata недоступны, provenance pin не аутентифицирован независимо. 30 последних releases, не вся история. Машинный census полный по staged contract; вручную разобраны 52 целевых issues, не все 3935.

За 30 дней opened/closed: **608/211**, за 90: **2013/787**. Opened/day: 20.267 / 22.367; closed/day: 7.033 / 8.744. Это потоки разных когорт; повторные закрытия не видны, closure не означает fix. Без request denominator issue count нельзя перевести в failure rate.

Уникальных непустых author strings: **2315**; без labels **3921 (99.644%)**, всего assignments 14. Поэтому автоматическое отделение defect/support/enhancement/duplicate слабое. Версия обнаружена лишь как упоминание: данные `version_mentions` не являются установленной версией репортёра.

| Режим | Fragility /10 (хуже выше) | Уверенность | Решение |
|---|---:|---|---|
| BYOK native API | 5 | medium-low | CONDITIONAL GO for isolated validation; production gate pending |
| OAuth subscription pool | 8 | medium | NO-GO for production adoption now; continue test-only spike |
| Our UI + private backend | 6 | medium | CONDITIONAL GO as chosen topology; production boundary gate pending |

Оценки порядковые, не вероятность отказа. BYOK исключает refresh/ban lifecycle pool, но не SSE false-green и tool integrity. Наша UI уменьшает открытый admin surface только при собственном ownership ledger и capability checks; добавляет adapter/cache сложность. OAuth дополнительно зависит от provider policy, token rotation, quota и переносимости encrypted history.

## Критические adoption gates

- **Tenant/custody:** C02/C05/C07/D04/D06/D07. Group routing не доказывает ownership account; JSONB credential map и Redis projection не дают оснований обещать application encryption. Admin/export/backup только operator; UI выдаёт filtered DTO, runner получает короткую capability. #3086 — слабый historical report, #6169/#6112 — конкретные source risks, не исполненные exploits.
- **False-green/native tools:** A01–A10/E02–E04/E10–E11. #7285 показывает reported HTTP 200 без настоящих tools; #7708 — ошибка внутри SSE 200; #7506 — encrypted history при смене account. Требуются реальные Codex/Claude reads, tool IDs/results и terminal outcome. Ни MiMo, ни OpenRouter E2E здесь не доказан.
- **Refresh/scheduling:** F02–F06/G01/G06. Unified refresh и RPM projection уже имеют source mitigations; Redis lock failure деградирует до local mutex. Pause/sticky и account-change encrypted state требуют transport/lifecycle proof, двух процессов и failure injection.
- **Hard budget:** H05/E06/E11/G05. v0.2.11 reservation — значимое улучшение concurrent admission, но estimation, unpriced/Redis fail-open и final overdraft сохраняют риски. ReviewRouter должен иметь собственный atomic budget/run cap и не выдавать engine balance за строгий финансовый лимит. Built-in payments/refunds не нужны нашему UI.
- **Recovery/upgrades:** G01–G04/G07. Cloned DB restore вместе с schema_migrations, readiness delay, restart active stream, bounded RSS. #7030 относится к потере migration ledger/partial restore; не ко всем обычным upgrades.

## Release patterns и maintenance

В latest-30 окне 68.884 дня, средний gap 2.375 дня, 11 release за последние 30 дней. Release notes активно закрывают protocol/billing/scheduler gaps; это maintenance signal и большой change surface, не доказательство SLA. Sponsor text/stars не используются как reliability evidence.

- v0.2.11: default-enabled inflight balance reservation; upgrade меняет admission low-balance concurrency. Проверить estimate/actual, unpriced, Redis failure, subscription bypass и cancel handoff. Новое #7770 относится к той же v0.2.11: compounded tier accounting остаётся reported risk.
- v0.2.9: structured-output beta и role-item conversion; #7633/#7629 совпадают с release claims. #7700/#7708/#7506 показывают иные формы encrypted errors, не опровергаемые этими fix claims.
- v0.2.8: RPM metadata projection, previous_response affinity и завершение stream на terminal event. #7225 получает scoped release/source/test corroboration; #7758 демонстрирует другую отсутствующую пару полей, её нельзя считать исправленной заодно.
- v0.2.4: persistent cooldown/runtime block semantics (#6319 related); v0.1.179: long-context pricing gating AND→OR, после upgrade меняется price и нужен config review.
- v0.1.172: release прямо заявляет regression quota reset, введённую v0.1.170. v0.1.182: release claim исправления duplicate cache-create accounting. Данные показывают реальные категории churn, но не частоту сбоев на наших workloads.

## Лицензия, границы и недостающая информация

LICENSE содержит LGPL v3; README указывает v3 или позже. Зафиксировать notices/изменения и проверить обязанности выбранного способа распространения/linking отдельно; это не юридическое заключение. Browser OIDC реализует human login/bind/registration, не наши GitHub Actions claims. Нельзя переносить существующий production subscription pool в этот эксперимент.

Comments: **SUPPLIED and interpreted; completeness bounded to snapshot counts**. Ранний `NEEDED-COMMENTS.json` содержит 52 приоритетных номера (лимит 60), URL, категории и причины. Первый batch (48 issues) получен; ещё 4 focused tool-ID/session issues добавлены в запрос. Формат staging описан в README. Первоначальный batch из 66 comments прочитан: NONE=56, CONTRIBUTOR=10, OWNER/MEMBER/COLLABORATOR отсутствуют. Counts первого batch совпадают со snapshot по всем 48 issues; pagination-complete assertion отдельно не предоставлен. Нет maintainer-confirmed fix; есть scoped reporter/release/source corroboration, особенно #7633. #6877 после comments исключён как likely off-project support. Live operator receipts и test OAuth identity остаются pending input; это не мешает завершить данный offline audit.

## Приложение: воспроизводимый census

| Age, elapsed days | Open since creation | Closed since creation | Closed time-to-close |
|---|---:|---:|---:|
| 0–7 | 89 | 18 | 1109 |
| 8–30 | 380 | 142 | 139 |
| 31–90 | 824 | 581 | 58 |
| 91–180 | 887 | 319 | 26 |
| 181+ | 420 | 275 | 3 |

Buckets: [0,8), [8,31), [31,91), [91,181), [181,∞). Closed age и time-to-close измеряют разные величины. Current state/last closed_at не восстанавливают event history.

| Keyword category (overlapping candidates only) | Count | Open | Closed |
|---|---:|---:|---:|
| native_protocols | 974 | 556 | 418 |
| oauth_provider | 814 | 512 | 302 |
| scheduling | 578 | 352 | 226 |
| security_custody | 218 | 132 | 86 |
| billing | 361 | 219 | 142 |
| deployment | 538 | 323 | 215 |

Heuristic issue kinds: defect_candidate=566, duplicate_candidate=2, enhancement_candidate=447, mixed_defect_enhancement_candidate=10, support_question_candidate=198, unclassified=2712. Unclassified не означает absence of defect; explicit duplicate label крайне редок/отсутствует, текстовый match не даёт deduplication.

Top explicit version mentions (может быть affected/fixed/requested version, overlap): v0.1.171: 30, v0.2.4: 30, v0.1.125: 23, v0.2.5: 20, v0.1.173: 19, v0.1.179: 19, v0.1.183: 19, v0.1.161: 17, v0.1.165: 17, v0.1.126: 16, v0.1.170: 16, v0.2.0: 16, v0.1.133: 15, v0.1.177: 14, v0.1.178: 14. Без такого упоминания: 3230.

## Приложение: 52 содержательных разборов

Purposive sample по шести risk domains, open/closed и recent regressions. Это не случайная выборка и не оценка prevalence. Inspected supplied narrative/metadata; screenshots/video не просмотрены. Config/credential блоки не публикуются. Каждый пункт — reported evidence + next observable boundary; ни один failure здесь независимо не воспроизведён. `release_source_fix_support` означает scoped corroboration, не maintainer/live подтверждение.

### [#7774](https://github.com/Wei-Shaw/sub2api/issues/7774) — open; state_reason=null

Reporter version: v0.2.4–v0.2.11 (reporter). Kind: defect_report; attribution: engine_provider_interaction; assessment: active_report; snapshot comments: 0.

Grok Responses: пустой completed без output/usage принят клиентом как успех. Репортёр связывает это с платформенным условием защиты OpenAI; нестабильность upstream и отсутствие защиты шлюза различаются.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** A06/E02/E10: пустой completed не доказывает review; проверить committed heartbeat, запрет повторного платного эффекта.

### [#7708](https://github.com/Wei-Shaw/sub2api/issues/7708) — open; state_reason=null

Reporter version: v0.2.4. Kind: defect_report; attribution: engine_provider_interaction; assessment: active_report; snapshot comments: 1.

HTTP 200 содержит SSE invalid_encrypted_content для encrypted function output; очистка reasoning при HTTP 400 не охватывает этот случай. Первая причина порчи истории неизвестна.

**Comments:** Дополнительный репортёр видит ту же ошибку и на Astra; переключение Sol→Astra не является общим fix.

Comment citations: [5891056628](https://github.com/Wei-Shaw/sub2api/issues/7708#issuecomment-5891056628) (NONE)

**Наблюдаемая проверка:** A04/E02/E11: ошибка внутри 200 должна завершить review неуспехом; сохранить tool results, ограничить replay.

### [#7700](https://github.com/Wei-Shaw/sub2api/issues/7700) — open; state_reason=null

Reporter version: v0.2.4. Kind: defect_report; attribution: engine_provider_interaction; assessment: active_report; snapshot comments: 2.

Codex multi-turn: HTTP 400 thinking_signature_invalid, повторное продолжение снова ломается. Минимальный стабильный reproducer отсутствует; упомянутое расширение распознавания ошибки не равно доказанному восстановлению.

**Comments:** Комментарий об обходе через Astra и contributor о thinking не дают root-cause/fix proof; #7708 ограничивает применимость обхода.

Comment citations: [5884938013](https://github.com/Wei-Shaw/sub2api/issues/7700#issuecomment-5884938013) (NONE), [5885868290](https://github.com/Wei-Shaw/sub2api/issues/7700#issuecomment-5885868290) (CONTRIBUTOR)

**Наблюдаемая проверка:** A04/E01/E11: отличать 400 от SSE 200, не удалять нормальные инструменты и не повторять бесконечно.

### [#7633](https://github.com/Wei-Shaw/sub2api/issues/7633) — closed; state_reason=completed

Reporter version: v0.2.8. Kind: defect_report; attribution: engine; assessment: release_source_fix_support; snapshot comments: 1.

OAuth Messages теряет structured-output beta при legacy output_format; репортёр приводит API-key контроль и рабочий output_config.format. v0.2.9 заявляет сохранение beta; соответствующий request-boundary тест присутствует, но здесь не запускался.

**Comments:** Репортёр заявляет live OAuth A/B v0.2.8→v0.2.9, три модели и JSON schemas. Вместе с release/source это сильное scoped fix corroboration, но не наш normalized operator receipt и не maintainer confirmation.

Comment citations: [5864591789](https://github.com/Wei-Shaw/sub2api/issues/7633#issuecomment-5864591789) (NONE)

**Наблюдаемая проверка:** A06/A09: проверить фактический beta header и JSON в native Messages, без fallback к платному маршруту.

### [#7629](https://github.com/Wei-Shaw/sub2api/issues/7629) — closed; state_reason=completed

Reporter version: build based on v0.2.8. Kind: defect_report; attribution: engine; assessment: release_fix_claim; snapshot comments: 0.

Chat→Responses не ставит type=message у role input; StepFun отвергает историю с 400. Репортёр заявляет локальный контроль; v0.2.9 описывает исправление role items. Это мост, а не разрешение заменить наш native lane.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** A04/A07: отдельно проверять bridge, native tool IDs и запрет тихой смены протокола.

### [#7637](https://github.com/Wei-Shaw/sub2api/issues/7637) — closed; state_reason=completed

Reporter version: not reported. Kind: defect_report; attribution: engine_provider_interaction; assessment: closed_unverified; snapshot comments: 0.

Antigravity буферизует thoughtSignature/message_start до смыслового вывода; при большой картинке TTFT больше 30 секунд клиент отключается. Закрытие completed само по себе не доказывает keepalive fix.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** A10/E05/E06/E10: bounded TTFT, cancellation; heartbeat не разрешает поздний failover.

### [#7285](https://github.com/Wei-Shaw/sub2api/issues/7285) — open; state_reason=null

Reporter version: Sub2API not reported; Codex 0.154. Kind: defect_report; attribution: provider_compatibility; assessment: active_report; snapshot comments: 6.

DeepSeek принимает Responses additional_tools с 200, но игнорирует их: shell не исполняется, вызов появляется текстом. HTTP capability probe недостаточен; рабочий chat bridge у репортёра зависит от других патчей.

**Comments:** Комментарии уточняют trigger: GPT alias заставляет Codex использовать Responses Lite, native DeepSeek name — top-level tools; другой репортёр воспроизводит на v0.2.7. Direct upstream nested-vs-flat tools даёт дополнительный semantic mismatch, отдельно от Sub2API E2E.

Comment citations: [5718786211](https://github.com/Wei-Shaw/sub2api/issues/7285#issuecomment-5718786211) (CONTRIBUTOR), [5748964123](https://github.com/Wei-Shaw/sub2api/issues/7285#issuecomment-5748964123) (NONE), [5864884211](https://github.com/Wei-Shaw/sub2api/issues/7285#issuecomment-5864884211) (NONE)

**Наблюдаемая проверка:** A01/A02/A04/A07: реальное чтение файлов и исполнение tool, честный отказ unsupported; не считать текст tool-call событием.

### [#4245](https://github.com/Wei-Shaw/sub2api/issues/4245) — closed; state_reason=completed

Reporter version: not reported. Kind: defect_report; attribution: engine_configuration; assessment: closed_unverified; snapshot comments: 0.

Root /responses работает, но /models отдаёт HTML/404, Codex использует bundled metadata. Репортёр описывает A/B с ETag и cache; /v1 является обходом, не доказательством общего исправления.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** A09: проверить /models content type, ETag, auth и group isolation вместе с native inference.

### [#5542](https://github.com/Wei-Shaw/sub2api/issues/5542) — open; state_reason=null

Reporter version: v0.1.173; latest tag also mentioned. Kind: defect_report; attribution: engine_provider_interaction; assessment: active_report; snapshot comments: 5.

OpenAI OAuth 401 переводит единственный аккаунт в unschedulable, клиент получает 502; ручной refresh восстанавливает запрос. Privacy 403 отделён от inference 401; автоматическое обновление на pin не проверено.

**Comments:** Follow-up приводит inference 401→502→subsequent 503; другие жалуются на частоту. IP-гипотеза не проверена, fleet frequency из комментариев не выводится.

Comment citations: [5261593013](https://github.com/Wei-Shaw/sub2api/issues/5542#issuecomment-5261593013) (NONE), [5288559219](https://github.com/Wei-Shaw/sub2api/issues/5542#issuecomment-5288559219) (NONE), [5288613054](https://github.com/Wei-Shaw/sub2api/issues/5542#issuecomment-5288613054) (NONE), [5288624028](https://github.com/Wei-Shaw/sub2api/issues/5542#issuecomment-5288624028) (NONE), [5351767369](https://github.com/Wei-Shaw/sub2api/issues/5542#issuecomment-5351767369) (NONE)

**Наблюдаемая проверка:** F04/F05/E09: revoked/expired token, bounded refresh и reconnect; не переносить бесконтрольно запрос на другой pool.

### [#1381](https://github.com/Wei-Shaw/sub2api/issues/1381) — open; state_reason=null

Reporter version: v0.1.105. Kind: support_or_weak_report; attribution: unknown_provider_or_engine; assessment: unknown; snapshot comments: 0.

Короткий invalid_grant без шагов и логов гонки. Заголовок про конкуренцию refresh — гипотеза, не установленная причина; комментариев нет.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** F04/F05: single-use refresh при конкурентных background/request обновлениях, без утверждения воспроизведения issue.

### [#1035](https://github.com/Wei-Shaw/sub2api/issues/1035) — closed; state_reason=completed

Reporter version: v0.1.95; commit 3cc407bc. Kind: defect_report; attribution: engine; assessment: source_mitigation_support; snapshot comments: 1.

Репортёр описывает разные lock paths background и inline Claude refresh, потребляющие одноразовый token. На supplied pin обе ветви используют OAuthRefreshAPI с reread и общим lock; Redis failure всё ещё деградирует до local mutex.

**Comments:** Contributor пишет, что исправление в работе; обещание не доказывает merge или deployed fix. Unified API на supplied source — отдельное mitigation evidence.

Comment citations: [4063204907](https://github.com/Wei-Shaw/sub2api/issues/1035#issuecomment-4063204907) (CONTRIBUTOR)

**Наблюдаемая проверка:** F04/G01: два процесса + Redis outage + rotating refresh; local mutex не обеспечивает межпроцессную исключительность.

### [#4414](https://github.com/Wei-Shaw/sub2api/issues/4414) — closed; state_reason=completed

Reporter version: v0.1.156 (title). Kind: support_or_weak_report; attribution: unknown_provider_or_engine; assessment: closed_unverified; snapshot comments: 0.

Лишь 502 с сообщением reused refresh token; ни таймлайна конкуренции, ни подтверждённого patch. Закрыто completed, но причинная связь с #1035 не установлена.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** F04/F05: повторное потребление одноразового refresh должно остановить аккаунт и требовать reconnect.

### [#3757](https://github.com/Wei-Shaw/sub2api/issues/3757) — closed; state_reason=completed

Reporter version: v0.1.145; latest tag mentioned. Kind: defect_report; attribution: engine_configuration_protocol_interaction; assessment: closed_unverified; snapshot comments: 8.

Antigravity exchange/refresh успешны, inference по нескольким путям всё равно 401. Scope, endpoint, project ID и stale cache не разделены контролем; refresh HTTP 200 не доказывает работоспособный identity.

**Comments:** Follow-up v0.1.145 показывает upstream /messages и Google token, контроль через иной gateway; suggested /antigravity/v1beta и fork — routing workaround, не maintainer pin fix. Позднее уточнение меняет attribution с неизвестного refresh на likely protocol/config routing interaction.

Comment citations: [4980981007](https://github.com/Wei-Shaw/sub2api/issues/3757#issuecomment-4980981007) (NONE), [5048566740](https://github.com/Wei-Shaw/sub2api/issues/3757#issuecomment-5048566740) (NONE), [5077635894](https://github.com/Wei-Shaw/sub2api/issues/3757#issuecomment-5077635894) (NONE), [5083809087](https://github.com/Wei-Shaw/sub2api/issues/3757#issuecomment-5083809087) (CONTRIBUTOR)

**Наблюдаемая проверка:** F05/F08: после refresh наблюдать upstream identity и реальный native запрос, не только admin success.

### [#3707](https://github.com/Wei-Shaw/sub2api/issues/3707) — closed; state_reason=completed

Reporter version: around v0.1.144; commit b650bdd6. Kind: defect_report; attribution: engine_provider_interaction; assessment: closed_unverified; snapshot comments: 0.

Отозванный до expires_at token может не попасть в refresh; прежний patch лечил eligibility, не expiry gate. Репортёр честно отделяет source inference от live проверки токена; закрытие не разрешает считать весь lifecycle исправленным.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** F05/E09: revoke до expiry, cache/snapshot invalidation и bounded recovery.

### [#3647](https://github.com/Wei-Shaw/sub2api/issues/3647) — closed; state_reason=completed

Reporter version: v0.1.142. Kind: defect_report; attribution: engine; assessment: closed_unverified; snapshot comments: 0.

Codex Session imports разных account в одном workspace совпадают по workspace/user identity и обновляют первый account. Репортёр заявляет локальный token-fingerprint patch; это не maintainer fix evidence.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** C06/C08: два test identity в одном provider workspace не сливаются; импорт после delete не оживляет чужое binding.

### [#7000](https://github.com/Wei-Shaw/sub2api/issues/7000) — open; state_reason=null

Reporter version: not reported. Kind: support_question; attribution: provider_policy; assessment: provider_dependence; snapshot comments: 6.

Вопрос о настройке Codex fingerprint для снижения банов, тело только screenshot. Не доказаны ни ban incident, ни эффективность маскировки; официальная политика провайдера остаётся независимой зависимостью.

**Comments:** Мнения об эффективности fingerprint противоречат друг другу; нет измерений ban risk. Provider dependence остаётся unknown, не установленная gateway уязвимость.

Comment citations: [5629041756](https://github.com/Wei-Shaw/sub2api/issues/7000#issuecomment-5629041756) (NONE), [5629580082](https://github.com/Wei-Shaw/sub2api/issues/7000#issuecomment-5629580082) (NONE), [5630188143](https://github.com/Wei-Shaw/sub2api/issues/7000#issuecomment-5630188143) (NONE), [5630798439](https://github.com/Wei-Shaw/sub2api/issues/7000#issuecomment-5630798439) (NONE), [5632154268](https://github.com/Wei-Shaw/sub2api/issues/7000#issuecomment-5632154268) (NONE), [5633899226](https://github.com/Wei-Shaw/sub2api/issues/7000#issuecomment-5633899226) (NONE)

**Наблюдаемая проверка:** F07/E09: test-only identity, ban/revoke выдаёт честный отказ; не обещать отсутствие блокировок.

### [#7758](https://github.com/Wei-Shaw/sub2api/issues/7758) — open; state_reason=null

Reporter version: v0.2.10; commit 2f3fed2fd. Kind: defect_report; attribution: engine; assessment: source_risk_support; snapshot comments: 0.

Scheduler metadata теряет capability/base_url: Seedance фильтруется, ограниченный embeddings account может считаться универсальным. На supplied source whitelist не содержит обоих полей; это source corroboration, не исполненный seedance reproducer.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** A07/C05/F01: production cache roundtrip сохраняет eligibility и выбранный разрешённый upstream.

### [#7757](https://github.com/Wei-Shaw/sub2api/issues/7757) — open; state_reason=null

Reporter version: not reported. Kind: defect_report; attribution: engine; assessment: active_report; snapshot comments: 0.

Antigravity /responses не закрепляет account по session_id, тогда как другие платформы в том же OpenWebUI работают. PR обещан репортёром; merge/transport proof отсутствует.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** A04/F02: разные multi-turn sessions, distinct upstream sentinels, affinity по Responses.

### [#7574](https://github.com/Wei-Shaw/sub2api/issues/7574) — open; state_reason=null

Reporter version: not reported. Kind: defect_report; attribution: engine; assessment: active_report; snapshot comments: 1.

Pause единственного OpenAI account не останавливает назначения прежней sticky-сессии; concurrency=3, fingerprint device+session. Не ясно, относятся ли screenshots к новым запросам или уже открытой работе.

**Comments:** Репортёр уточняет: два-три subsequent turns, потом восстановилось. Cache задержка вероятнее, чем только старый in-flight stream, но root cause по-прежнему не доказан.

Comment citations: [5810527933](https://github.com/Wei-Shaw/sub2api/issues/7574#issuecomment-5810527933) (NONE)

**Наблюдаемая проверка:** F06/C04: отличить in-flight stream от нового turn после disable и проверить новый admission.

### [#7506](https://github.com/Wei-Shaw/sub2api/issues/7506) — open; state_reason=null

Reporter version: v0.2.7-based; Codex 0.154.0. Kind: defect_report; attribution: engine_provider_interaction; assessment: active_report; snapshot comments: 1.

Encrypted agent_message от backend A не переносится на B/C при смене account. Репортёр показывает ограничения своих контролей; plain-text 3×3 не доказывает native lifecycle. Молчаливое удаление истории недопустимо.

**Comments:** Автор прямо уточняет: #7520 closed unmerged, локальный Codex с scripted fake upstream доказывает только plaintext self-message. Реальный encrypted cross-account/model lifecycle и recovery не проверены этим prototype.

Comment citations: [5788247041](https://github.com/Wei-Shaw/sub2api/issues/7506#issuecomment-5788247041) (NONE)

**Наблюдаемая проверка:** A04/F02/E10/E11: реальная encrypted collaboration история, failover и продолжение; запрет false-green от plaintext fixture.

### [#7225](https://github.com/Wei-Shaw/sub2api/issues/7225) — open; state_reason=null

Reporter version: v0.2.4. Kind: defect_report; attribution: engine; assessment: release_source_fix_support; snapshot comments: 0.

Anthropic RPM=10 пропадает в sched:meta, reported 28–29 forwards/min. v0.2.8 release и source сохраняют три RPM поля; upstream test проверяет schedulability после projection, но ещё нужен live cache admission.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** F03/G05: Redis serialization плюс фактический request count, не проверка наличия поля alone.

### [#7458](https://github.com/Wei-Shaw/sub2api/issues/7458) — open; state_reason=null

Reporter version: v0.2.5; v0.2.7/main inspected by reporter. Kind: defect_report; attribution: engine_provider_interaction; assessment: active_report; snapshot comments: 1.

Role-only SSE commit запрещает failover при последующем overloaded, особенно для тела меньше 64KB. Числа 48h принадлежат одному репортёру, не fleet failure rate; семантический stream commit важнее HTTP status.

**Comments:** Комментарий не содержит технического подтверждения или исправления.

Comment citations: [5760836498](https://github.com/Wei-Shaw/sub2api/issues/7458#issuecomment-5760836498) (NONE)

**Наблюдаемая проверка:** E02/E10/E11: early role/heartbeat, overload до и после output; считать реальные upstream effects.

### [#6992](https://github.com/Wei-Shaw/sub2api/issues/6992) — open; state_reason=null

Reporter version: main 96e440… (reporter); no release version. Kind: enhancement_with_defect_hypothesis; attribution: engine_design; assessment: design_tradeoff; snapshot comments: 1.

Sticky account при saturation получает WaitPlan, свободный второй account простаивает. Soft sticky помогает throughput, но encrypted/previous_response state может запретить миграцию; предложенные изменения — требования, не измеренная регрессия pin.

**Comments:** Дополнительный reporter experiment v0.2.4: 50 non-sticky DeepSeek requests, высокая очередь при concurrency=5; fresh-load retry предложен. Числа относятся к чужому workload, не нашему soak; расширить тест и на general scheduler, не только OpenAI sticky.

Comment citations: [5654946776](https://github.com/Wei-Shaw/sub2api/issues/6992#issuecomment-5654946776) (NONE)

**Наблюдаемая проверка:** F02/F03/G05: bounded queue, cancellation release, одновременно affinity и fairness для переносимых запросов.

### [#6319](https://github.com/Wei-Shaw/sub2api/issues/6319) — closed; state_reason=completed

Reporter version: not reported. Kind: defect_report; attribution: engine; assessment: release_fix_claim; snapshot comments: 0.

Clear runtime block только в одном процессе; другой экземпляр ждёт прежнего cooldown. v0.2.4 говорит о persistent cooldown как источнике истины; DB failure containment нужно проверить отдельно.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** F01/G01/G06: reset account в процессе A, admission в B и затем потеря DB.

### [#6169](https://github.com/Wei-Shaw/sub2api/issues/6169) — open; state_reason=null

Reporter version: v0.1.181 and earlier (reporter). Kind: security_report; attribution: engine; assessment: source_risk_support; snapshot comments: 0.

Image download URL потенциально позволяет private/metadata fetch. Supplied helper делает Get(downloadURL) без локального validator; достижимость входа, shared client transport и redirects требуют boundary проверки. Публичный severity репортёра не заменяет exploit proof.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** D07/B12: deny images и arbitrary URLs на нашем broker; DNS/redirect/private target тесты перед включением.

### [#6112](https://github.com/Wei-Shaw/sub2api/issues/6112) — open; state_reason=null

Reporter version: v0.1.179 (reporter). Kind: security_report; attribution: engine_configuration; assessment: source_risk_support; snapshot comments: 0.

Legacy forwarded-IP режим доверяет CF-Connecting-IP впереди nginx headers. Source default=true, legacy precedence сохранён; trusted proxy mode и stripping на private edge обязательны. Ни brute force, ни эксплуатация здесь не запускались.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** B12/D04: spoof CF/XFF с runner не меняет authorization; edge strips headers, explicit trusted proxies.

### [#3086](https://github.com/Wei-Shaw/sub2api/issues/3086) — closed; state_reason=completed

Reporter version: not reported. Kind: security_report; attribution: unknown_engine_or_configuration; assessment: closed_unverified; snapshot comments: 1.

Пользователь будто использует private group без permission после public→exclusive. Только screenshots и предположение; cache invalidation или существующий API-key binding не установлены, closure не доказательство tenant isolation.

**Comments:** Contributor подтверждает retained binding после public→private: ранее выбранная группа сохраняется у user. Это конкретная permission semantics, не доказанный arbitrary tenant exploit. Нужен revoke-old-key/group test.

Comment citations: [4642060429](https://github.com/Wei-Shaw/sub2api/issues/3086#issuecomment-4642060429) (CONTRIBUTOR)

**Наблюдаемая проверка:** C02/C05/C09: revoke group membership, старый key и новый grant, наблюдать forbidden upstream sentinel.

### [#6548](https://github.com/Wei-Shaw/sub2api/issues/6548) — open; state_reason=null

Reporter version: not reported. Kind: enhancement_with_defect_hypothesis; attribution: engine_design; assessment: active_report; snapshot comments: 1.

No available accounts возвращает внутреннюю причину и 503 api_error вместо ожидаемого overload. Это раскрытие topology и возможное усиление retries, но не доказанная утечка credential bytes.

**Comments:** Согласие с configurable message; нет fix/security evidence.

Comment citations: [5535973650](https://github.com/Wei-Shaw/sub2api/issues/6548#issuecomment-5535973650) (NONE)

**Наблюдаемая проверка:** D02/D08/E01: provider error с synthetic secret, sanitization и bounded retries клиента.

### [#4469](https://github.com/Wei-Shaw/sub2api/issues/4469) — open; state_reason=null

Reporter version: new version; not specified. Kind: enhancement; attribution: security_control_design; assessment: design_tradeoff; snapshot comments: 2.

Просьба убрать 2FA перед account export. Наличие неудобства не означает vulnerability; для privatebackend export должен остаться operator-only и не попадать в UI.

**Comments:** Комментарии спорят с обязательным 2FA export; не evidence дефекта. Наш private backend не открывает export UI.

Comment citations: [5001329779](https://github.com/Wei-Shaw/sub2api/issues/4469#issuecomment-5001329779) (NONE), [5005022807](https://github.com/Wei-Shaw/sub2api/issues/4469#issuecomment-5005022807) (NONE)

**Наблюдаемая проверка:** C03/C07/D06: member/UI не экспортирует credentials, admin boundary отдельно.

### [#4002](https://github.com/Wei-Shaw/sub2api/issues/4002) — closed; state_reason=completed

Reporter version: not reported. Kind: support_or_weak_report; attribution: unknown_configuration_or_engine; assessment: historical_reporter_fix_claim; snapshot comments: 5.

Backup S3 снова работает после повторной установки secret, ломается после update. Потеря persistence только гипотеза; нет доказательств утечки или установленного хранения этого secret.

**Comments:** Повторные reporter observations persistent secret loss и TOTP save workaround; последний комментатор заявляет исправление v0.1.164. Это historical reporter fix claim, без maintainer/source mapping; не делать current-critical без pin reproducer.

Comment citations: [4954097417](https://github.com/Wei-Shaw/sub2api/issues/4002#issuecomment-4954097417) (NONE), [4992884819](https://github.com/Wei-Shaw/sub2api/issues/4002#issuecomment-4992884819) (NONE), [5001013031](https://github.com/Wei-Shaw/sub2api/issues/4002#issuecomment-5001013031) (NONE), [5011656263](https://github.com/Wei-Shaw/sub2api/issues/4002#issuecomment-5011656263) (NONE), [5057040012](https://github.com/Wei-Shaw/sub2api/issues/4002#issuecomment-5057040012) (NONE)

**Наблюдаемая проверка:** G04/D06/D09: separate-instance backup/restore, custody ключей и переживание обновления.

### [#3712](https://github.com/Wei-Shaw/sub2api/issues/3712) — open; state_reason=null

Reporter version: not reported. Kind: support_or_weak_report; attribution: engine_configuration; assessment: unknown; snapshot comments: 0.

Первый human OIDC login требует email verification при выключенном флаге. Это пользовательская регистрация с invite, не GitHub Actions issuer/audience/workflow authorization.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** H06/B01–B07: наш verifier проверяет signed workload claims отдельно от встроенного human SSO.

### [#6610](https://github.com/Wei-Shaw/sub2api/issues/6610) — open; state_reason=null

Reporter version: not reported. Kind: support_or_weak_report; attribution: unknown_security_incident; assessment: unknown; snapshot comments: 3.

Автор сообщает о множестве атак и денежных потерях, но детали находятся в screenshots/video. Не удалось установить attack vector или связь с engine; это приоритет triage, не подтверждённый breach.

**Comments:** Комментарии предполагают login brute force и отдельно quota расход; компрометация/двойная тарификация не установлены. Закрытый admin edge — конкретная защита; alarming anecdotes не доказательство breach.

Comment citations: [5547690483](https://github.com/Wei-Shaw/sub2api/issues/6610#issuecomment-5547690483) (NONE), [5549067751](https://github.com/Wei-Shaw/sub2api/issues/6610#issuecomment-5549067751) (NONE), [5564368532](https://github.com/Wei-Shaw/sub2api/issues/6610#issuecomment-5564368532) (NONE)

**Наблюдаемая проверка:** C02/D04/D08: закрытый admin network, workspace capability и аудит без credentials.

### [#7770](https://github.com/Wei-Shaw/sub2api/issues/7770) — open; state_reason=null

Reporter version: v0.2.11; reported exact requested pin. Kind: defect_report; attribution: engine_design; assessment: source_risk_support; snapshot comments: 0.

Две Sub2API цепочки учитывают priority/default по-разному: OAuth сохраняет priority, внешний API-key снижает tier. Reported paired ledgers не являются официальным provider bill; существующие отдельные unit rules не покрывают compositional consistency.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** H05/E11: tier propagation при chained proxy, trusted metadata и exact-once debit; не доверять caller price.

### [#7205](https://github.com/Wei-Shaw/sub2api/issues/7205) — open; state_reason=null

Reporter version: not reported. Kind: defect_report; attribution: unknown_engine_or_provider; assessment: active_report; snapshot comments: 2.

После sticky failover входные token якобы учитываются как cache и занижают цену. Объяснение AI и screenshots не доказывают причину; нужны authoritative usage и ledger pairs.

**Comments:** Contributor предлагает max_account_switches=1 как mitigation, не fix; общий негативный отзыв не используется для оценки failure rate. Проверять перенос cache accounting при failover.

Comment citations: [5709933445](https://github.com/Wei-Shaw/sub2api/issues/7205#issuecomment-5709933445) (CONTRIBUTOR), [5714218242](https://github.com/Wei-Shaw/sub2api/issues/7205#issuecomment-5714218242) (NONE)

**Наблюдаемая проверка:** H05/E10/E11: смена account с разными cache counters, actual debit и upstream count.

### [#7002](https://github.com/Wei-Shaw/sub2api/issues/7002) — open; state_reason=null

Reporter version: not reported. Kind: defect_report; attribution: engine_design; assessment: partial_mitigation_remaining_risk; snapshot comments: 0.

Long stream допущен по положительному balance, финальная сумма уводит в минус. v0.2.11 добавляет inflight reservation; source всё ещё допускает final overdraft и unpriced fail-open. Это существенная mitigation, не доказанный hard spend cap.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** H05/G01/G05/E06: неизвестная цена, actual&gt;estimate, long stream, Redis loss, multi-request final debit.

### [#5188](https://github.com/Wei-Shaw/sub2api/issues/5188) — open; state_reason=null

Reporter version: main c043c247 (reporter). Kind: defect_report; attribution: engine; assessment: source_mitigation_support; snapshot comments: 0.

Refund pending/restart race: repeated refund, double deduction, lost finalize. На supplied source stale-caller и rollback-after-debit DB tests существуют; это покрывает часть заявлений, не весь payment-provider crash lifecycle.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** H05/G02: не включать встроенный payment/refund в наш UI; если понадобится, crash/reconcile и single debit отдельно.

### [#6515](https://github.com/Wei-Shaw/sub2api/issues/6515) — open; state_reason=null

Reporter version: not reported. Kind: defect_report; attribution: engine; assessment: active_report; snapshot comments: 0.

Messages upstream billing_model_source будто выбирает requested Model вместо UpstreamModel. Репортёр сравнивает OpenAI путь; наличие выбора в UI не доказывает его использование во всех native paths.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** H05/A05: model mapping меняет actual upstream identity и цену, не caller-controlled billing override.

### [#6646](https://github.com/Wei-Shaw/sub2api/issues/6646) — closed; state_reason=completed

Reporter version: not reported. Kind: support_or_weak_report; attribution: unknown_provider_or_engine; assessment: closed_unverified; snapshot comments: 1.

Astra стоимость приблизительно 70% ожидаемой по обратной оценке quota. Автор сам исключает точный root cause: нет per-request usage, версии или официального bill; не принимать 0.7 за поправочный коэффициент.

**Comments:** Screenshot и quota anecdote не добавляют per-request usage/bill или version evidence.

Comment citations: [5565092518](https://github.com/Wei-Shaw/sub2api/issues/6646#issuecomment-5565092518) (NONE)

**Наблюдаемая проверка:** H05: separate input/cache-read/cache-write/output counters, compare normalized authoritative receipt.

### [#7034](https://github.com/Wei-Shaw/sub2api/issues/7034) — open; state_reason=null

Reporter version: not reported. Kind: support_or_weak_report; attribution: unknown_engine_or_configuration; assessment: unknown; snapshot comments: 0.

Заголовок сообщает отрицательный balance; тело screenshot. Согласуется с допустимым overdraft, но не доказывает отдельный bug или размер потерь.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** H05/G05: concurrency из малого balance, reservation и финальная запись в DB.

### [#7582](https://github.com/Wei-Shaw/sub2api/issues/7582) — open; state_reason=null

Reporter version: v0.2.8 (title). Kind: support_or_weak_report; attribution: unknown_provider_or_engine; assessment: unknown; snapshot comments: 0.

Codex web-search якобы не тарифицируется, отличие от другого шлюза приведено screenshots. Неизвестен actual provider usage и pricing mode, доказанного общего billing defect нет.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** H05: search effect count, provider native usage и ровно одна запись ledger.

### [#7030](https://github.com/Wei-Shaw/sub2api/issues/7030) — open; state_reason=null

Reporter version: v0.2.3; v0.2.4 file compared. Kind: defect_report; attribution: engine_recovery; assessment: source_risk_support; snapshot comments: 0.

После потери schema_migrations повтор 026 комментирует error_rate, удалённый replacement schema 033; startup зациклен. Оба SQL механизма видны в source. Это аварийный partial restore, не любое обычное обновление.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** G04/G02: сохранить migration ledger, full restore в отдельной DB, запрет downgrade без совместимого backup.

### [#6412](https://github.com/Wei-Shaw/sub2api/issues/6412) — closed; state_reason=completed

Reporter version: v0.1.169. Kind: defect_report; attribution: engine_deployment; assessment: closed_unverified; snapshot comments: 0.

После host restart Postgres в recovery, InitEnt завершает процесс; Docker restart позже восстанавливает. Compose depends_on не гарантирует first startup существующего container; permanent SQL errors нельзя маскировать бесконечным retry.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** G01/G02/G07: delay DB readiness, bounded retry; invalid credential/checksum fail fast.

### [#6232](https://github.com/Wei-Shaw/sub2api/issues/6232) — open; state_reason=null

Reporter version: v0.1.183; backend unmodified (reporter). Kind: defect_report; attribution: engine; assessment: source_mitigation_support; snapshot comments: 1.

Два gateway держат channel whitelist/pricing до 10 минут после update. Supplied source теперь broadcasts invalidate via pub/sub и имеет two-instance service test; отключение pub/sub/Redis ещё оставляет uncertainty.

**Comments:** Contributor обещает cross-instance notification; source теперь содержит pub/sub и service test. Обещание + source поддерживают partial fix, не гарантируют delivery при Redis outage.

Comment citations: [5419907749](https://github.com/Wei-Shaw/sub2api/issues/6232#issuecomment-5419907749) (CONTRIBUTOR)

**Наблюдаемая проверка:** G06/C05/H05: два gateway после model/group/price update, missed notification и retry/TTL.

### [#6780](https://github.com/Wei-Shaw/sub2api/issues/6780) — closed; state_reason=completed

Reporter version: v0.2.2 (title). Kind: defect_report; attribution: unknown_engine_or_deployment; assessment: closed_unverified; snapshot comments: 1.

После upgrade user API-key и subscription списки не загружаются, rollback не помогает. Backend error и DB mismatch не раскрыты; screenshot не свидетельствует потере данных или исправлению.

**Comments:** Другой репортёр подтверждает проблему после upgrade и успешный DB-backup rollback. Отличается от первого автора, которому rollback не помог; disaster recovery зависит от совместимого DB snapshot.

Comment citations: [5573950807](https://github.com/Wei-Shaw/sub2api/issues/6780#issuecomment-5573950807) (NONE)

**Наблюдаемая проверка:** G04/H04: migration + user/admin contract smoke на cloned DB, не только server healthy.

### [#7146](https://github.com/Wei-Shaw/sub2api/issues/7146) — open; state_reason=null

Reporter version: not reported. Kind: support_question; attribution: deployment_configuration; assessment: unknown; snapshot comments: 4.

Docker не стартует после machine reboot; пользователь также спрашивает о переносе данных. Без compose restart policy/volume evidence engine regression не установлен.

**Comments:** Ответы указывают на Docker restart policy; likely deployment support, не engine regression. Следовать внешним инструкциям не требовалось и команды не исполнялись.

Comment citations: [5673026299](https://github.com/Wei-Shaw/sub2api/issues/7146#issuecomment-5673026299) (NONE), [5673899499](https://github.com/Wei-Shaw/sub2api/issues/7146#issuecomment-5673899499) (NONE), [5674330953](https://github.com/Wei-Shaw/sub2api/issues/7146#issuecomment-5674330953) (NONE), [5675114259](https://github.com/Wei-Shaw/sub2api/issues/7146#issuecomment-5675114259) (NONE)

**Наблюдаемая проверка:** G07/G04: owned resource restart policy, data persistence и separate restore rehearsal.

### [#6877](https://github.com/Wei-Shaw/sub2api/issues/6877) — open; state_reason=null

Reporter version: not reported. Kind: support_question; attribution: off_project; assessment: off_project_support; snapshot comments: 4.

Первоначально DB-version/password жалоба; staged comments направляют автора к другому проекту, автор соглашается. Исключён из Sub2API defect signals; сохраняется в appendix как пример ошибочного keyword отбора.

**Comments:** Комментарии направляют автора к другому проекту; автор соглашается. Этот кандидат исключён из активных Sub2API defect signals как likely off-project support.

Comment citations: [5595374342](https://github.com/Wei-Shaw/sub2api/issues/6877#issuecomment-5595374342) (NONE), [5596384300](https://github.com/Wei-Shaw/sub2api/issues/6877#issuecomment-5596384300) (NONE), [5602567417](https://github.com/Wei-Shaw/sub2api/issues/6877#issuecomment-5602567417) (CONTRIBUTOR), [5610997050](https://github.com/Wei-Shaw/sub2api/issues/6877#issuecomment-5610997050) (NONE)

**Наблюдаемая проверка:** G04/H04: совместимость schema до rollback; recovery admin доступен только operator.

### [#1009](https://github.com/Wei-Shaw/sub2api/issues/1009) — closed; state_reason=completed

Reporter version: v0.1.99. Kind: defect_report; attribution: deployment_packaging; assessment: closed_unverified; snapshot comments: 7.

Backup вызов падает: pg_dump отсутствует в PATH, конкретный stacktrace и fresh Docker install. Историческое закрытие без release/comment доказательства не подтверждает наличие бинаря в pinned image.

**Comments:** Один комментатор считает исправленным v0.1.101; поздняя непроверенная AI-like рекомендация говорит v0.1.110 всё ещё без pg_dump. Противоречие и workaround не доказывают pin image contents; никаких shell snippets из комментариев не исполнялось.

Comment citations: [4065665617](https://github.com/Wei-Shaw/sub2api/issues/1009#issuecomment-4065665617) (NONE), [4111697191](https://github.com/Wei-Shaw/sub2api/issues/1009#issuecomment-4111697191) (NONE), [4256143334](https://github.com/Wei-Shaw/sub2api/issues/1009#issuecomment-4256143334) (NONE), [4256889613](https://github.com/Wei-Shaw/sub2api/issues/1009#issuecomment-4256889613) (NONE), [4256899888](https://github.com/Wei-Shaw/sub2api/issues/1009#issuecomment-4256899888) (NONE), [4256976474](https://github.com/Wei-Shaw/sub2api/issues/1009#issuecomment-4256976474) (NONE), [4256982884](https://github.com/Wei-Shaw/sub2api/issues/1009#issuecomment-4256982884) (NONE)

**Наблюдаемая проверка:** G04: pinned container реально создаёт и восстанавливает backup; source Dockerfile alone недостаточно.

### [#2108](https://github.com/Wei-Shaw/sub2api/issues/2108) — open; state_reason=null

Reporter version: not reported. Kind: support_or_weak_report; attribution: deployment_capacity; assessment: unknown; snapshot comments: 0.

Reported 3.8GB RAM, 7.4GB DB/logs и exit137 при R2 backup. Текст предлагает объяснение, не memory profile; размер DB не равен обязательному RSS при streaming.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** G04/G05: bounded backup RSS, log retention и cancel; не выдавать предположение за measured OOM.

### [#2337](https://github.com/Wei-Shaw/sub2api/issues/2337) — open; state_reason=null

Reporter version: not reported. Kind: defect_report; attribution: engine_protocol_bridge; assessment: active_report; snapshot comments: 0.

Messages→OpenAI bridge будто теряет tool_use_id/tool_call_id после двух и более turns: простой grep работает, full-file reads дают 400. Reporter рекомендует native Anthropic как обход; не смешивать эту bridge failure с native Messages availability.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** A04/A05: два параллельных tools, result в обратном порядке, три turns; сохранить ID association и content order, reject unmatched results.

### [#6146](https://github.com/Wei-Shaw/sub2api/issues/6146) — open; state_reason=null

Reporter version: main 03e8ab413 (reporter). Kind: defect_report; attribution: engine; assessment: source_mitigation_support; snapshot comments: 3.

После custom→function→custom restoration fc item ID отравляет историю и следующий turn получает 400 вместо ctc; аналогично tool_search tsc. Supplied source теперь re-prefixes известные IDs при restore. Это scoped source mitigation; call_id отдельно от item id, runtime replay не проверен.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** A04/A10/E11: JSON, added/done/completed SSE и next-turn history; item ID namespaces и call/result association отдельно, Unicode и split chunks.

### [#6185](https://github.com/Wei-Shaw/sub2api/issues/6185) — closed; state_reason=completed

Reporter version: v0.1.181 and v0.1.182; Grok Build 1.0.5. Kind: defect_report; attribution: unknown_session_state_or_provider; assessment: closed_unverified; snapshot comments: 1.

После parallel vision tool results Grok Responses продолжает посторонний task при корректной local history; official direct control будто работает. Reported unrelated task не доказывает actual cross-tenant data source, но требует isolation triage. Закрытие completed не подтверждает фикса.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** G06/C05/A04: две synthetic workspaces с distinct prompt/account sentinels, parallel tools и previous_response_id; отсутствие crossover после restart/cache reuse.

### [#6402](https://github.com/Wei-Shaw/sub2api/issues/6402) — closed; state_reason=completed

Reporter version: v0.1.183/main; Desktop 26.825.51511; CLI 0.151.0-alpha.7.2. Kind: defect_report; attribution: engine_client_compatibility; assessment: closed_unverified; snapshot comments: 10.

Desktop delegation bootstrap function_call_output без call_id отвергается HTTP handler до inference. Это специальный bootstrap, обычным orphan tool outputs по-прежнему нужен 400. WS101 с последующим fallback не обход; supplied WS compatibility test не доказывает HTTP Desktop fix.

**Comments:** No substantive staged comment evidence; no fix inferred.

Comment citations: none

**Наблюдаемая проверка:** A08/A09: real Desktop delegation если scope includes it; explicit unsupported error вместо fabricated call_id/успеха, strict обычный tool context.

## Приложение: source/test evidence

Upstream tests только прочитаны; отдельного PASS нет. Каждый source fingerprint включён в findings.json, ссылки используют supplied immutable SHA, который не проверен через Git metadata.

- [S01 backend/internal/repository/scheduler_cache.go:953](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/internal/repository/scheduler_cache.go#L953): Credentials whitelist excludes openai_capabilities/base_url; Extra now retains base_rpm/rpm_strategy/rpm_sticky_buffer. Different projection bugs must be assessed separately. (source audit; no runtime reproduction).
- [S02 backend/internal/repository/scheduler_cache_unit_test.go:1173](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/internal/repository/scheduler_cache_unit_test.go#L1173): TestBuildSchedulerMetadataAccount_KeepsRPMFieldsForRPMGate compares real schedulability before/after metadata projection; unit build tag. v0.2.8 release corroborates fix; not executed here. (source/test inspection plus release claim).
- [S03 backend/internal/service/oauth_refresh_api.go:168](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/internal/service/oauth_refresh_api.go#L168): Unified refresh acquires local/distributed lock and rereads DB; lock error explicitly degrades to local mutex. This is not distributed exclusivity during Redis failure. (source audit; live rotating identity NOT RUN).
- [S04 backend/internal/service/token_refresh_service.go:869](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/internal/service/token_refresh_service.go#L869): Background executor uses shared OAuthRefreshAPI; Claude request provider does too when injected. Old separate-entry claim has source mitigation, not proof of all refresh failure branches. (source audit).
- [S05 backend/internal/service/openai_images.go:1641](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/internal/service/openai_images.go#L1641): Downloader invokes Get(downloadURL) without a local target validator. Cannot infer entire attack reachability or shared transport protections from this helper alone; keep image route inaccessible. (source risk corroboration; exploit NOT RUN).
- [S06 backend/internal/config/config.go:2115](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/internal/config/config.go#L2115): Legacy forwarded IP trust defaults true. ip.go legacy resolver prioritizes CF-Connecting-IP; trusted-proxy path is available when mode disabled. Must deploy explicit edge/header policy. (source/config audit).
- [S07 backend/ent/schema/account.go:74](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/ent/schema/account.go#L74): Credential map is JSONB. account_repo UpdateCredentials JSON-marshals directly to credentials JSONB, scheduler projection can contain api_key. No application-encryption claim is supported by these paths; DB/Redis/exports/backups belong in operator custody. (source custody audit).
- [S08 backend/internal/repository/usage_billing_repo.go:243](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/internal/repository/usage_billing_repo.go#L243): Final debit retries insufficient-balance update without balance predicate, allowing overdraft. v0.2.11 inflight reservation mitigates concurrent admission but is not a strict DB spend cap. (source audit and bounded release claim).
- [S09 backend/internal/service/billing_inflight_reservation.go:238](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/internal/service/billing_inflight_reservation.go#L238): Redis/cache read/reserve failure returns no reservation (fail-open); subscription path bypasses balance reservation. Unpriced fail-open defaults false for fail_closed_on_unpriced in config. Need hard ReviewRouter budget admission outside engine. (source audit; load/cancellation NOT RUN).
- [S10 backend/internal/service/channel_service.go:396](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/internal/service/channel_service.go#L396): Cache invalidation rebuilds locally and notifies pub/sub; subscription clears other process cache. TestInvalidateCachePublishesToOtherInstances uses two real service instances but mock pub/sub, so does not prove Redis notification delivery or outage behavior. (source mitigation; service-boundary test inspected only).
- [S11 backend/internal/service/payment_refund_test.go:505](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/internal/service/payment_refund_test.go#L505): Tests reject stale finalize before second deduction and roll back DB deduction after injected error. They inspect transactional DB state, not live payment provider/restart recovery. Partial mitigation only. (test source inspection; not executed).
- [S12 backend/migrations/026_ops_metrics_aggregation_tables.sql:50](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/migrations/026_ops_metrics_aggregation_tables.sql#L50): Unconditional error_rate column comment; migration 033 drops/rebuilds metrics tables. Replaying old migrations against later schema needs full restored ledger, not assumed idempotency. (source corroboration; PostgreSQL reproducer NOT RUN).
- [S13 backend/internal/service/gateway_structured_outputs_beta_test.go:49](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/internal/service/gateway_structured_outputs_beta_test.go#L49): BuildUpstreamRequestStructuredOutputsBeta inspects outgoing header/body; v0.2.9 release says beta retained. This supports scoped fix and is not full native Claude E2E. (source/test and release corroboration; execution NOT RUN).
- [S14 backend/internal/service/service_tier_billing.go:69](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/internal/service/service_tier_billing.go#L69): OAuth-like account retains outbound tier when response is default; API-key path uses response-tier downgrade. Chained accounting consistency requires compositional test. (source corroboration; provider bill not independently verified).
- [S15 backend/internal/handler/auth_oidc_oauth.go:36](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/internal/handler/auth_oidc_oauth.go#L36): Browser OIDC state/nonce/verifier/intent/bind-user cookies implement human auth. Not evidence for GitHub Actions repository/workflow/run capability checks. (source audit).
- [S16 LICENSE:1](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/LICENSE#L1): LGPL v3 text present; README says v3 or later. Preserve notices and request distribution/linking review for chosen packaging; no legal conclusion. README sponsorship is not independent availability evidence. (licence/community source inspection).
- [S17 backend/internal/pkg/apicompat/responses_client_tools.go:328](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/internal/pkg/apicompat/responses_client_tools.go#L328): Known fc_/ctc_/tsc_ prefixes are retyped when restoring custom/tool_search items, preserving suffix. restoreClientToolValue applies the helper. This source mitigation contradicts assuming the still-open historical restoration report remains unchanged on pin; full SSE/replay still untested. (source mitigation; no independent runtime reproduction).

## Воспроизведение и handoff

Из repository root: `python3 sub2api-issues-audit/analyze.py`; затем `python3 sub2api-issues-audit/verify.py`. Input SHA-256, formulas, весь census, короткие безопасные dashboard поля и source hashes находятся в findings.json/dashboard.json. `verification.json` фиксирует реально выполненные проверки этого analyzer, не upstream engine.

Ownership: только sub2api-issues-audit/. Git lock preflight выполнен один раз: .git — linked-worktree файл, index.lock недоступен; обходов, commits/push не было. Bifrost и implementation lane не изменялись. Comments/live evidence не фабрикуются; рекомендации пересмотреть после normalized receipts и полного comment review.
