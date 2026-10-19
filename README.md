# bike-computer-navigator

Велокомпьютер с навигацией для iPhone (Израиль, MTB и город): запись поездок, карты Israel Hiking / CyclOSM / OpenTopoMap, построение маршрутов под тип велосипеда (BRouter, OSRM, встроенный движок по OpenStreetMap), трассы из OSM, импорт GPX/KML/KMZ/TCX и ссылок, передача маршрута в Google Maps и Waze, офлайн-карты.

Открывать в Safari по адресу GitHub Pages, затем «Поделиться» → «На экран Домой».

## Google Карты и маршруты Google (необязательно)

Без ключа всё работает на бесплатных картах и маршрутизаторах. С ключом Google появляются карта Google, движок маршрутов «Google» (велорежим Google Maps) и поиск адресов Google.

1. console.cloud.google.com → создать проект и привязать платёжный аккаунт (в пределах бесплатных лимитов Google ничего не списывает).
2. «APIs & Services» → «Library» → включить **Map Tiles API**, **Routes API** и при желании **Places API (New)**.
3. «Credentials» → «Create credentials» → «API key». В ограничениях ключа: «Websites» → `https://foxyatina32-debug.github.io/*`; «API restrictions» → только эти три API.
4. В приложении: Профиль → «Google Карты» → вставить ключ → «Сохранить». Приложение проверит карту и маршруты.

Маршруты Google: «Маршруты» → «Построить» → движок «Google», или «Из точки в точку» с покрытием «По дорогам». Велорежим Google — бета: велодорожки учтены не везде, тропы и бездорожье Google не знает (для MTB — BRouter или GPX). Маршруты и поиск Google показываются на карте Google. Высоты для профиля берутся из Open-Meteo.
