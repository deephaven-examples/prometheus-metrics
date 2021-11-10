"""
prometheus.py

A simple python script that pulls data from Prometheus's API, and
stores it in a Deephaven table.

This is expected to be run within Deephaven's application mode https://deephaven.io/core/docs/how-to-guides/app-mode/.

After launching, there will be 2 tables within the "Panels" section of the Deephaven UI.
One will be a static table and the other will be continually updating with real data.

@author Jake Mulford
@copyright Deephaven Data Labs LLC
"""
from deephaven.TableTools import newTable, stringCol, dateTimeCol, doubleCol
from deephaven import DynamicTableWriter
from deephaven.DBTimeUtils import millisToTime
import deephaven.Types as dht
from typing import Callable
from deephaven.MovingAverages import ByEmaSimple
from deephaven import Plot

import requests

import threading
import time

PROMETHEUS_QUERIES = ["go_memstats_alloc_bytes", "go_memstats_heap_idle_bytes", "go_memstats_frees_total"] #Edit this and add your queries here
BASE_URL = "{base}/api/v1/query".format(base="http://prometheus:9090") #Edit this to your base URL if you're not using a local Prometheus instance

ApplicationState = jpy.get_type("io.deephaven.appmode.ApplicationState")

prometheus_metrics_ema = ByEmaSimple(nullBehavior='BD_SKIP', nanBehavior='BD_SKIP', mode='TIME', type='LEVEL', timeScale=10, timeUnit="SECONDS")

def make_prometheus_request(prometheus_query, query_url):
    """
    A helper method that makes a request on the Prometheus API with the given
    query, and returns a list of results containing the timestamp, job, instance, and value for the query.
    The data returned by this method will be stored in a Deephaven table.

    This assumes that the query is going to return a "vector" type from the Prometheus API.
    https://prometheus.io/docs/prometheus/latest/querying/api/#instant-vectors

    Args:
        prometheus_query (str): The Prometheus query to execute with the API request.
        query_url (str): The URL of the query endpoint.
    Returns:
        list[(date-time, str, str, float)]: List of the timestamps, jobs, instances, and values from the API response.
    """
    results = []
    query_parameters = {
        "query": prometheus_query
    }
    response = requests.get(query_url, params=query_parameters)
    response_json = response.json()

    if "data" in response_json.keys():
        if "resultType" in response_json["data"] and response_json["data"]["resultType"] == "vector":
            for result in response_json["data"]["result"]:
                #Prometheus timestamps are in seconds. We multiply by 1000 to convert it to
                #milliseconds, then cast to an int() to use the millisToTime() method
                timestamp = millisToTime(int(result["value"][0] * 1000))
                job = result["metric"]["job"]
                instance = result["metric"]["instance"]
                value = float(result["value"][1])
                results.append((timestamp, job, instance, value))
    return results

column_names = ["DateTime", "PrometheusQuery", "Job", "Instance", "Value"]
column_types = [dht.datetime, dht.string, dht.string, dht.string, dht.double]

table_writer = DynamicTableWriter(
    column_names,
    column_types
)

result_dynamic = table_writer.getTable() 

def thread_func():
    while True:
        for prometheus_query in PROMETHEUS_QUERIES:
            values = make_prometheus_request(prometheus_query, BASE_URL)

            for (date_time, job, instance, value) in values:
                table_writer.logRow(date_time, prometheus_query, job, instance, value)
        time.sleep(2)

thread = threading.Thread(target = thread_func)
thread.start()

date_time_list = []
prometheus_query_list = []
job_list = []
instance_list = []
value_list = []
query_count = 2

for i in range(query_count):
    for prometheus_query in PROMETHEUS_QUERIES:
        values = make_prometheus_request(prometheus_query, BASE_URL)

        for (date_time, job, instance, value) in values:
            date_time_list.append(date_time)
            prometheus_query_list.append(prometheus_query)
            job_list.append(job)
            instance_list.append(instance)
            value_list.append(value)
    time.sleep(2)

result_static = newTable(
    dateTimeCol("DateTime", date_time_list),
    stringCol("PrometheusQuery", prometheus_query_list),
    stringCol("Job", job_list),
    stringCol("Instance", instance_list),
    doubleCol("Value", value_list)
) 

#Perform the desired queries, and set the results as new fields
result_static_update = result_static.by("PrometheusQuery")

result_static_average = result_static.dropColumns("DateTime", "Job", "Instance").avgBy("PrometheusQuery")

result_dynamic_update = result_dynamic.by("PrometheusQuery")

result_dynamic_average = result_dynamic.dropColumns("DateTime", "Job", "Instance").avgBy("PrometheusQuery")

#Downsampling examples
result_dynamic_downsampled_average = result_dynamic.update("DateTimeMinute = lowerBin(DateTime, '00:01:00')")\
    .dropColumns("DateTime")\
    .avgBy("PrometheusQuery", "DateTimeMinute", "Job", "Instance")

result_dynamic_downsampled_tail = result_dynamic.tail(20)

result_dynamic_ema = result_dynamic.view("PrometheusQuery", "EMA = prometheus_metrics_ema.update(DateTime, Value, PrometheusQuery, Job, Instance)")\
    .lastBy("PrometheusQuery")\
    .tail(10)

#Plotting examples

line_plot = Plot.plot("Average By Minute", result_dynamic_downsampled_average.where("PrometheusQuery = `go_memstats_alloc_bytes`"), "DateTimeMinute", "Value").show()
cat_plot = Plot.catPlot("Average By Minute", result_dynamic_downsampled_average.where("PrometheusQuery = `go_memstats_alloc_bytes`"), "DateTimeMinute", "Value").show()
hist_plot = Plot.histPlot("Count Of Values", result_dynamic.where("PrometheusQuery = `go_memstats_alloc_bytes`"), "Value", 20).show()
