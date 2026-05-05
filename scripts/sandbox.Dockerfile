# Sandbox image for the Mercury executor.
# Pre-installs the libraries the agent will plausibly reach for, so it does
# NOT need network access at run time (the container is started with
# `network=none`).
#
# Build with:  docker build -t mercury-sandbox:latest -f scripts/sandbox.Dockerfile .
FROM python:3.11-slim

RUN pip install --no-cache-dir \
        pandas==2.2.3 \
        numpy==1.26.4 \
        python-dateutil==2.9.0.post0 \
        regex==2024.11.6 \
        lxml==5.3.0 \
        beautifulsoup4==4.12.3 \
        chardet==5.2.0

WORKDIR /workspace

# Default cmd is overridden by the sandbox start (`sleep infinity`).
CMD ["python"]
