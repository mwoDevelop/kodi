FROM python:3.12-alpine AS runtime

RUN addgroup -S broker && adduser -S -G broker -h /app broker
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
USER broker
ENTRYPOINT ["kodi-secret-broker"]
CMD ["serve"]
