#!/bin/sh
# Beim ersten Start: mitgelieferte Beispiel-Lektionen auf das Daten-Volume kopieren
mkdir -p /data/lessons
if [ -z "$(ls -A /data/lessons 2>/dev/null)" ]; then
    cp /app/app/lessons/*.json /data/lessons/ 2>/dev/null || true
fi
exec "$@"
