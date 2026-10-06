**FAIL: checkpoint не готов к трём платным native canaries. Ограниченный независимый review завершён; runtime E2E остаётся NOT RUN.**

Заявленный checkpoint: `078fd409ef19ff71f6062030174bb2fb5c21f3be`. Заявленный Sub2API v0.2.11: `96f4c115c9749078f90cbf210a01d39baf3f53b6`. Commit задан координатором; git rev-parse/status недоступны из-за отсутствующего/закрытого linked-worktree gitdir. Независимо проверены байты всех source files и их неизменность; commit-to-tree mapping должен проверить coordinator.

Проверенный harness SHA-256: `7902bde772a2317e770b32dccdd249c3f8a24f3082d6a159690f483671b976c6`. Полный независимый manifest 4208 source/dependency файлов: `7b3d7da58d27949ddb6b45ef23d323618cdc5ffeb4c9ad3e5ea7fcd7be869829`; алгоритм и все file hashes — [source-hashes.before.json](source-hashes.before.json). Пять source-snapshot hashes совпали. Before/after проверка — [source-verification.json](source-verification.json).

Node 24.21.0: полный встроенный contract suite попытались запустить, но sandbox запретил loopback 127.0.0.1; полный PASS не установлен. Шесть socket-free исходных contracts PASS. Восемь проверок reproduction PASS означают подтверждённые наблюдения дефектов, а не E2E. [Pure contracts](pure-contract.txt), [reproduction](reproduction.json), [reproducer](reproduce.mjs).

Reproducer импортирует неизменённые модули и вызывает действующие HTTP request handlers без listening sockets; fetch только синтетический. Для parent-env проверки создаётся отдельный synthetic-only родитель, реальные credentials/proc environments не читаются. Команда: `TMPDIR=<доступный временный каталог> node sub2api-review/reproduce.mjs`.

**R01 P1: Блокер Claude canary.**

Claude 2.1.285 обращается к /anthropic/v1/messages?beta=true; брокер отклоняет любой query до проверки capability: 404 route_denied. Нативная ветка до engine не доходит.

Места: `sub2api-spike/broker.mjs:31`, `sub2api-spike/run-client.mjs:66`.

Доказательство: Выполнен настоящий обработчик брокера без listening socket; 404, upstream effects=0. Фактический wire от установленного Claude в этом review не запускался; форма URL сообщена координатором.

Минимальное исправление: Разрешить ровно один параметр beta=true только на разрешённых Messages paths; неизвестные, повторные и routing-параметры по-прежнему отклонять. Отдельно проверить исходящий URL/anthropic-beta. Native engine сам добавляет beta=true.

**R02 P1: Блокер native synthetic Messages.**

Engine формирует /v1/messages?beta=true, но mock выбирает Messages лишь при req.url === /v1/messages. Поэтому A05 получает Responses SSE вместо Messages.

Места: `sub2api-spike/mock-upstream.mjs:27`, `.spike-inputs/upstream/backend/internal/service/gateway_anthropic_passthrough.go:310`.

Доказательство: Прямой вызов действующего mock handler с engine URL вернул response.completed и не вернул message_stop.

Минимальное исправление: Разбирать URL и выбирать протокол по pathname; проверять допустимый beta query отдельно. Добавить contract с точным исходящим engine URL.

**R03 P1: Нативная корректность обоих протоколов.**

Рекурсивный denyRouting принимает обычные поля tool_use.input.account/workspace, metadata и JSON Schema за маршрутизацию. Законные structured данные получают 400. Исключение только для ключа tools не решает проблему.

Места: `sub2api-spike/broker.mjs:10`, `sub2api-spike/broker.mjs:11`, `sub2api-spike/broker.mjs:64`.

Доказательство: Messages assistant tool_use с input.account.balance=100 и input.workspace отклонён до upstream.

Минимальное исправление: Ограничить запрет служебными routing-полями верхнего уровня и routing headers/query; закреплять реальную workspace/group/key/URL только доверенными server bindings. Вложенные input/messages/content/schema сохранять. Проверить roundtrip association и оба протокола.

**R04 P1: Предусловие безопасного operator setup и платных canaries.**

