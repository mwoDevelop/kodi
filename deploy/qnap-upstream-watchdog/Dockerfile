FROM python:3.12.11-alpine3.22@sha256:efcdfa6a6b2fd2afb9c7dfa9a5b288a6f68338b5cfdebe6b637d986067d85757

RUN addgroup -S -g 10001 watchdog \
    && adduser -S -D -H -u 10001 -G watchdog watchdog

WORKDIR /app
COPY tools/upstream_watchdog.py tools/upstream_watchdog.py
COPY manifests/upstream-watchdog.json manifests/upstream-watchdog.json

USER 10001:10001
ENTRYPOINT ["python", "tools/upstream_watchdog.py"]
CMD ["watch", "--status", "/run/watchdog/status.json"]
