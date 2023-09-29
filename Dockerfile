FROM ghcr.io/deephaven/server:0.13.0
COPY app.d /app.d
RUN pip3 install -r /app.d/requirements.txt
