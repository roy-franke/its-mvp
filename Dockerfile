FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

# Daten (SQLite-DB und Lektionen) liegen auf einem Volume und überleben Updates
ENV ITS_DB_PATH=/data/its.db \
    ITS_LESSONS_DIR=/data/lessons

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
