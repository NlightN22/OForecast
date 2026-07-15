# OForecast Sales Forecast

## English

### Overview

This project forecasts monthly brand sales by employee and for the company as a
whole. It contains the forecasting engine and two Excel-based applications:

- `ts_forecast` - the shared time-series forecasting engine and web service.
- `sales_forecast` - runs the forecasting engine locally.
- `sales_forecast_api` - sends forecasting tasks to a remote OForecast API.

Both applications read the same sales workbook and generate two report sheets:

- `Brand Totals` - total forecast for each brand.
- `Employee Forecasts` - forecast for every employee and brand combination.

`TBATS_y` is disabled in both workflows because it significantly increases the
calculation time without improving the selected forecasts for the current data.

### Requirements

- Python 3.11 or newer.
- Access to the OForecast server for the API version.
- An input workbook matching the structure described below.

Install the dependencies from the project root:

```bash
python -m venv venv
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt
```

### Input workbook

Place a copy of `Sales.xlsx` in the application directory you want to run:

- Local: `sales_forecast/Sales.xlsx`
- API: `sales_forecast_api/Sales.xlsx`

The default workbook layout is configured as follows:

- Row 8 contains brand names.
- Column B contains employee names and month labels.
- Brand values start in column C.
- Month labels use a format such as `Январь 2026 г.`.
- Zero sales must remain in the history; they are valid observations.
- Rows named `Итог`, `Итого`, `Всего`, or `Общий итог` are not treated as data.

If the workbook layout changes, update the constants in the corresponding
`config.py` file.

### Local version

The local version calls `ts_forecast` directly and does not require a running
HTTP service.

Run it from the project root:

```bash
./venv/bin/python -m sales_forecast.main
```

Configuration: `sales_forecast/config.py`

Output: `sales_forecast/output/Sales_Forecast.xlsx`

The workbook title is `Local version OForecast`. The report contains four
brand totals and the available employee-brand forecasts. Individual series with
less than `MIN_HISTORY_MONTHS` observations or no positive sales are skipped.

### API version

The API version converts each series to the OForecast text contract and sends
the requests sequentially to the endpoint configured in
`sales_forecast_api/config.py`.

Run it from the project root:

```bash
./venv/bin/python sales_forecast_api/main.py
```

Configuration: `sales_forecast_api/config.py`

Output: `sales_forecast_api/output/Sales_Forecast_API.xlsx`

The workbook title is `API version OForecast`. The current input creates 24 API
tasks: four brand totals and twenty employee-brand series. Runtime depends on
the server and enabled models and may exceed 15 minutes.

Important API settings:

- `API_URL` - forecast endpoint.
- `MODELS` - models sent to the server; `TBATS_y` is intentionally excluded.
- `USE_ALL = False` - use only the configured model list.
- `FILL_MISSING_WITH_MEAN = False` - missing recognized periods use zero.
- `DROP_ZERO_ROWS = False` - preserve zero-sales months.

API request format:

```json
{
  "raw": "period | value\nJanuary 2023 | 1200\nFebruary 2023 | 1350",
  "models": ["SES_log", "ETS_log_trend=None_seasonal=None", "AutoARIMA_log"],
  "use_all": false,
  "fill_missing_with_mean": false
}
```

Fields: `raw` is one time series in the OForecast text format, `models` are the
requested model names, `use_all=false` limits the run to that list, and
`fill_missing_with_mean=false` keeps missing periods from being interpolated with
the mean value.

The response is JSON from the OForecast server. The application uses the final
forecast, intervals, selected model, selected dataset, and metadata for the
Excel report.

### Web service

Run the OForecast web application locally:

```bash
./venv/bin/uvicorn ts_forecast.web.app:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`.

To match the Excel applications in the web interface, disable `Use all models`,
select the same models, exclude `TBATS_y`, and keep interpolation disabled.

Docker Compose can run the published web image:

```bash
docker compose up -d
```

The published service is then available at `http://localhost:80`.

### Troubleshooting

- Close the output workbook before running the application; Excel may lock it.
- If forecasts differ, compare every historical value, including zeros and the
  final month. Different input values correctly produce different forecasts.
- If the API request fails, verify network access and `API_URL`.
- Optional model availability depends on the installed package versions.

---

## Русский

### Обзор

Проект прогнозирует ежемесячные продажи брендов по сотрудникам и по компании в
целом. В проект входят движок прогнозирования и два приложения для Excel:

- `ts_forecast` - общий движок временных рядов и веб-сервис.
- `sales_forecast` - локальный запуск движка прогнозирования.
- `sales_forecast_api` - отправка задач на удаленный API OForecast.

