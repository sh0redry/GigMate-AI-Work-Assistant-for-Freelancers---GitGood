FROM python:3.12.10-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PROJECT_ROOT=/workspace PYTHONPATH=/workspace/apps/backend/src:/workspace
WORKDIR /workspace
COPY apps/backend/requirements.lock apps/backend/requirements.lock
RUN pip install --no-cache-dir -r apps/backend/requirements.lock
COPY apps/backend apps/backend
COPY contracts contracts
COPY scripts scripts
RUN useradd --create-home appuser && mkdir -p /run/waha-media && chown appuser:appuser /run/waha-media && chmod 700 /run/waha-media
USER appuser
CMD ["uvicorn","gigmate.api:app","--host","0.0.0.0","--port","8000","--no-access-log","--log-level","error"]
