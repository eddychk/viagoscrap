FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir -e .
RUN python -m playwright install chromium

ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/data/viagoscrap.db
ENV HEADLESS=true

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "viagoscrap.webapp:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
