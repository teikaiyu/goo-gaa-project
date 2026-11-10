# Cloud Run image for avatar_api. Lives at the REPO ROOT on purpose: a Docker build can only
# copy files inside its build folder, and the designer's pictures are in the top-level images/.
# Deploy from the repo root:  gcloud run deploy avatar-api --source . ...
FROM python:3.12-slim

WORKDIR /app
# Destinations end with "/" on purpose: Cloud Build's older Docker builder rejects a wildcard
# source copied to "." ("destination must be a directory and end with a /"), while local
# BuildKit accepts it. The trailing slash works with both.
COPY avatar_api/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY avatar_api/*.py ./
COPY images/ images/
ENV IMAGES_DIR=/app/images
# The iPhone web app (Flutter). Built locally first: scripts/deploy_avatar_api.sh runs `flutter build web`.
COPY lumo_app/build/web/ web/
ENV WEB_DIR=/app/web
# The Chrome extension, handed out as /lumo_extension.zip (it is not on the Chrome Web Store).
COPY lumo_extension/ lumo_extension/
ENV EXTENSION_DIR=/app/lumo_extension

# Least privilege: the web server needs no root. If it were ever compromised, the
# attacker would not own the container.
RUN useradd --system --no-create-home appuser
USER appuser

# Cloud Run injects $PORT. Shell form so the variable is expanded.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
