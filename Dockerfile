FROM ghcr.io/deephaven/server:edge
COPY app.d /app.d
RUN pip3 install -r /app.d/requirements.txt
