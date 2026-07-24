FROM python:3.12-slim

WORKDIR /workspace
COPY . .
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --no-cache-dir pytest
RUN python tools/checkout_locked_components.py --output /locked-components
ENV KODI_COMPONENT_ROOT=/locked-components
CMD ["bash", "tests/e2e/run.sh"]
