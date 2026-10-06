# Codex + MiMo: диагностика отсутствующего финального ответа

2026-10-01. Изолированный disposable sandbox на workers-fsn1-01. Production ReviewRouter не изменялся.

## Вывод

**Воспроизведена потеря reasoning-контекста на входе MiMo и последующий `completed` без assistant message.** Sub2API v0.2.11 применяет OpenAI-специфическую нормализацию к MiMo, подключённому как OpenAI-compatible API-key account. При `store=false` она удаляет reasoning items без `encrypted_content`. MiMo возвращает незашифрованный reasoning и рекомендует сохранять его в истории tool conversations.

Сам поток ответа Sub2API и наш error fence **не повредили**: все 6 Responses в failing диагностическом запуске совпали побайтово между provider и client tap.

Codex 0.159.2 получает `response.completed`, не видит нового tool call или `end_turn=false`, завершает ход. `--output-last-message` сохраняет последнее assistant message, если оно было, либо пустую строку. Поэтому возможны оба наблюдения: пустой файл и устаревший промежуточный комментарий.

Уверенность в механизме нового воспроизведения: **🎯 9/10**. Причина исходного Actions run 36778603368 очень вероятно та же, но его исходный upstream stream уже удалён. Новая диагностика не выдаётся за побайтовое доказательство старого запуска или статистику надёжности.

## Эксперименты

Все genuine clients: Codex 0.159.2, MiMo `mimo-v2.6-pro`, одинаковый prompt и immutable financial fixture. Native Responses, без protocol conversion. Ключ провайдера находится только в trusted operator tap; в agent container только sandbox capability. Автоматические retries выключены.

| Эксперимент | Наблюдение | Граница доказательства |
|---|---|---|
| Sub2API, thinking по умолчанию | 6 provider calls, 5 successful tools; последний response только reasoning, `completed`, output/reasoning tokens 284/284. Review 98 bytes содержит прежний commentary | Настоящий hosted agent, final finding FAIL |
| Напрямую MiMo, thinking по умолчанию | 4 calls, 3 tools; genuine assistant message 563 bytes, валидный finding и независимое numeric reproduction | Ответ получен; полный строгий canary FAIL: numeric tool output не совпадает с примером final finding |
| Точный последний запрос, 5 reasoning items удалены | HTTP200, completed, только reasoning, 176 output /175 reasoning tokens, ноль message | Один planned provider replay |
| Тот же запрос, 5 reasoning items сохранены | HTTP200, completed, reasoning +assistant message 658 characters, 240 output /81 reasoning tokens | Один planned provider replay; единственная структурная разница в input |
| Sub2API + `reasoning.effort=none` | 8 calls, 7 successful tools; final answer 767 bytes. Отдельные reads кода/правил, valid finding, совпадающий numeric tool и независимое reproduction | **PASS** строгого financial contract в hosted container; не новый GitHub Actions run |

Парный replay усиливает причинный вывод, но один stochastic sample на вариант не доказывает, что сохранение истории всегда исключает пустой ответ. Full thinking-enabled canary через исправленный Sub2API ещё не выполнен.

### Что исключено

- **Потеря финального текста фильтром:** 6/6 native provider/client responses равны побайтово; message отсутствует уже у provider.
- **HTTP/quota/stream interruption:** реальные ответы HTTP200, `response.completed`, без provider error или incomplete terminal.
- **Явно маленький output limit:** в обоих последних запросах нет `max_output_tokens`; последний failing ответ завершён, а не `incomplete`.
- **Старая ошибка JSON array validator:** failing новый запуск содержит commentary вместо JSON. Причина отличается от ранее исправленного array/object validator.
- **Отсутствие tool execution:** tools реально выполнялись, но их stdout не подменяет финальный ответ модели.

## Исходный код и документация

Sub2API v0.2.11, revision `96f4c115c9749078f90cbf210a01d39baf3f53b6`:

