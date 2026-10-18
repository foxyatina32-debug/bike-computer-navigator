# Тесты

`regression.py` — регрессионные проверки ошибок, найденных при QA-аудите. Приложение запускается в настоящем Chromium (размер iPhone, эмуляция GPS) с настоящими Leaflet 1.9.4 и leaflet-rotate 0.2.8; внешние сервисы (тайлы карт, BRouter, Overpass, Nominatim) подменены заглушками — их реальная работа этими тестами не проверяется.

Нужно: Python 3, `pip install playwright`, Chromium для Playwright (или путь к нему в `CHROME_PATH`), git (библиотеки скачиваются в `tests/.cache` при первом запуске).

```
python3 tests/regression.py
```
