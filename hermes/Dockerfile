# hermes-agent service: the pinned Hermes image plus the runner.
# Build the base first: make hermes-build (docker build -t hermes-base:v0.22.1 https://github.com/NousResearch/hermes-agent.git#v0.22.1)
FROM hermes-base:v0.22.1

USER root
COPY runner/ /opt/runner/
RUN /opt/hermes/.venv/bin/python -c "import fastapi, uvicorn, psutil" \
 && mkdir -p /opt/data/runs /opt/data/registry && chown -R hermes:hermes /opt/data /opt/runner
USER hermes
ENV RUNNER_PORT=8700 \
    HERMES_HOME=/opt/data \
    PYTHONUNBUFFERED=1
EXPOSE 8700
ENTRYPOINT []
CMD ["/opt/hermes/.venv/bin/python", "/opt/runner/serve.py"]
