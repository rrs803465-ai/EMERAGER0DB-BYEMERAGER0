# Railway service: website, release API and installer endpoints.
# The web service never imports the database engine and never stores user data.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY web ./web
COPY installer ./installer

# Railway injects PORT at runtime. The app reads it itself.
EXPOSE 8080

RUN useradd --create-home --uid 10001 appuser
USER appuser

CMD ["python", "-m", "web.api.app"]
