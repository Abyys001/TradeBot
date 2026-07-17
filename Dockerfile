FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=300

RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app

WORKDIR /app

RUN printf 'Acquire::Retries "10";\nAcquire::http::Timeout "180";\nAcquire::https::Timeout "180";\n' > /etc/apt/apt.conf.d/99retries \
    && apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && (pip install --retries 10 --timeout 300 -r requirements.txt \
        || (echo "pip install retry 1/2" && rm -rf /root/.cache/pip && sleep 10 \
            && pip install --retries 10 --timeout 300 -r requirements.txt) \
        || (echo "pip install retry 2/2" && rm -rf /root/.cache/pip && sleep 10 \
            && pip install --retries 10 --timeout 300 -r requirements.txt))

RUN chown -R app:app /app

COPY entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh \
    && chmod +x /entrypoint.sh

USER app

COPY --chown=app:app . .

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
