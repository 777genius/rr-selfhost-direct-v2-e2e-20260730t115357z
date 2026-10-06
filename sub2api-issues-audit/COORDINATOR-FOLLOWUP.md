# Завершение исследования комментариев координатором

Полный снимок gh CLI от 2026-09-30T20:21:04Z: **52 threads / 80 comments**, все страницы получены. Hosted audit worker прочитал первоначальные 48 threads / 66 comments; его исходные результаты и ограничения сохранены. Координатор отдельно прочитал последние четыре thread. Это дополнение завершает комментарии, не переписывая историю worker evidence.

- [#2337](https://github.com/Wei-Shaw/sub2api/issues/2337): комментариев нет. Нового подтверждения исправления не появилось.
- [#6146](https://github.com/Wei-Shaw/sub2api/issues/6146): репортёр описывает повторяемую несовместимость fc_/ctc_ и временный обход через новую сессию. Поздний комментарий ссылается на [PR #6078](https://github.com/Wei-Shaw/sub2api/pull/6078). gh CLI подтвердил MERGED 2026-08-25, commit e8cb019fabf8b55199436229044cbf9aa7a82564. В закреплённом v0.2.11 `responses_client_tools.go` есть типизация ctc_/tsc_ и обратное отображение. Это source + merged-fix evidence; наш native function-tool тест не доказывает custom_tool_call/tool_search_call replay. Нужен отдельный canary этих типов.
- [#6185](https://github.com/Wei-Shaw/sub2api/issues/6185): один дополнительный репортёр подтверждает похожий симптом. Проверяемого fix или версии в комментарии нет.
- [#6402](https://github.com/Wei-Shaw/sub2api/issues/6402): несколько подтверждений симптома delegation bootstrap; отдельный автор предлагает узкий reference implementation, последний комментарий спрашивает о решении. Это не подтверждение включённого и проверенного fix. Delegation/subagents/heartbeat bootstrap нашим обычным review canary не покрыты.

Число подтверждающих комментариев не является числом независимых воспроизведений. Внешние блоги/reference repo в комментариях не исполнялись и не приняты как инструкции. Raw bodies и изображения не экспортируются в публичный отчёт.

Продолжение старого audit job через runtime было отклонено: `status_requires_review`, затем export scanner `handoff_raw_secret_rejected:sub2api-issues-audit/verify.py` на файле тестовых sentinel fixtures. Защита не обходилась; лёгкий разбор четырёх комментариев выполнил координатор. Исходный HANDOFF worker описывает старый снимок, а итоговые product conclusions находятся в `sub2api-spike/REPORT.md`.
