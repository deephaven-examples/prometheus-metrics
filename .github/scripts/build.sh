#!/usr/bin/env bash

set -o errexit
set -o pipefail
set -o nounset

docker build --tag deephaven-examples/prometheus-metrics-grpc-api .
