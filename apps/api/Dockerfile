FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["uvicorn", "opportunity_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
