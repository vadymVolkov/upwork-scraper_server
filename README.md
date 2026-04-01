# Upwork Job Scraper API Server

HTTP сервер для поиска вакансий на Upwork с использованием FastAPI.

## Documentation

- CLI документация: `README-CLI.md`
- REST API документация: `README-API.md`

## Установка

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Создайте файл `.env` в корне проекта:
```env
UPWORK_USERNAME=your_email@example.com
UPWORK_PASSWORD=your_password
```

3. Настройте параметры поиска в файле `config.toml` (опционально)

## Запуск сервера

```bash
python server.py
```

Или используя uvicorn напрямую:
```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

Сервер будет доступен по адресу: `http://localhost:8000`

## API Endpoints

### GET `/search`

Поиск вакансий на Upwork.

**Параметры:**
- `query` (обязательный) - текст для поиска
- `limit` (опциональный) - количество результатов (1-100, по умолчанию: 10)

**Пример запроса:**
```
GET /search?query=n8n&limit=10
```

**Пример ответа:**
```json
{
  "success": true,
  "query": "n8n",
  "limit": 10,
  "count": 10,
  "jobs": [
    {
      "title": "Job Title",
      "description": "Job Description",
      "url": "https://www.upwork.com/jobs/...",
      ...
    }
  ]
}
```

**Полный URL для запроса:**
```
http://localhost:8000/search?query=n8n&limit=10
```

## Описание возвращаемых данных

Каждая вакансия в массиве `jobs` содержит следующие поля:

### Основная информация о вакансии
- `title` - Название вакансии
- `description` - Описание вакансии
- `url` - Ссылка на вакансию на Upwork
- `job_id` - Уникальный идентификатор вакансии
- `type` - Тип вакансии: "Hourly" или "Fixed"
- `level` - Уровень опыта: "Entry", "Intermediate", "Expert"
- `duration` - Длительность проекта
- `category` - Категория вакансии
- `category_name` - Название категории
- `category_urlSlug` - URL slug категории
- `categoryGroup_name` - Название группы категорий
- `categoryGroup_urlSlug` - URL slug группы категорий

### Финансовая информация
- `hourly_min` - Минимальная почасовая ставка
- `hourly_max` - Максимальная почасовая ставка
- `fixed_budget_amount` - Сумма для фиксированной оплаты
- `currency` - Валюта (USD, EUR и т.д.)
- `connects_required` - Количество коннектов, необходимых для подачи заявки

### Информация о клиенте
- `client_country` - Страна клиента
- `client_company_size` - Размер компании клиента
- `client_industry` - Отрасль клиента
- `client_hires` - Количество наймов клиента
- `client_rating` - Рейтинг клиента (0-5)
- `client_reviews` - Количество отзывов о клиенте
- `client_total_spent` - Общая сумма, потраченная клиентом
- `buyer_hire_rate_pct` - Процент найма клиента (%)
- `buyer_avgHourlyJobsRate_amount` - Средняя почасовая ставка, которую платит клиент
- `buyer_jobs_openCount` - Количество открытых вакансий клиента
- `buyer_jobs_postedCount` - Общее количество вакансий, размещенных клиентом
- `buyer_stats_hoursCount` - Общее количество часов работы с клиентом
- `buyer_stats_totalJobsWithHires` - Количество вакансий с наймами
- `buyer_stats_activeAssignmentsCount` - Количество активных заданий
- `buyer_company_contractDate` - Дата регистрации компании клиента
- `buyer_location_city` - Город клиента
- `buyer_location_countryTimezone` - Часовой пояс страны клиента
- `buyer_location_localTime` - Локальное время клиента
- `buyer_location_offsetFromUtcMillis` - Смещение от UTC в миллисекундах

### Активность клиента
- `clientActivity_invitationsSent` - Количество отправленных приглашений
- `clientActivity_totalHired` - Общее количество наймов
- `clientActivity_totalInvitedToInterview` - Количество приглашенных на интервью
- `clientActivity_unansweredInvites` - Количество неотвеченных приглашений
- `lastBuyerActivity` - Последняя активность клиента

### Дополнительная информация
- `applicants` - Количество заявителей
- `numberOfPositionsToHire` - Количество позиций для найма
- `skills` - Список требуемых навыков
- `qualifications` - Квалификации/требования
- `questions` - Вопросы от клиента
- `contractorTier` - Уровень подрядчика
- `payment_verified` - Проверен ли способ оплаты (true/false)
- `phone_verified` - Проверен ли телефон (true/false)
- `premium` - Премиум вакансия (true/false)
- `enterpriseJob` - Корпоративная вакансия (true/false)
- `isContractToHire` - Контракт с возможностью найма (true/false)
- `ts_create` - Временная метка создания вакансии
- `ts_publish` - Временная метка публикации вакансии

### Пример полного ответа
```json
{
  "success": true,
  "query": "n8n",
  "limit": 10,
  "count": 1,
  "jobs": [
    {
      "title": "n8n Workflow Automation Developer",
      "description": "We need an experienced n8n developer...",
      "url": "https://www.upwork.com/jobs/~abc123",
      "job_id": "abc123",
      "type": "Hourly",
      "level": "Intermediate",
      "hourly_min": "25",
      "hourly_max": "50",
      "fixed_budget_amount": "0",
      "currency": "USD",
      "client_country": "United States",
      "client_rating": "4.8",
      "client_reviews": "15",
      "client_hires": "8",
      "skills": ["n8n", "API Integration", "Automation"],
      "payment_verified": true,
      "connects_required": "6"
    }
  ]
}
```

## Конфигурация

- **Credentials** (логин/пароль) - хранятся в файле `.env` (не коммитится в Git)
- **Настройки поиска** - хранятся в файле `config.toml`
- **Cookies** - автоматически сохраняются в папке `cookies/` для повторного использования

## Примечания

- Браузер работает в headless режиме (без отображения окна)
- Cookies сохраняются для уменьшения количества запросов к Upwork
- При первом запуске может потребоваться решение капчи
- Для работы требуется активное интернет-соединение
