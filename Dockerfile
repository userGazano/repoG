FROM python:3.11-slim

# Установка системных зависимостей для сборки psycopg2 и работы с сетевыми библиотеками
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копирование требований и установка Python-пакетов
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода проекта
COPY . .

# Создание директории для сессий Telethon
RUN mkdir -p /app/sessions

# Запуск бота
CMD ["python", "main.py"]
