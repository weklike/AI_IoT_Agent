FROM charge-ops-backend:test-94f8cb9ab56df832
RUN rm -rf backend simulator knowledge tests/support
COPY backend backend
COPY simulator simulator
COPY knowledge knowledge
COPY tests/support tests/support
RUN uv sync --offline --locked --no-dev
