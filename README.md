# Polygon Service

Сервис для хранения полигонов и проверки «точка попадает в полигон?».  
Без внешних зависимостей — только стандартная библиотека Python 3.9+.

---

## Запуск

```bash
python main.py                        # localhost:8080
python main.py --port 9000            # другой порт
python main.py --host 0.0.0.0         # доступен извне
python main.py --cell-size 10.0       # размер ячейки индекса
```

После старта открой `http://127.0.0.1:8080` — там живая документация с примерами.

---

## Структура проекта

```
polygon_service/
├── geometry/
│   ├── types.py        # Point, Ring, Polygon — данные и GeoJSON-сериализация
│   ├── algorithms.py   # Ray Casting, Winding Number, polygon_contains()
│   └── index.py        # BoundingBoxIndex, GridIndex
├── storage/
│   └── repository.py   # PolygonRepository — CRUD + пространственный поиск
├── api/
│   ├── server.py       # HTTP REST-сервер
│   └── templates/
│       └── index.html  # Стартовая страница
├── tests/
│   └── test_all.py     # 66 тестов
└── main.py             # Точка входа
```

---

## API

| Метод  | URL                        | Описание                          |
|--------|----------------------------|-----------------------------------|
| GET    | `/`                        | Документация (HTML)               |
| GET    | `/health`                  | Статус сервиса                    |
| GET    | `/stats`                   | Статистика пространственного индекса |
| GET    | `/polygons`                | Список всех полигонов             |
| POST   | `/polygons`                | Создать полигон                   |
| GET    | `/polygons/{id}`           | Получить полигон по ID            |
| PUT    | `/polygons/{id}`           | Обновить полигон                  |
| DELETE | `/polygons/{id}`           | Удалить полигон                   |
| POST   | `/query/point-in-polygon`  | Найти полигоны, содержащие точку  |

---

## Примеры

### Создать полигон
```bash
curl -X POST http://localhost:8080/polygons \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Зона А",
    "geometry": {
      "type": "Polygon",
      "coordinates": [[[0,0],[10,0],[10,10],[0,10],[0,0]]]
    },
    "properties": {"region": "Moscow"}
  }'
```

### Полигон с отверстием
```bash
curl -X POST http://localhost:8080/polygons \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Пончик",
    "geometry": {
      "type": "Polygon",
      "coordinates": [
        [[0,0],[20,0],[20,20],[0,20],[0,0]],
        [[5,5],[15,5],[15,15],[5,15],[5,5]]
      ]
    }
  }'
```
Первый массив координат — внешний контур, каждый следующий — отверстие.

### Проверить точку
```bash
curl -X POST http://localhost:8080/query/point-in-polygon \
  -H "Content-Type: application/json" \
  -d '{
    "point": [5.0, 5.0],
    "algorithm": "ray_casting",
    "include_boundary": true
  }'
```

Параметры запроса:
- `point` — координаты `[x, y]`, обязательно
- `algorithm` — `"ray_casting"` (по умолчанию) или `"winding_number"`
- `include_boundary` — считать ли точку на границе попаданием, по умолчанию `true`

### Обновить полигон (частичное обновление)
```bash
curl -X PUT http://localhost:8080/polygons/{id} \
  -H "Content-Type: application/json" \
  -d '{"name": "Новое имя"}'
```
Передавать можно любое подмножество полей: `name`, `geometry`, `properties`.

---

## Алгоритмы point-in-polygon

**Ray Casting** — из точки P проводим горизонтальный луч вправо и считаем, сколько рёбер полигона он пересекает. Нечётное число → внутри, чётное → снаружи. Сложность O(n).

**Winding Number** — считаем, сколько раз контур полигона «обматывается» вокруг точки P. Если ноль раз — снаружи, иначе — внутри. Точнее при самопересечениях. Сложность O(n).

Оба алгоритма различают три состояния: `inside`, `outside`, `on_boundary`.

### Граничные случаи

| Ситуация                       | Результат      |
|--------------------------------|----------------|
| Точка на ребре полигона        | `on_boundary`  |
| Точка в вершине полигона       | `on_boundary`  |
| Точка внутри отверстия         | `outside`      |
| Точка на границе отверстия     | `on_boundary`  |
| Точка в нескольких полигонах   | возвращаются все |

---

## Пространственный индекс

Наивная проверка точки против N полигонов требует O(N·m) операций, где m — среднее число рёбер.

Сервис использует **GridIndex**: пространство делится на сетку ячеек. При запросе:
1. Ячейка точки находится за O(1)
2. Из ячейки берутся только кандидаты (k << N)
3. Точная PIP-проверка только кандидатов — O(k·m)

Параметр `--cell-size` задаёт размер ячейки. Хорошее значение — примерный диаметр типичного полигона в твоих данных.

---

## Тесты

```bash
python tests/test_all.py
```

66 тестов: типы, оба алгоритма, граничные случаи, индексы, репозиторий, HTTP API.

---

## Дальнейшее развитие

- [ ] Заменить `GridIndex` на R-Tree (`rtree`) — лучше работает при неравномерном распределении полигонов
- [ ] Добавить булевы операции (объединение, пересечение, разность) через `shapely`
- [ ] Персистентное хранилище (PostgreSQL + PostGIS)
- [ ] Поддержка `MultiPolygon` (GeoJSON)
- [ ] `FastAPI` + `pydantic` вместо голого `http.server`