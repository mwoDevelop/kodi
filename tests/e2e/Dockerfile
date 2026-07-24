FROM python:3.12-slim

WORKDIR /workspace
COPY . .
RUN python -m pip install --no-cache-dir pytest
CMD ["bash", "tests/e2e/run.sh"]
