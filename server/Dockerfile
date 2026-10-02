FROM docker@sha256:1f029db43a32fbb1465fe8ff4327d405154876946986170e97d7861232a8227a AS docker-cli

FROM python:3.12-slim

COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /opt/ai-workshop
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

ENTRYPOINT ["ai-workshop"]
CMD ["server", "serve", "--config", "/config/server.yaml", "--state-root", "/state", "--host", "0.0.0.0", "--port", "8770"]
