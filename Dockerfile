# CaddieInsight v2 web app.
#
#   docker build -t caddieinsight .
#   docker run -p 8000:8000 -v caddie-data:/data caddieinsight
#
# Railway supplies PORT; the CMD honours it and falls back to 8000 locally.

FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY caddieinsight ./caddieinsight
RUN pip install --no-cache-dir ".[web]"

# The one SQLite file lives outside the image so a redeploy keeps every
# bag, shot and clubhouse post. Point CADDIE_DB somewhere on the volume.
ENV CADDIE_DB=/data/caddieinsight.db
VOLUME /data

EXPOSE 8000
CMD ["sh", "-c", "uvicorn --factory caddieinsight.web.app:create_app --host 0.0.0.0 --port ${PORT:-8000}"]
