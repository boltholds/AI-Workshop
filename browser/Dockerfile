FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

WORKDIR /opt/ai-workshop
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
RUN mkdir -p /data/browser-profile /data/artifacts \
    && chown -R pwuser:pwuser /data /opt/ai-workshop

USER pwuser
ENTRYPOINT ["ai-workshop"]
CMD ["browser", "--profile", "/data/browser-profile", "--artifacts", "/data/artifacts", "--host", "0.0.0.0", "--port", "8767"]
