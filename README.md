# SpecIQ — электроника: каталог, цены и сигналы сообщества

MVP по концепции из Google Docs: единый каталог электроники, региональные предложения, история цен, импорт данных, очередь Celery и объяснимое извлечение частых технических проблем из отзывов.

> **Ответственный сбор данных:** подключайте только API/фиды и страницы, на сбор которых у вас есть право. Система не обходит CAPTCHA/Cloudflare, не ротирует IP для обхода ограничений и не следует HTTP-редиректам фидов. Для конкретного источника используйте его официальный API или согласованный экспорт.

## Быстрый запуск без Docker

Требуются Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Откройте <http://localhost:8000>. Локально используется SQLite, демонстрационные данные синтетические. Swagger UI: <http://localhost:8000/docs>.

По умолчанию задания обрабатываются фоново в процессе FastAPI. Для настоящей очереди используйте Compose.

### Подключение разрешённого JSON-фида

В `.env` перечислите только домены, на которые у вас есть разрешение:

```dotenv
AUTHORIZED_SOURCE_HOSTS=api.partner.example,*.feeds.partner.example
```

Затем в панели выберите «Источники → Импортировать данные» и вставьте HTTPS URL. Коллектор принимает JSON-массив или объект с ключом `records`, валидирует каждую запись, ограничивает ответ 5 МБ/500 записей и делает не более одного запроса в секунду на хост. DNS-адрес назначения проверяется на публичную маршрутизацию; редиректы, IP-адреса вместо доменов и хосты вне allowlist отклоняются. Специфические авторизации (ключи/подписи поставщика) добавляются в отдельный адаптер, а не в URL.

Если панель опубликована наружу, задайте `INGESTION_API_KEY` и передавайте его заголовком `X-Ingestion-Key` для загрузки предложений и отзывов. Не помещайте ключи API источников в URL или в репозиторий.

## Запуск PostgreSQL + pgvector + Redis + Celery

```bash
docker compose up --build
```

- Web/API: <http://localhost:8000>
- Документация API: <http://localhost:8000/docs>
- PostgreSQL создаёт расширения `uuid-ossp` и `vector`, затем таблицы `products`, `offers`, `price_snapshots`, `reviews`, `knowledge_vector` и `ingestion_jobs`.
- Worker слушает Redis и называется `hardware_celery_worker`.

Для локального запуска Compose пароль по умолчанию простой. Перед публикацией задайте `POSTGRES_PASSWORD`, `INGESTION_API_KEY`, не используйте демо-данные и настройте резервное копирование.

## Что реализовано

- Каталог с поиском по названию/бренду/модели, категориями и фильтрами по региону, источнику, состоянию и цене.
- Нормализация ключей бренда/модели и консервативное fuzzy-сопоставление только при совпадающих бренде и категории; история изменений цены.
- JSON-пакетная загрузка вручную или из allowlisted HTTPS JSON feed с отслеживанием статуса, прогресса и ошибок; локальный режим и Celery/Redis.
- Загрузка отзывов, правила тональности и метки проблем (шум/охлаждение, перегрев, батарея, экран, надёжность, производительность) на английском и русском.
- Хранилище `knowledge_vector` с совместимым с pgvector полем `vector(384)`; вычисление эмбеддингов подключается отдельно, тяжёлая модель автоматически не запускается.
- Адаптивная панель: клавиатурная навигация, масштаб текста, контрастный режим и озвучивание активного раздела браузерным синтезатором речи.

## API: импорт предложений

```bash
curl -X POST http://localhost:8000/api/ingestion/jobs \
  -H 'Content-Type: application/json' \
  -H 'X-Ingestion-Key: your-local-key' \
  -d '{
    "source": "authorized_partner_feed",
    "records": [{
      "name": "Example laptop 14-inch",
      "brand": "Example",
      "model": "E14 Gen 1",
      "category": "Laptops",
      "region": "Netherlands",
      "condition": "new",
      "price": "899.00",
      "currency": "EUR",
      "external_id": "partner-item-123",
      "availability": true
    }]
  }'
```

Основные маршруты: `GET /api/dashboard`, `GET /api/products`, `GET /api/products/{id}`, `GET /api/products/{id}/history`, `GET /api/products/{id}/insights`, `POST /api/ingestion/jobs`, `POST /api/ingestion/feed-jobs`, `GET /api/ingestion/jobs`, `POST /api/reviews/batch`, `GET /api/sources`.

Загрузка отзывов: `POST /api/reviews/batch` с телом `{ "reviews": [{ "product_name": "...", "source": "authorized_forum_export", "content": "...", "rating": 4.5 }] }`.

## Проверки

```bash
pytest -q
```

Для production-схемы следует заменить `create_all` в lifespan на миграции Alembic, настроить секреты, ротацию логов, мониторинг очереди, политики хранения исходного текста и отдельные адаптеры поставщиков.
