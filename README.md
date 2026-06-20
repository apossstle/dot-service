# Polygon Service

Сервис для хранения полигонов и проверки попадания точки в геометрию.
Веб-интерфейс — карта OpenStreetMap: рисование полигонов и проверка точки кликом.

**Требования:** Python **3.10+**, только стандартная библиотека (внешние пакеты не нужны).

## Быстрый старт

Откройте в браузере: **http://127.0.0.1:8080**

Если порт **8080** занят (`Address already in use` / «порт занят»), укажите другой, например **9090**.

### macOS / Linux

На macOS команда `python` часто отсутствует — используйте **`python3`**:

```bash
cd /path/to/dot-service
python3 main.py
```

В терминале появится URL (по умолчанию `http://127.0.0.1:8080`) — откройте его в браузере.

Другой порт:

```bash
python3 main.py --port 9090
# или
PORT=9090 python3 main.py
```

Проверка:

```bash
curl http://127.0.0.1:8080/health
```

Тесты:

```bash
python3 tests/test_all.py
```

### Windows

Установите Python 3.10+ с [python.org](https://www.python.org/downloads/) и отметьте **«Add python.exe to PATH»** в установщике.

**Командная строка (cmd):**

```bat
cd C:\path\to\dot-service
python main.py
```

Если `python` не находится, используйте лаунчер **`py`**:

```bat
py -3 main.py
```

Другой порт:

```bat
python main.py --port 9090
rem или
set PORT=9090
python main.py
```

**PowerShell:**

```powershell
cd C:\path\to\dot-service
python main.py
# другой порт:
$env:PORT = "9090"
python main.py
```

Проверка (в cmd или PowerShell, если есть `curl`):

```bat
curl http://127.0.0.1:8080/health
```

Или откройте в браузере: http://127.0.0.1:8080/health

Тесты:

```bat
python tests\test_all.py
rem или: py -3 tests\test_all.py
```

### Параметры запуска

| Параметр / переменная | По умолчанию | Описание |
|----------------------|--------------|----------|
| `--port` / `PORT` | `8080` | HTTP-порт |
| `--host` / `HOST` | `127.0.0.1` | Адрес привязки |
| `--cell-size` / `CELL_SIZE` | `1.0` | Размер ячейки `GridIndex` |

Пример (macOS/Linux — `python3`, Windows — `python` или `py -3`):

```bash
python3 main.py --host 127.0.0.1 --port 8080 --cell-size 2.5
```

Установка как пакета (опционально):

```bash
pip install -e .
polygon-service --port 8080
```

## Возможности

- CRUD над полигонами (HTTP REST).
- Форматы ввода: GeoJSON и WKT.
- Типы геометрии: `Polygon` (с отверстиями) и `MultiPolygon`.
- Два алгоритма point-in-polygon: ray casting и winding number.
- Различение трёх состояний точки: внутри, снаружи, на границе.
- Пространственный индекс `GridIndex` для ускорения PIP-запросов.
- Веб-карта на Leaflet с тайлами OSM, рисованием и проверкой точки кликом.

## Структура проекта

```
.
├── geometry/
│   ├── types.py        Point, Ring, Polygon, MultiPolygon
│   ├── algorithms.py   ray casting, winding number, polygon/multipolygon contains
│   ├── index.py        BoundingBoxIndex, GridIndex
│   └── wkt.py          парсер и сериализатор WKT
├── storage/
│   └── repository.py   PolygonRepository
├── api/
│   ├── server.py       HTTP-обработчики
│   └── templates/
│       └── index.html  веб-интерфейс на Leaflet
├── tests/
│   └── test_all.py     unit + интеграционные тесты
├── main.py             точка входа
└── pyproject.toml
```

## HTTP API

| Метод  | URL                        | Описание                              |
|--------|----------------------------|---------------------------------------|
| GET    | `/`                        | Веб-интерфейс                         |
| GET    | `/health`                  | Статус сервиса                        |
| GET    | `/stats`                   | Статистика `GridIndex`                |
| GET    | `/polygons`                | Список всех полигонов                 |
| POST   | `/polygons`                | Создать полигон                       |
| GET    | `/polygons/{id}`           | Получить полигон по ID                |
| PUT    | `/polygons/{id}`           | Обновить полигон                      |
| DELETE | `/polygons/{id}`           | Удалить полигон                       |
| POST   | `/query/point-in-polygon`  | Найти полигоны, содержащие точку      |
| OPTIONS| `*`                        | CORS preflight                        |

Ошибки: `400` / `404` / `500` с телом `{"error": "текст"}`.

`GET /stats` возвращает, например:

```json
{
  "polygon_count": 2,
  "index": {
    "type": "GridIndex",
    "cell_size": 1.0,
    "polygon_count": 2,
    "occupied_cells": 1,
    "avg_polygons_per_cell": 2.0
  }
}
```

### Создание полигона (GeoJSON)

```http
POST /polygons
Content-Type: application/json

{
  "name": "Зона А",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[37.6,55.7],[37.7,55.7],[37.7,55.8],[37.6,55.8],[37.6,55.7]]]
  },
  "properties": {"region": "Moscow"}
}
```

### Создание полигона (WKT)

```json
{
  "name": "Зона А",
  "wkt": "POLYGON ((37.6 55.7, 37.7 55.7, 37.7 55.8, 37.6 55.8, 37.6 55.7))"
}
```

### Полигон с отверстием

GeoJSON: первый массив координат — внешний контур, остальные — отверстия.

```json
{
  "type": "Polygon",
  "coordinates": [
    [[0,0],[20,0],[20,20],[0,20],[0,0]],
    [[5,5],[15,5],[15,15],[5,15],[5,5]]
  ]
}
```

WKT: `POLYGON ((0 0, 20 0, 20 20, 0 20, 0 0), (5 5, 15 5, 15 15, 5 15, 5 5))`

### Проверка точки

```http
POST /query/point-in-polygon
Content-Type: application/json

{
  "point": [37.65, 55.75],
  "algorithm": "ray_casting",
  "include_boundary": true
}
```

Параметры:

- `point` — `[x, y]` или `[lng, lat]` для географических данных, обязательно.
- `algorithm` — `ray_casting` (по умолчанию) или `winding_number`.
- `include_boundary` — считать ли точку на границе попаданием (по умолчанию `true`).

В ответе — список полигонов, которым принадлежит точка, каждый
сериализован и в GeoJSON, и в WKT.

## Алгоритмы point-in-polygon

**Ray casting.** Из проверяемой точки проводится горизонтальный луч вправо,
считаются пересечения с рёбрами полигона. Нечётное число — внутри,
чётное — снаружи. Сложность O(n) на одно кольцо.

**Winding number.** Считается, сколько раз контур обматывается вокруг
точки. Если ноль — снаружи, иначе — внутри. Алгоритм устойчивее к
самопересечениям. Сложность также O(n).

Перед запуском любого из них точка проверяется на принадлежность
рёбрам с допуском `EPSILON = 1e-10`: если лежит — возвращается
`on_boundary` без дальнейших вычислений.

### Граничные случаи

| Случай                              | Результат      |
|-------------------------------------|----------------|
| Точка на ребре внешнего контура     | `on_boundary`  |
| Точка в вершине                     | `on_boundary`  |
| Точка внутри отверстия              | `outside`      |
| Точка на границе отверстия          | `on_boundary`  |
| Точка попадает в несколько полигонов| возвращаются все |

## Пространственный индекс

Наивная проверка точки против N полигонов — O(N·m), где m — среднее число
рёбер. Сервис использует `GridIndex`: пространство делится на
равномерные ячейки, каждый полигон регистрируется во всех ячейках,
которые пересекает его bounding box. При запросе:

1. По координатам точки за O(1) находится ячейка.
2. Из ячейки берутся кандидаты — обычно k ≪ N.
3. Точная PIP-проверка выполняется только для кандидатов.

Размер ячейки задаётся при запуске (`--cell-size` / `CELL_SIZE`) в **тех же единицах, что и координаты**.
Для lng/lat значение `1.0` по умолчанию — это ~1°, сетка очень грубая; для города обычно
подходят `0.01`–`0.05`, например:

```bash
python3 main.py --cell-size 0.02
```

Слишком мелкая сетка — много памяти; слишком крупная — индекс почти не помогает.

## Тесты

```bash
python3 tests/test_all.py
python3 -m unittest tests.test_all -v
```

94 теста: геометрия, индексы, репозиторий, HTTP API (включая CRUD по id).

## Ограничения

- Данные только in-memory, после перезапуска пропадают.
- `GridIndex` с фиксированным шагом сетки неудобен при сильно разной плотности объектов.
- WKT: только `POLYGON` и `MULTIPOLYGON`, без WKB.
- Один поток `HTTPServer`, без аутентификации.
