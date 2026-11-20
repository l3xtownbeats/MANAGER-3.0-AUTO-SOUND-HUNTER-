# MANAGER 3.0 — чистая консолидация рабочих наработок

**Дата:** 2026-11-20  
**Целевой репозиторий:** `l3xtownbeats/MANAGER-3.0-AUTO-SOUND-HUNTER-`  
**Интеграционная ветка:** `integration/manager-3.0-clean`  
**База:** `main`  
**Выбранный источник кода:** `fix/manager-3-neon-stage-default-skin1` @ `b68de698bead76a9f4a37eb4c38aca98220ddbc6`

## Почему выбран этот источник

Из семи веток репозитория выбрана ветка `fix/manager-3-neon-stage-default-skin1`: это наиболее полный снимок Manager 3.0.0-dev9. В нём уже присутствуют GUI, portable build/installer scripts, NEON STAGE assets, task journal, транзакционные операции, pattern/riff extraction, chord analysis, pitch map, performance manifest, library structure и соответствующие регрессионные тесты.

Выбор не означает, что ветка уже проверена: на момент переноса отдельного успешного CI run для её HEAD не найдено. Поэтому содержимое сначала ставится в интеграционную ветку, а не объявляется готовым релизом и не принимается в main без CI.

## Перенос и сохранение

- Снимок выбранной ветки наложен на существующий `main` с сохранением ancestry целевой ветки.
- Ранее существующие inventory, SHA-256 manifests, L3XTOWN routing/audit отчёты и LibraryManager исходные материалы сохранены; одинаковые файлы не дублировались второй копией.
- Старое изображение `IMG_20261119_123325.jpg` и исторический прототип `acoustic_signal_audit.py.txt` выведены из корня в `docs/archive/` для сохранения исходного содержимого без захламления корня.
- Основной интерфейс Manager остаётся с шестью утверждёнными действиями и темой NEON STAGE DEFAULT / SKIN-1. MELODY/PATTERN/AutoChords остаются функциями отдельного VST3, а не режимами Manager.
- Существующие правила сохранения оригиналов, review/license gates, запрета destructive similarity cleanup и отсутствия тяжёлых операций в audio callback сохранены.

## Точечные исправления перед CI

1. SFZ sample paths за пределами выбранной библиотеки теперь классифицируются как `OUTSIDE_LIBRARY` даже тогда, когда внешний файл существует. Ранее проверка сначала смотрела на существование файла и могла ошибочно пометить его как FOUND.
2. SFZ `#include` за пределами корня библиотеки блокируется до чтения содержимого; добавлен regression test.
3. Диагностика pattern loop теперь называет отсутствующие/некорректные поля отдельно: `loop_start_sample`, `loop_end_sample`, `loop_end_after_start`, `loop_end_within_clip`.
4. Тесты синхронизированы с актуальной схемой note metadata (`asset_role`) и правилом chromatic pitch map: соседняя нота может иметь только неиграбельное fallback-предложение, пока оно не прошло QA.
5. Multi-mode fixture для теста readiness явно объявляет оба режима; gate кода не ослаблялся.

## Ограничения статуса

- Это консолидация исходного кода и документации, а не подтверждение завершённой сборки.
- Windows Portable ZIP/Installer должны быть пересобраны на точном SHA интеграционной ветки.
- Все unit/regression tests должны пройти на точном SHA этой ветки.
- Для релиза необходимы clean Windows 10 x64 install/startup checks и тест на реальной пользовательской библиотеке.
- READY для ассетов допускается только после plugin file/mapping access и playback probes; прохождение тестов менеджера само по себе не закрывает эти проверки.
