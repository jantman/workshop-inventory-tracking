# syntax=docker/dockerfile:1

# Build stage: compile dependencies into a virtualenv.
#
# git is needed because pt-p710bt-label-maker (and its pybluez dependency)
# install straight from GitHub. build-essential and libbluetooth-dev are needed
# because pybluez is a C extension that has no wheels.
FROM python:3.13-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        git \
        libbluetooth-dev \
    && rm -rf /var/lib/apt/lists/*

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt


# Runtime stage.
#
# cups-client provides the `lp` binary used for label printing; set CUPS_SERVER
# to point it at a CUPS server on the network. libbluetooth3 is the shared
# library the pybluez extension built above links against.
#
# fonts-dejavu-core provides DejaVuSans.ttf. Label composition asks Pillow for it
# by bare filename, which resolves against the system font path, and the slim
# base image ships no fonts at all -- so without this every label print fails at
# render time with "cannot open resource". It is needed by both the product
# labels and the pre-existing JA-ID ones, since the barcode generator defaults to
# the same font.
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        cups-client \
        fonts-dejavu-core \
        libbluetooth3 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 inventory

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY alembic.ini config.py manage.py pyproject.toml wsgi.py ./
COPY app/ ./app/
COPY migrations/ ./migrations/

# The commit this image was built from, shown in the footer and reported by
# /health as `0.1.1-6d15bde`. The image carries no history to derive it from --
# .dockerignore excludes .git/ and this stage installs no git -- so the build has
# to tell it.
#
# The `docker-build` job in test.yml passes this; the `release` job deliberately
# does not, which is what makes a release image report a bare `0.1.1`.
#
# It goes here, below every COPY, because its value changes with every commit and
# would otherwise invalidate the layers above it on every build.
ARG BUILD_SHA=""
ENV APP_BUILD_SHA=$BUILD_SHA

USER inventory

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health').read()"

# No ENTRYPOINT, so `docker run <image> python manage.py db upgrade` works for
# migrations and the other manage.py commands.
#
# --timeout 600: confirming an Amazon order stores every line's listing images
# before it responds, at 8-15 seconds per gallery, so a five-line order is well
# past gunicorn's 30-second default and the worker was killed mid-request. The
# purchases were already written; the pictures and the page were not
# (044 research.md §8). A reverse proxy in front needs a read timeout as long.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "600", "--access-logfile", "-", "wsgi:app"]
