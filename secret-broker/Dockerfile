FROM python:3.12-slim-bookworm AS runtime

RUN addgroup --system broker \
    && adduser --system --ingroup broker --home /app --disabled-password broker
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
USER broker
ENTRYPOINT ["kodi-secret-broker"]
CMD ["serve"]