Создание OpenAI apikey account запускает асинхронный Responses tool probe. force_responses/openai_passthrough его не отключают. Admin-roundtrip использует dummy credential с настоящим MiMo URL; live создание с настоящим ключом тоже может вызвать inference до запланированного Actions. Без model_mapping probe выбирает gpt-5.4, а не выбранную модель canary.

Места: `sub2api-spike/operator/admin-roundtrip.mjs:36`, `sub2api-spike/customer.mjs:67`, `.spike-inputs/upstream/backend/internal/handler/admin/account_handler.go:1096`, `.spike-inputs/upstream/backend/internal/handler/admin/account_handler.go:1241`, `.spike-inputs/upstream/backend/internal/service/openai_apikey_responses_probe.go:166`, `.spike-inputs/upstream/backend/internal/service/openai_apikey_responses_probe.go:178`, `.spike-inputs/upstream/backend/internal/pkg/openai/constants.go:55`.

Доказательство: Подтверждено по полной цепочке create -> goroutine -> validate baseURL -> HTTP POST. Реальных provider вызовов reviewer не делал. Эффективная synthetic allowlist [mock-a,mock-b] блокирует настоящий MiMo URL до сети; это требуется подтвердить на operator engine, а не предполагать по YAML.

Минимальное исправление: Для dummy roundtrip использовать доверенный server-only mock URL override до создания, не caller input. Для live setup закрыть provider egress/allowlist на время create/update и дождаться завершения probes до включения live выхода, либо отдельно проверить pinned engine patch для отключения probes. Mock-probe requests учитывать отдельно и дождаться покоя до fault metrics. Не объявлять upstream_requests=0 по константе receipt.

**R05 P1: Ложный FAIL обоих Codex canaries.**

Wallet-read и reproduction validators распознают /bin/bash -lc shell wrapper, а rulesRead допускает только голый cat BUSINESS_RULES.md. Корректный успешный Codex tool read через wrapper отвергается.

Места: `sub2api-spike/evidence.mjs:29`, `gateway-spike/evidence.mjs:4`, `sub2api-spike/run-client.mjs:81`.

Доказательство: Одинаковые успешные events: plain rules command принят; shell-wrapped rules command отвергнут Missing separate rules read.

Минимальное исправление: Использовать общий строгий нормализатор shell command для wallet, rules и reproduction; сохранить отдельные completed tool calls, exit_code=0 и фактическое содержимое обоих файлов. Не менять classifier/User-Agent для обхода.

**R06 P1: Недостоверный synthetic gate неопределённых эффектов.**

partial-reset сначала конструирует и записывает весь поток, включая response.completed, затем уничтожает соединение. Это не надёжное воспроизведение reset после частичного semantic output до terminal; фактическая доставка зависит от buffering. Engine fault lane также не повторяет HTTP ошибки и reset для Messages.

Места: `sub2api-spike/mock-upstream.mjs:39`, `sub2api-spike/mock-upstream.mjs:45`, `sub2api-spike/mock-upstream.mjs:48`, `sub2api-spike/operator/container-native.mjs:53`, `sub2api-spike/operator/container-native.mjs:59`.

Доказательство: Действующий handler записал response.completed до destroy; socket delivery и retries engine NOT RUN.

Минимальное исправление: Выдать подтверждённый частичный output/tool-result association, оборвать до terminal после контролируемого flush/барьера; отдельно reset до headers и после частичного output. Измерять реальные engine requests/effects после quiescence для обоих протоколов и live-подобных pool_mode=false/single-account/no-fallback настроек.

**R07 P1: Блокер D03 изоляции agent от Actions OIDC.**

Env allowlist дочернего процесса не изолирует его от родителя run-client/Actions runner с OIDC request token. Codex danger-full-access в том же UID/PID namespace способен читать /proc/<parent>/environ. Sealed fixture ограничивает запись fixture, но не доступ к control runtime.

Места: `sub2api-spike/run-client.mjs:14`, `sub2api-spike/run-client.mjs:19`, `sub2api-spike/run-client.mjs:44`, `sub2api-spike/run-client.mjs:62`.

Доказательство: В отдельном процессе с исключительно синтетическим родительским токеном child env не содержал токена, но parent procfs оставался читаемым. Настоящие credentials/proc environments не исследовались. Runner-specific procfs hardening пока не доказан.