Оба приложения читают одинаковую книгу продаж и создают две вкладки отчета:

- `Brand Totals` - общий прогноз по каждому бренду.
- `Employee Forecasts` - прогноз по каждой комбинации сотрудника и бренда.

Модель `TBATS_y` отключена в обоих вариантах, поскольку она существенно
увеличивает время расчета и не улучшает выбранные прогнозы на текущих данных.

### Требования

- Python 3.11 или новее.
- Доступ к серверу OForecast для API-версии.
- Исходная книга, соответствующая описанной ниже структуре.

Установка зависимостей из корня проекта:

```bash
python -m venv venv
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt
```

### Исходная книга

Поместите копию `Sales.xlsx` в директорию запускаемого приложения:

- Локальная версия: `sales_forecast/Sales.xlsx`
- API-версия: `sales_forecast_api/Sales.xlsx`

Структура книги по умолчанию:

- В строке 8 находятся названия брендов.
- В столбце B находятся сотрудники и названия месяцев.
- Значения продаж по брендам начинаются со столбца C.
- Месяцы записаны в формате `Январь 2026 г.`.
- Нулевые продажи должны оставаться в истории как корректные наблюдения.
- Строки `Итог`, `Итого`, `Всего` и `Общий итог` не считаются данными.

Если структура книги изменится, скорректируйте константы в соответствующем
файле `config.py`.

### Локальная версия

Локальная версия вызывает `ts_forecast` напрямую и не требует запущенного
HTTP-сервиса.

Запуск из корня проекта:

```bash
./venv/bin/python -m sales_forecast.main
```

Настройки: `sales_forecast/config.py`

Результат: `sales_forecast/output/Sales_Forecast.xlsx`

Заголовок книги: `Local version OForecast`. Отчет содержит четыре общих
прогноза брендов и доступные прогнозы по сотрудникам. Ряды короче
`MIN_HISTORY_MONTHS` или без положительных продаж пропускаются.

### API-версия

API-версия преобразует каждый ряд в текстовый формат OForecast и последовательно
отправляет запросы на адрес из `sales_forecast_api/config.py`.

Запуск из корня проекта:

```bash
./venv/bin/python sales_forecast_api/main.py
```

Настройки: `sales_forecast_api/config.py`

Результат: `sales_forecast_api/output/Sales_Forecast_API.xlsx`

Заголовок книги: `API version OForecast`. Для текущего файла выполняются 24
запроса: четыре общих ряда брендов и двадцать рядов сотрудников. Время зависит
от сервера и моделей и может превышать 15 минут.

Основные настройки API:

- `API_URL` - адрес прогнозного API.
- `MODELS` - передаваемые модели; `TBATS_y` намеренно исключена.
- `USE_ALL = False` - использовать только указанный список моделей.
- `FILL_MISSING_WITH_MEAN = False` - пропущенные периоды заполняются нулями.
- `DROP_ZERO_ROWS = False` - месяцы с нулевыми продажами сохраняются.

Формат API-запроса:

```json
{
  "raw": "period | value\nЯнварь 2023 г. | 1200\nФевраль 2023 г. | 1350",
  "models": ["SES_log", "ETS_log_trend=None_seasonal=None", "AutoARIMA_log"],
  "use_all": false,
  "fill_missing_with_mean": false
}
```

Поля: `raw` - один временной ряд в текстовом формате OForecast, `models` -
запрошенные модели, `use_all=false` ограничивает расчет этим списком, а
`fill_missing_with_mean=false` отключает интерполяцию пропусков средним.

Ответом является JSON от сервера OForecast. Приложение берет из него прогноз,
интервалы, выбранную модель, выбранный датасет и служебные данные для
Excel-отчета.

### Веб-сервис

Локальный запуск веб-приложения OForecast:

```bash
./venv/bin/uvicorn ts_forecast.web.app:app --host 0.0.0.0 --port 8000
```

Откройте `http://localhost:8000`.

Чтобы повторить настройки Excel-приложений в веб-интерфейсе, отключите
`Use all models`, выберите тот же набор моделей без `TBATS_y` и не включайте
интерполяцию пропущенных периодов.

Запуск опубликованного веб-образа через Docker Compose:

```bash
docker compose up -d
```

После запуска сервис доступен по адресу `http://localhost:80`.

### Решение проблем

- Закройте итоговый файл перед запуском: Excel может блокировать его запись.
- При расхождении прогнозов сравните всю историю, включая нули и последний
  месяц. Разные входные значения закономерно дают разные прогнозы.
- При ошибке API проверьте сеть и значение `API_URL`.
- Доступность дополнительных моделей зависит от версий установленных пакетов.
