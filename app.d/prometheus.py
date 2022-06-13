"""
prometheus.py

A simple Python script that pulls data from Prometheus's API, and
stores it in a Deephaven table.

This is expected to be run within Deephaven's application mode https://deephaven.io/core/docs/how-to-guides/app-mode/.

After launching, there will be two tables within the "Panels" section of the Deephaven UI.
One will be a static table and the other will be continually updating with real data.

@author Jake Mulford
@copyright Deephaven Data Labs LLC
"""
from deephaven import new_table
from deephaven.column import string_col, datetime_col, double_col
from deephaven.time import millis_to_datetime
from deephaven import DynamicTableWriter
import deephaven.dtypes as dht
from deephaven.experimental.ema import ByEmaSimple
from deephaven.plot.figure import Figure

import requests

import threading
import time

PROMETHEUS_QUERIES = ["go_memstats_alloc_bytes", "go_memstats_heap_idle_bytes", "go_memstats_frees_total"] #Edit this and add your queries here
BASE_URL = "{base}/api/v1/query".format(base="http://prometheus:9090") #Edit this to your base URL if you're not using a local Prometheus instance

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
                #milliseconds, then cast to an int() to use the millis_to_datetime() method
                timestamp = millis_to_datetime(int(result["value"][0] * 1000))
                job = result["metric"]["job"]
                instance = result["metric"]["instance"]
                value = float(result["value"][1])
                results.append((timestamp, job, instance, value))
    return results

dynamic_table_writer_columns = {
    "DateTime": dht.DateTime,
    "PrometheusQuery": dht.string,
    "Job": dht.string,
    "Instance": dht.string,
    "Value": dht.double,
}

table_writer = DynamicTableWriter(dynamic_table_writer_columns)

result_dynamic = table_writer.table

def thread_func():
    while True:
        for prometheus_query in PROMETHEUS_QUERIES:
            values = make_prometheus_request(prometheus_query, BASE_URL)

            for (date_time, job, instance, value) in values:
                table_writer.write_row(date_time, prometheus_query, job, instance, value)
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

result_static = new_table([
    datetime_col("DateTime", date_time_list),
    string_col("PrometheusQuery", prometheus_query_list),
    string_col("Job", job_list),
    string_col("Instance", instance_list),
    double_col("Value", value_list)
])

#Perform the desired queries, and set the results as new fields
result_static_update = result_static.group_by(by="PrometheusQuery")

result_static_average = result_static.drop_columns(["DateTime", "Job", "Instance"]).avg_by(by="PrometheusQuery")

result_dynamic_update = result_dynamic.group_by(by="PrometheusQuery")

result_dynamic_average = result_dynamic.drop_columns(["DateTime", "Job", "Instance"]).avg_by(by="PrometheusQuery")

#Downsampling examples
result_dynamic_downsampled_average = result_dynamic.update(["DateTimeMinute = lowerBin(DateTime, '00:01:00')"])\
    .drop_columns(["DateTime"])\
    .avg_by(by=["PrometheusQuery", "DateTimeMinute", "Job", "Instance"])

result_dynamic_downsampled_tail = result_dynamic.tail(20)

result_dynamic_ema = result_dynamic.view(["PrometheusQuery", "EMA = prometheus_metrics_ema.update(DateTime, Value, PrometheusQuery, Job, Instance)"])\
    .last_by(by=["PrometheusQuery"])\
    .tail(10)

#Plotting examples

line_plot = Figure().plot_xy(series_name="Average By Minute", t=result_dynamic_downsampled_average.where(filters=["PrometheusQuery = `go_memstats_alloc_bytes`"]), x="DateTimeMinute", y="Value").chart_title(title="go_memstats_alloc_bytes Average Per Minute").show()
cat_plot = Figure().plot_cat(series_name="Average By Minute", t=result_dynamic_downsampled_average.where(filters=["PrometheusQuery = `go_memstats_alloc_bytes`"]), category="DateTimeMinute", y="Value").chart_title(title="go_memstats_alloc_bytes Average Per Minute").show()
hist_plot = Figure().plot_xy_hist(series_name="Count Of Values", t=result_dynamic.where(filters=["PrometheusQuery = `go_memstats_alloc_bytes`"]), x="Value", nbins=20).chart_title(title="go_memstats_alloc_bytes Distribution").show()