Минимальное исправление: После trusted OIDC exchange запускать model client в отдельном PID/mount/container boundary без Actions runner процессов и control mounts, передавая только scoped capability и sealed fixture. Либо доказать эквивалентную раздельную UID/procfs изоляцию синтетическим sentinel тестом. Проверить D03/D04 на новом runner.

**R08 P1: Блокер custody fault gate; source-дефект native Messages.**

Broker санирует только non-2xx; HTTP200 SSE error проходит байтами. Native Anthropic passthrough выводит error line без key redaction, а HTTP401/403/429/5xx failover пишет raw Body до 1000 символов в LegacyPrintf и Message в ops. log_upstream_error_body=false не закрывает эти пути; строка upstream error получает ERROR уровень и остаётся при log.level=warn.

Места: `sub2api-spike/broker.mjs:76`, `sub2api-spike/broker.mjs:84`, `.spike-inputs/upstream/backend/internal/service/gateway_anthropic_passthrough.go:220`, `.spike-inputs/upstream/backend/internal/service/gateway_anthropic_passthrough.go:234`, `.spike-inputs/upstream/backend/internal/service/gateway_anthropic_passthrough.go:555`, `.spike-inputs/upstream/backend/internal/pkg/logger/logger.go:471`.

Доказательство: Broker handler переслал синтетический credential sentinel в HTTP200 SSE error. Native redaction gap подтверждён source; настоящий engine sentinel/log test NOT RUN. Никакой фактической утечки настоящего ключа не утверждается.

Минимальное исправление: На trusted engine sanitise provider credential values для всех API-key accounts до logs/ops/error responses, либо удалить произвольные upstream error messages на публичном SSE boundary. Broker не должен получать provider key для этого. Проверить sentinel в non-2xx, HTTP200 terminal error после output, ops/logs/runner artifacts.

**R09 P2: Точность checkpoint и evidence handoff.**

harnessDigest не включает BUSINESS_RULES.md и импортированные gateway-spike/oidc.mjs/evidence.mjs/fixture/wallet.mjs. normalizedReceipt проверяет harness_git_sha лишь по regex, не на равенство reviewed checkpoint. Поэтому digest/receipt сами не доказывают неизменность всех значимых inputs exact review.

Места: `sub2api-spike/operator/provenance.mjs:8`, `sub2api-spike/operator/provenance.mjs:9`, `sub2api-spike/receipts.mjs:6`, `sub2api-spike/build-report.mjs:35`.

Доказательство: Validator принял произвольный SHA a*40 при заданном matching tree digest; исключённые зависимости установлены по алгоритму digest и import.

Минимальное исправление: Проверять ожидаемый checkpoint SHA плюс полный manifest значимых транзитивных imports и fixture/rules. Использовать приложенный независимый manifest при integration; включить actual runner image/client measurements.

**R10 P2: Ограничение production и неподтверждённый engine cancellation gate.**

Engine использует WithoutCancel и продолжает drain upstream для usage после client disconnect. Abort брокера по TTL/revoke/cancel не доказывает немедленную отмену provider inference или освобождение engine concurrency. Broker mock contract это различие не покрывает.

Места: `.spike-inputs/upstream/backend/internal/service/gateway_usage_billing.go:573`, `.spike-inputs/upstream/backend/internal/service/gateway_usage_billing.go:583`, `.spike-inputs/upstream/backend/internal/service/openai_gateway_passthrough.go:369`, `.spike-inputs/upstream/backend/internal/service/gateway_anthropic_passthrough.go:558`, `sub2api-spike/broker.test.mjs:48`.

Доказательство: Подтверждено source; actual engine duration/active connections после revoke NOT RUN.

Минимальное исправление: Измерить revoke/expiry/disconnect на native engine для обоих протоколов. Явно документировать drain/billing и верхнюю границу; если требуется строгая upstream отмена, нужен отдельно проверенный engine change. Не повышать mock E06/B11 до engine PASS.

**R11 P2: Production customer adapter; отдельный риск при management fault tests.**

При ambiguous create метаданные уходят в recovery_required, но удалённый account уже создаётся active/schedulable и привязан к существующей group. Скрытие local binding не убирает его из scheduler существующего group-bound key. Тест C10 оставляет record и не доказывает отсутствие orphan authority.

