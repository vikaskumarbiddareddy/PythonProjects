FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY static static
# Mount a persistent volume here so the plan, logs and Garmin tokens survive redeploys.
ENV MARATHON_DB=/data/marathon.db GARMIN_TOKENS=/data/garmin_tokens
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
