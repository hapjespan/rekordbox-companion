FROM node:24-trixie

# python3 is explicit rather than inherited from the base image: the workflow
# scripts in .workflow/ depend on it and must not break on a base image bump.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git gh curl ca-certificates python3 \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://claude.ai/install.sh | bash

ENV PATH="/root/.local/bin:$PATH"

# uv and the Spec Kit CLI, baked into the image so the toolchain version travels
# with the project instead of with the host. Spec Kit is pinned, because an
# unpinned install makes every rebuild a silent upgrade of the tool the whole
# workflow graph runs on. Upgrading is a deliberate bump here plus a rebuild.
# Claude Code is deliberately not pinned: it updates itself either way.
ARG SPECIFY_VERSION=0.16.4
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && uv tool install "specify-cli==${SPECIFY_VERSION}"