Места: `sub2api-spike/customer.mjs:67`, `sub2api-spike/customer.mjs:70`, `sub2api-spike/customer.test.mjs:72`, `.spike-inputs/upstream/backend/internal/service/admin_account.go:434`.

Доказательство: Source create выставляет active/schedulable; catch не делает quarantine/delete и может не знать upstreamID. Это source review, не реальный create fault.

Минимальное исправление: Создавать account в отдельной exclusive quarantine group без любых access keys; публиковать рабочую group binding только после durable локальной записи. Проверять отсутствие других groups и reconcile неоднозначные creates по server-generated id/name. Не объявлять C10 fully PASS на основании отсутствия account в UI list. Успешный sealed canary сам по себе этот production риск не закрывает.

**Проверенные boundaries и важные ограничения.**

- Grant выдаёт random 32-byte opaque capability, model/expires; provider/engine/admin key не включаются. Синтетический grant projection проверен.
- resolveWorkspace использует server runBindings[runID:attempt]; caller grant разрешает только provider/protocol. group/key/URL взяты из private server scopes, не customer body.
- Compose не публикует ports; runner network отделён от engine/state/control; customer listener должен bind approved control IP. Actual runner network reachability NOT RUN.
- Upstream /api/v1/admin использует admin auth/audit/compliance middleware. Customer API отдаёт положительную metadata projection, raw export остаётся private.
- Native account flags подтверждены source: extra.openai_responses_mode=force_responses, extra.openai_passthrough=true, extra.anthropic_passthrough=true; это не credentials flags. force_responses выбирает Responses до auto probe support flag, но не отменяет probe.
- MiMo client_metadata: broker передаёт его; OpenAI API-key passthrough не удаляет его автоматически, rejected-field retry helper не поддерживает client_metadata. Предыдущий Bifrost отказ — основание для точного synthetic/recorded-wire preflight, но не доказанный live MiMo FAIL этого engine. Если текущий MiMo действительно отказывает, минимальная явная provider-specific нормализация только этого поля либо honest unsupported результат; не менять originator/User-Agent/classifiers и не bridge Chat Completions.
- max_account_switches=0 игнорируется: OpenAI constructor default=3, общий Messages handler default=10. Single account/private group/no fallback/pool_mode=false ограничивают ordinary повторные effects; source сам по себе не доказывает duplicate paid request. Synthetic pool_mode=true,retry_count=0 отличается от live setup.
- При default API-key settings ShouldHandleErrorCode=true, поэтому shouldRetryUpstreamError=false: нельзя утверждать безусловные пять Anthropic retries. При custom error codes это может измениться; OpenAI имеет отдельные explicit-400 compatibility retries. Требуется измерение actual native fault effects.
- Admin login/groups actual200, принятое owner authorization/operator commitment и effective standard mode приняты как факты координатора. Staged bootstrap/YAML всё ещё simple; не запускать их поверх уже установленного standard engine и не считать их доказательством effective config.
- Sealed root fixture, версии клиента и существующий runner image сообщены координатором. run-client проверяет root ownership, отсутствие write bits, byte equality fixture и ожидаемую version; measured image/PID/network isolation остаётся operator evidence.
- Claude разрешены Read/Glob/Grep, локальный executable numeric пример воспроизводит harness. Собственное выполнение примера агентом проверяется отдельно только для Codex. Если требуется own-tool execution также для Claude, текущая allowlist его не обеспечивает.
- ReviewRouter SSO/dynamic membership, OAuth lifecycle/test identities, credential-bearing JSONB/Redis/export/backup custody и upgrade/license operations не доказаны production-ready этим disposable spike. Они не требуют ожидания live receipts для завершения этого ограниченного review.

Исправления reviewer не вносил. Рекомендации R01-R09 передать владельцу кода; trusted coordinator проверяет manifest и выполняет native synthetic/custody gates перед тремя платными canaries. Повторные реальные запуски после неопределённого результата не инициировались.

Reviewer менял только собственный `sub2api-review/`: report/result, source manifests и воспроизводитель/outputs. Reviewed source/upstream/workflow и чужие outputs не изменены; commits/staging/push, credentials, Docker/GitHub/production operations отсутствуют.
