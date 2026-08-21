FROM python:3.12-slim-bookworm AS builder

RUN apt-get update \
    && apt-get install --yes --no-install-recommends gcc libc6-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY pyproject.toml ./
COPY src ./src
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.12-slim-bookworm AS runtime

RUN addgroup --system broker \
    && adduser --system --ingroup broker --home /app --disabled-password broker \
    && apt-get update \
    && apt-get install --yes --no-install-recommends libffi8 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels kodi-secret-broker==0.1.0 \
    && rm -rf /wheels
USER broker
ENTRYPOINT ["kodi-secret-broker"]
CMD ["serve"]
