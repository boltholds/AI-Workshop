FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    AI_WORKSHOP_CHROMIUM_EXECUTABLE=/usr/bin/chromium \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium ffmpeg curl fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 --shell /bin/bash workshop
WORKDIR /opt/ai-workshop
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir '.[browser]' \
    && python -m playwright install ffmpeg \
    && chmod -R a+rX /ms-playwright
COPY browser/entrypoint.sh /usr/local/bin/ai-workshop-browser
RUN chmod +x /usr/local/bin/ai-workshop-browser

USER workshop
ENTRYPOINT ["/usr/local/bin/ai-workshop-browser"]
