# Sub2API: итог спайка и E2E

Проверено 2026-10-01 19:42 UTC. Только disposable sandbox на Hetzner. Production ReviewRouter и действующий Codex subscription pool не переключались. Hosted workers: gpt-6.1-sol, priority/fast.

## Результат

| Живой Actions E2E | Результат | Новые запросы | Транспортный бюджет |
|---|---|---:|---:|
| [Codex + MiMo HIGH](https://github.com/777genius/rr-selfhost-direct-v2-e2e-20260730t115357z/actions/runs/36913301414) | PASS | 5 | 120s |
| [Codex + OpenRouter](https://github.com/777genius/rr-selfhost-direct-v2-e2e-20260730t115357z/actions/runs/36913671762) | PASS | 5 | 120s |
| [Claude + MiMo](https://github.com/777genius/rr-selfhost-direct-v2-e2e-20260730t115357z/actions/runs/36915189084) | PASS | 2 | 300s |

Каждый агент действительно читал wallet.mjs и BUSINESS_RULES.md инструментами, завершил ответ с financial finding; числовой пример проверен независимым запуском Node. Codex дополнительно выполнил собственное локальное воспроизведение. В трёх terminal filesystem snapshot около 2,48 ГБ каждый: 0 raw/base64 provider-key hits, 0 host binds. Это проверка файлов, конфигурации и логов на завершении, не непрерывная проверка памяти процесса. Network boundary PASS: runner видит broker, Sub2API/Postgres/Redis недоступны напрямую.

- Exact workflow/source `3c230702f3fb6e333b290bedb66419374bee9a9c`; runner image `f4971c169942227e808ccac24e3e740525f3dd149ac974a0e760b554c6ceec5a`.
- Native image `c656447c1b79706e67f71fe49ada0f0f840e26eba798597e6751917ddc691bd1`; binary `5e28306e531eac0abea49811f116dbbddb233c4e52ce3f7d63f9c71d949632fd`.
- Native84 PASS: 4 группы account/user × Responses/Messages,80 opt-in +4 default controls, 168 effects, 420 Redis checks, 0 cleanup failures/active/unknown dispatches. Setup 70s и active 35s явно разделены, supervisor 20min и 1250ms recovery сохранены.
- Cancellation 12/12 PASS, uncertainty 8/8 PASS. Actual normal Go 569/native 292/probe 63/race 129 PASS, 0 skips/DATA_RACE. Wrong-CA BAD_CERTIFICATE подтверждён,0 effects/leases.
- Functional load 20/20 PASS: 686 synthetic requests,0 cleanup/unknowns. Synthetic OAuth 211 PASS; live OAuth NOT RUN.

## Сохранённый сбой Claude

[36913874394](https://github.com/777genius/rr-selfhost-direct-v2-e2e-20260730t115357z/actions/runs/36913874394) отменён после невосстановимого истечения доступа. Исходный hard total timeout 120s оборвал запрос, который native gateway завершил за 150440ms; далее сработала expiry capability. После завершения native drain известно 4 provider requests, включая дополнительные попытки клиента; исходная заметка о 2 завершённых строках остаётся исторической. Утверждения о побитово одинаковых payload или надёжности upstream без дополнительных trace не делаются. Custody/owned cleanup PASS.

Новый эксперимент изменил только операторскую конфигурацию request timeout на 300s, сохранив тот же SHA, sealed runner/native binary, TTL и все native/RSS gate. Он завершён успешно: 2 requests, один успешный stream 138811ms. Порог 120s оказался слишком коротким для наблюдаемого MiMo Messages latency; это конфигурация внешнего broker, не новый фикс или изменение Sub2API в production.

## Границы готовности

**Общего production GO нет.**

1. Все 20 strict RSS-return checks FAIL: baseline+32MiB за 5s не достигнут. Порог / GC / container budget не ослаблялись.132 raw pprof проверены, live attribution/бесконечная утечка и непрерывный физический bound не доказаны. Функциональный PASS не заменяет эту проверку памяти.
2. Capability ограничена expiry исходного GitHub OIDC JWT (обычно 5min). Refresh для более долгих jobs в спайке не реализован. Конфигурация300s сама по себе это ограничение не исправляет.
3. При истечении root supervisor его собственная cleanup не запускается: исходный FAIL сохранён. Отдельный parent compensator проверен на реальных 4 owned контейнерах/сети за 1673ms. Автоматической production-гарантии ещё нет.
4. Live OAuth не проверен; migration 243 запрещает upgrade populated consumption history. Агент/провайдер за пределами трёх проверенных combinations не объявляется совместимым.

## Переиспользование и очистка

Reusable exact-source kit: [RUNBOOK](../../sub2api-native-merged/RUNBOOK.md), official upstream v0.2.11 / 96f4c115c9749078f90cbf210a01d39baf3f53b6. Он воспроизводит backend из официального дерева и проверенных patches; лицензия upstream сохраняется. GitHub fork/release ещё не опубликован. Product UI/production integration в эту работу не входили.

Все собственные canary runners/brokers/networks удалены, GitHub ephemeral runner entries отсутствуют.6 owned тестовых сервисов остановлены; образы, данные и private diagnostics сохранены для воспроизведения. Original root-only provider files не изменены. Disposable workflow disabled.

Полные публичные receipts, SHA pins, GitHub statuses и сохранённые failures: [evidence.json](evidence.json).

## Независимый аудит OIDC и таймаута

[Отчёт](../../sub2api-auth-timeout-audit/REPORT.md) принят в коммите1d569cf:8 deterministic checks над замороженным исходным кодом, без HTTP/provider execution. Он подтверждает, что300s не продлевает OIDC lease. Входы были заморожены до завершения последнего Claude; его формулировка «не проверен в supplied inputs» историческая. Parent после этого независимо проверил публичный PASS36915189084, source/image pins, custody и usage2requests.

Минимальный следующий шаг для jobs дольше5min оценён аудитом в60–120 строк рабочего кода и100–180 строк тестов: отдельный ограниченный access lease до15min и явная проверка оставшегося времени в trusted launcher. Это отдельное изменение политики авторизации; оно не реализовано в спайке. Схема бесконечного продления не предлагается.
