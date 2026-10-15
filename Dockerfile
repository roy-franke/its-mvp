FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY VERSION CHANGELOG.md ./
COPY app ./app
COPY static ./static
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

# T-31: Ohne .git im Container kommt der Commit-Hash als Build-Argument:
#   docker compose build --build-arg ITS_GIT_COMMIT=$(git rev-parse --short HEAD)
ARG ITS_GIT_COMMIT=
ENV ITS_GIT_COMMIT=${ITS_GIT_COMMIT}

# Daten (SQLite-DB, Lektionen und Lernmaterialien) liegen auf einem Volume und überleben Updates
ENV ITS_DB_PATH=/data/its.db \
    ITS_LESSONS_DIR=/data/lessons \
    ITS_MATERIAL_DIR=/data/materialien

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
