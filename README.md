# AI Hedge Fund — MOEX

Форк проекта [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund), адаптированный для **российского фондового рынка** (Московская биржа / MOEX).

Система использует несколько AI-агентов для анализа акций и принятия торговых решений:

1. **Aswath Damodaran** — фокус на оценке стоимости (story, numbers, disciplined valuation)
2. **Ben Graham** — ценной инвестирование, покупка с запасом прочности
3. **Bill Ackman** — активистский инвестор
4. **Cathie Wood** — инвестирование в инновации и разрушение
5. **Charlie Munger** — покупка замечательных компаний по справедливой цене
6. **Michael Burry** — контрариан, поиск глубокой стоимости
7. **Mohnish Pabrai** — поиск низкорисковых удвоений
8. **Nassim Taleb** — анализ хвостовых рисков и антихрупкости
9. **Peter Lynch** — поиск "тенбаггеров" в повседневных компаниях
10. **Phil Fisher** — глубокое исследование "scuttlebutt"
11. **Rakesh Jhunjhunwala** — бычий инвестор
12. **Stanley Druckenmiller** — макро-легенда
13. **Warren Buffett** — оракул из Омахи
14. **Valuation Agent** — расчёт внутренней стоимости акций
15. **Sentiment Agent** — анализ настроений рынка
16. **Fundamentals Agent** — анализ фундаментальных данных
17. **Technicals Agent** — анализ технических индикаторов
18. **Risk Manager** — расчёт рисков и лимитов позиций
19. **Portfolio Manager** — принятие финальных торговых решений

> Система не совершает реальные сделки.

## Отличия от оригинального проекта

| Компонент | Оригинал | MOEX-форк |
|-----------|----------|-----------|
| Рынок | США (NYSE, NASDAQ) | Россия (MOEX, TQBR) |
| Цены | Financial Datasets API (платный) | MOEX ISS API (бесплатно, без ключа) |
| Финансовая отчётность | Financial Datasets API | Smart-Lab (МСФО, парсинг) |
| Новости | Financial Datasets API | Smart-Lab + Perplexity Sonar |
| Тикеры | AAPL, MSFT, NVDA... | SBER, GAZP, YDEX, LKOH... |
| Пакетный менеджер | Poetry | venv + pip |
| GUI | FastAPI + React | Streamlit |

## Отказ от ответственности

Этот проект предназначен **исключительно для образовательных и исследовательских целей**.

- Не предназначен для реальной торговли или инвестирования
- Не является инвестиционной рекомендацией
- Автор не несёт ответственности за финансовые потери
- Проконсультируйтесь с финансовым советником перед принятием инвестиционных решений
- Прошлые результаты не гарантируют будущих

## Установка

### 1. Клонируйте репозиторий

```bash
git clone https://github.com/KaigorodovTuskul/ai-hedge-fund-moex.git
cd ai-hedge-fund-moex
```

### 2. Создайте виртуальное окружение

```bash
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # Linux/Mac
```

### 3. Установите зависимости

```bash
pip install langchain>=0.3.7 langchain-anthropic==0.3.5 langchain-groq==0.2.3 \
  langchain-openai>=0.3.5 langchain-deepseek>=0.1.2 langchain-ollama==0.3.6 \
  langgraph==0.2.56 pandas numpy python-dotenv==1.0.0 matplotlib tabulate \
  colorama questionary rich langchain-google-genai>=2.0.11 \
  langchain-gigachat>=0.3.12 langchain-xai>=0.2.5 \
  "fastapi[standard]>=0.104.0" fastapi-cli pydantic httpx sqlalchemy alembic \
  beautifulsoup4 lxml streamlit
```

### 4. Настройте API-ключи

```bash
cp .env.example .env
```

Отредактируйте `.env` — добавьте ключи LLM-провайдеров (минимум один):

```env
# Для LLM (хотя бы один)
OPENAI_API_KEY=your-key
# ANTHROPIC_API_KEY=your-key
# GROQ_API_KEY=your-key
# DEEPSEEK_API_KEY=your-key

# Для поиска новостей (опционально, fallback)
# PERPLEXITY_API_KEY=your-key
```

**Важно**: Финансовые данные (цены, отчётность) берутся из бесплатных источников (MOEX ISS API, Smart-Lab) и не требуют API-ключей.

## Запуск

### CLI

```bash
venv\Scripts\activate
python -m src.main --tickers SBER,GAZP,YDEX --analysts-all
```

Дополнительные флаги:

```bash
# Указать период
python -m src.main --tickers SBER --start-date 2026-01-01 --end-date 2026-04-14 --analysts-all

# Использовать локальные LLM через Ollama
python -m src.main --tickers SBER --ollama --analysts-all

# Показать рассуждения агентов
python -m src.main --tickers SBER,GAZP --analysts-all --show-reasoning
```

### Streamlit GUI

```bash
venv\Scripts\activate
streamlit run app_streamlit.py
```

### Бэктестер

```bash
python -m src.backtester --tickers SBER,GAZP,LKOH
```

## Доступные тикеры

Любые акции на основной площадке MOEX (TQBR), ~260 тикеров. Примеры:

| Тикер | Компания | Сектор |
|-------|----------|--------|
| SBER | Сбербанк | Банки |
| GAZP | Газпром | Нефтегаз |
| YDEX | Яндекс | Технологии |
| LKOH | ЛУКОЙЛ | Нефтегаз |
| GMKN | Норникель | Добыча |
| NVTK | НОВАТЭК | Газ |
| ROSN | Роснефть | Нефть |
| PLZL | Полюс | Золото |
| MGNT | Магнит | Ритейл |
| OZON | Ozon | E-commerce |
| VKCO | VK Company | Технологии |
| MTSS | МТС | Телеком |

## Источники данных

| Данные | Источник | Стоимость |
|--------|----------|-----------|
| Цены (OHLCV) | MOEX ISS API | Бесплатно |
| Капитализация | MOEX ISS API | Бесплатно |
| Финансовая отчётность (МСФО) | Smart-Lab | Бесплатно |
| Финансовые метрики (P/E, ROE...) | Smart-Lab | Бесплатно |
| Новости компаний | Smart-Lab + Perplexity Sonar | Бесплатно / по ключу |
| Инсайдерские сделки | Недоступны (заглушка) | — |

## Как внести вклад

1. Форкните репозиторий
2. Создайте ветку фичи
3. Сделайте коммит
4. Отправьте Pull Request

## Лицензия

MIT License — см. файл LICENSE.
