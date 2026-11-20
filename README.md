# AUTO SOUND HUNTER MANAGER 3.0

Самостоятельный Windows-инструмент для безопасного импорта, анализа, классификации и подготовки гитарной библиотеки для отдельного VST3-инструмента **POP PUNK GUITAR ULTIMATE**.

Manager не является плагином и не воспроизводит гитарные партии. Он подготавливает и проверяет материал, который затем использует VST3.

## Утверждённая основа

- Платформа: Windows 10 x64.
- Главный экран: ровно шесть действий — **IMPORT GUITAR**, **SCAN LIBRARY**, **START HUNTING**, **REVIEW QUEUE**, **BUILD LIBRARY**, **VERIFY / RECOVERY**.
- Визуальный стандарт: **NEON STAGE DEFAULT / SKIN-1**.
- Папки Samples: `FACTORY/`, `Import Sample Guitar/`, `OTHER/`.
- Исходные пользовательские материалы сохраняются. Импорт создаёт проверенные копии; перемещение/распределение и очистка выполняются отдельными подтверждаемыми транзакциями.
- Музыкальные гипотезы, похожесть, неизвестные артикуляции и неподтверждённые ноты не выдаются за подтверждённые данные.
- Точные дубликаты определяются SHA-256. Похожие тембры, ноты, ритмы и исполнения не являются основанием для удаления или объединения.
- FACTORY принимает только файлы с проверенной целостностью, подтверждённым музыкальным ревью и разрешёнными правами на использование/распространение.

## Структура библиотеки

```text
Samples/
├── FACTORY/
├── Import Sample Guitar/
└── OTHER/
```

Новые WAV, SFZ, библиотеки и поддерживаемые архивы помещаются в `Samples/Import Sample Guitar/`. Не создавайте дополнительные корневые папки внутри Samples.

## Запуск из исходников

Для разработки нужен Python 3.11. Из папки `LibraryManager`:

```bat
RUN_LIBRARY_MANAGER.bat
```

Полная инструкция пользователя: [LibraryManager/PORTABLE_USER_GUIDE_RU.md](LibraryManager/PORTABLE_USER_GUIDE_RU.md).  
Release notes: [LibraryManager/V3_0_RELEASE_NOTES_RU.md](LibraryManager/V3_0_RELEASE_NOTES_RU.md).

## Сборка Portable для Windows x64

На машине сборки Windows с Python 3.11:

```bat
BUILD_PORTABLE_WINDOWS.bat
```

Целевой архив:

`LibraryManager/dist/POP_PUNK_GUITAR_LIBRARY_MANAGER-windows-x64.zip`

Пользовательский Portable-пакет должен включать собственный runtime и запускаться без системного Python. Сборка/проверка считаются успешными только по конкретному CI run и проверке полученного архива; наличие скрипта сборки само по себе не является доказательством.

## Архитектура и статусы

Manager ведёт подготовку библиотеки через этапы импорта, сканирования, анализа, классификации, регистрации, проверки файлов/карт и проверки доступа плагина. Статус **READY** допустим только после всех обязательных проверок и подтверждённого playback probe. Если часть данных не проверена, результат должен оставаться PARTIAL / REVIEW REQUIRED / ERROR.

Подробная утверждённая база находится в [PROJECT_BASELINE_RU.md](LibraryManager/PROJECT_BASELINE_RU.md), решения — в [PROJECT_DECISION_LOG_RU.md](LibraryManager/PROJECT_DECISION_LOG_RU.md), ход задач — в [TASK_JOURNAL_RU.md](LibraryManager/TASK_JOURNAL_RU.md).

## Статус версии 3.0.0

Автоматические release gates пройдены на финальном commit `414df7bf92fd9d44ebcc357702c03388c72316b0`: Linux — 239/239 тестов; Windows — 239/239 тестов; Portable ZIP и Inno Setup Installer собраны, оба режима запуска и их data roots проверены. Версия GUI, unified manager и installer metadata — `3.0.0`. [Linux CI](https://github.com/l3xtownbeats/MANAGER-3.0-AUTO-SOUND-HUNTER-/actions/runs/44730743388) · [Windows build + smoke](https://github.com/l3xtownbeats/MANAGER-3.0-AUTO-SOUND-HUNTER-/actions/runs/44730743351). Состав, ограничения и скачивание — в [V3_0_RELEASE_NOTES_RU.md](LibraryManager/V3_0_RELEASE_NOTES_RU.md). Проверка реальной пользовательской папки Samples остаётся отдельным операторским этапом после установки.