- [openai_gateway_forward.go:181](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/internal/service/openai_gateway_forward.go#L181): normalizer вызывается для OpenAI API-key account. Passthrough=true его не отключает.
- [openai_gateway_request_body.go:731](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/internal/service/openai_gateway_request_body.go#L731): при `store=false` reasoning без непустого `encrypted_content` исключается из input.
- [account.go:1441](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/internal/service/account.go#L1441): native CN Responses platforms перечислены явно; MiMo в списке нет. Подменять MiMo другим provider type не предлагается.
- [MiMo native Responses docs](https://mimo.mi.com/docs/en-US/api/chat/responses): сохранение reasoning в multi-turn tool history рекомендовано; `reasoning.effort=none` отключает thinking. Все остальные уровни включают одинаковый thinking mode.

Codex `rust-v0.159.2`, revision `8b9fa496bbf2c47aebd62e85a080b9a522a455b5`:

- [session/turn.rs:2953](https://github.com/openai/codex/blob/8b9fa496bbf2c47aebd62e85a080b9a522a455b5/codex-rs/core/src/session/turn.rs#L2953): `end_turn=false` требует follow-up; сам completed не требует assistant message.
- [exec/event_processor.rs:31](https://github.com/openai/codex/blob/8b9fa496bbf2c47aebd62e85a080b9a522a455b5/codex-rs/exec/src/event_processor.rs#L31): отсутствующее last message превращается в пустую строку.

GitHub source читался через gh CLI. Проверка releases/latest 2026-10-01 дала v0.2.11; новая версия не устанавливалась.

## Исправление и ограничения

**Проверенный временный обход:** в sandbox Codex config добавить `model_reasoning_effort="none"`. Provider master key по-прежнему остаётся на сервере. Это меняет режим модели, поэтому не считается полноценным исправлением thinking path и не переносится молча на production.

**Нужное постоянное исправление:** provider-aware native passthrough должен сохранять MiMo reasoning history и отключать OpenAI-specific replay sanitation только на соответствующем account path. Нельзя глобально выключать нормализацию OpenAI: она защищает отдельный upstream контракт. Поддержанного account toggle для этой операции в проверенном коде не найдено. Это работа в upstream/fork Sub2API с real thinking-enabled canary; в данном диагностическом запросе fork не создавался.

Наш final review contract уже отвергает пустой или невалидный finding. Нужна также явная terminal diagnostic: completed без message/tool должен быть наблюдаемым failed review, а не поводом заменить результат tool stdout или автоматически повторять paid inference.

## Evidence и custody

- [trace-summary.json](evidence/mimo-diagnosis/trace-summary.json): positive projection response types/status/lengths, exact-byte comparison boolean, request shape delta.
- [paired-replay.json](evidence/mimo-diagnosis/paired-replay.json): два запланированных запроса, 0 automatic retries.
- [client-validation.json](evidence/mimo-diagnosis/client-validation.json): отдельные transport/finding/numeric проверки, включая частичный direct результат.
- [engine-none-summary.json](evidence/mimo-diagnosis/engine-none-summary.json): genuine agent terminal и tools.
- Ключ не смонтирован в agent, не найден в 196 residual client files; сырые requests/SSE/reasoning/agent homes не экспортированы и удалены при teardown.
- [Teardown](evidence/mimo-diagnosis/teardown.json): удалены свои 9 containers, 3 networks, diagnostic operator tree и четыре оставшихся synthetic paths прошлого спайка. Original provider files сохранили inode/size/mtime; чужие ресурсы не затронуты.
- Hosted source worker gpt-6.1-sol/high подготовил отдельный bounded observer/replay prototype; 34/34 synthetic tests прошли на сервере. Worker был прерван guidance при runtime max-attempts=1; его final report не завершён, поэтому прототип не включён в доставку и не считается независимым finished review. Промежуточная работа сохранена в изолированном worker workspace. Диагноз выше основан на реальных operator experiments и pinned source.

Исходный Actions FAIL сохранён. GitHub Actions workflow остаётся disabled. Product UI, Codex subscription pool и production deploy не менялись.
