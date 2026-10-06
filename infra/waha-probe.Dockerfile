FROM python:3.12.10-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY apps/backend/requirements.lock /app/requirements.lock
RUN python -m pip install --no-cache-dir -r requirements.lock
COPY apps/backend/src /app/apps/backend/src
COPY scripts/waha_local.py /app/scripts/waha_local.py
COPY scripts/waha_ingress.py /app/scripts/waha_ingress.py
COPY scripts/waha_container_config.py /app/scripts/waha_container_config.py
CMD ["python", "scripts/waha_local.py", "probe", "--container"]
