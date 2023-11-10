from __future__ import print_function

import os
import sys

# Copyright 2020-2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance with the License. A copy of the License is located at
# http://aws.amazon.com/apache2.0/
# or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.

# add the lib directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), "lib"))
sys.path.append(os.path.join(os.path.dirname(__file__), "sql"))

import boto3
import base64

import pg8000.dbapi as pg8000
import datetime
import json
import pgpasslib
from botocore.client import Config
import ssl as sslv

#### Static Configuration
ssl = True
interval = "1 hour"
##################

__version__ = "1.0"
debug = False
pg8000.paramstyle = "qmark"


def run_external_commands(command_set_type, file_name, cursor, cluster):
    if not os.path.exists(file_name):
        return []

    external_commands = None
    try:
        external_commands = json.load(open(file_name, "r"))
    except ValueError as e:
        # handle a malformed user query set gracefully
        if e.message == "No JSON object could be decoded":
            return []
        else:
            raise

    output_metrics = []

    for command in external_commands:
        if command["type"] == "value":
            cmd_type = "Query"
        else:
            cmd_type = "Canary"

        print("Executing %s %s: %s" % (command_set_type, cmd_type, command["name"]))

        try:
            t = datetime.datetime.now()
            interval = run_command(cursor, command["query"])
            value = cursor.fetchone()[0]

            if value is None:
                value = 0

            # append a cloudwatch metric for the value, or the elapsed interval, based upon the configured 'type' value
            if command["type"] == "value":
                output_metrics.append(
                    {
                        "MetricName": command["name"],
                        "Dimensions": [{"Name": "ClusterIdentifier", "Value": cluster}],
                        "Timestamp": t,
                        "Value": value,
                        "Unit": command["unit"],
                    }
                )
            else:
                output_metrics.append(
                    {
                        "MetricName": command["name"],
                        "Dimensions": [{"Name": "ClusterIdentifier", "Value": cluster}],
                        "Timestamp": t,
                        "Value": interval,
                        "Unit": "Milliseconds",
                    }
                )
        except Exception as e:
            print("Exception running external command %s" % command["name"])
            print(e)

    return output_metrics


def run_command(cursor, statement):
    if debug:
        print("Running Statement: %s" % statement)

    t = datetime.datetime.now()
    cursor.execute(statement)
    interval = (datetime.datetime.now() - t).microseconds / 1000

    return interval


# nasty hack for backward compatibility, to extract label values from os.environ or event
def get_config_value(labels, configs):
    for l in labels:
        for c in configs:
            if l in c:
                if debug:
                    print("Resolved label value %s from config" % l)

                return c[l]

    return None


def monitor_cluster(config_sources):
    aws_region = get_config_value(["AWS_REGION"], config_sources)

    set_debug = get_config_value(["DEBUG", "debug", "Debug"], config_sources)
    if set_debug is not None and (
        (isinstance(set_debug, bool) and set_debug) or set_debug.upper() == "TRUE"
    ):
        global debug
        debug = True

    boto_retries = 4
    boto_timeout = 60

    if debug:
        boto_retries = 0
        boto_timeout = 5

    config = Config(
        region_name=aws_region,
        connect_timeout=boto_timeout,
        retries={"max_attempts": boto_retries},
    )

    kms = boto3.client("kms", config=config)
    cw = boto3.client("cloudwatch", config=config)

    if debug:
        print("Connected to AWS KMS & CloudWatch in %s" % aws_region)

    user = get_config_value(
        ["DbUser", "db_user", "dbUser", "DatabaseUser"], config_sources
    )
    host = get_config_value(
        ["HostName", "cluster_endpoint", "dbHost", "db_host", "ClusterEndpoint"],
        config_sources,
    )
    port = int(
        get_config_value(
            ["HostPort", "db_port", "dbPort", "ClusterPort"], config_sources
        )
    )
    database = get_config_value(["DatabaseName", "db_name", "db"], config_sources)
    cluster = get_config_value(
        ["ClusterName", "cluster_name", "clusterName"], config_sources
    )
    global interval
    interval = get_config_value(
        [
            "AggregationInterval",
            "agg_interval",
            "aggregtionInterval",
            "ScheduleFrequency",
        ],
        config_sources,
    )

    pwd = None
    try:
        pwd = pgpasslib.getpass(host, port, database, user)
    except pgpasslib.FileNotFound as e:
        pass

    # check if unencrypted password exists if no pgpasslib
    if pwd is None:
        pwd = get_config_value(["db_pwd"], config_sources)

    # check for encrypted password if the above two don't exist
    if pwd is None:
        enc_password = get_config_value(
            ["EncryptedPassword", "encrypted_password", "encrypted_pwd", "dbPassword"],
            config_sources,
        )
        # resolve the authorisation context, if there is one, and decrypt the password
        auth_context = get_config_value("kms_auth_context", config_sources)

        if auth_context is not None:
            auth_context = json.loads(auth_context)

        try:
            if auth_context is None:
                pwd = kms.decrypt(CiphertextBlob=base64.b64decode(enc_password))[
                    "Plaintext"
                ]
            else:
                pwd = kms.decrypt(
                    CiphertextBlob=base64.b64decode(enc_password),
                    EncryptionContext=auth_context,
                )["Plaintext"]

        except:
            print("KMS access failed: exception %s" % sys.exc_info()[1])
            print("Encrypted Password: %s" % enc_password)
            print("Encryption Context %s" % auth_context)
            raise

    # Create a new cursor for methods to run through
    cursor = None
    # Connect to the cluster
    try:
        if debug:
            print("Connecting to Aurora Postgres: %s" % host)
        conn = None
        conn = pg8000.Connection(
            database=database,
            user=user,
            password=pwd,
            host=host,
            port=port,
            ssl_context=None,
        )
        cursor = conn.cursor()
    except Exception as e:
        print("Aurora Postgres Connection Failed: exception %s" % sys.exc_info()[1])

    if debug:
        print("Successfully Connected to Aurora Postgres")

    # set application name
    set_name = (
        "set application_name to 'AuroraPostgresAdvancedMonitoring-v%s'" % __version__
    )
    cursor.execute(set_name)

    # run the externally configured commands and save their values in the put metrics
    put_metrics = run_external_commands(
        "Aurora Postgres Diagnostic", "monitoring-queries.json", cursor, cluster
    )

    # run the supplied user commands and append their values onto the put metrics
    put_metrics.extend(
        run_external_commands("User Configured", "user-queries.json", cursor, cluster)
    )

    # add a metric for how many metrics we're exporting (whoa inception)
    put_metrics.extend(
        [
            {
                "MetricName": "CloudwatchMetricsExported",
                "Dimensions": [{"Name": "ClusterIdentifier", "Value": cluster}],
                "Timestamp": datetime.datetime.utcnow(),
                "Value": len(put_metrics),
                "Unit": "Count",
            }
        ]
    )

    max_metrics = 20
    group = 0
    print("Publishing %s CloudWatch Metrics" % (len(put_metrics)))

    for x in range(0, len(put_metrics), max_metrics):
        group += 1

        # slice the metrics into blocks of 20 or just the remaining metrics
        put = put_metrics[x : (x + max_metrics)]

        if debug:
            print("Metrics group %s: %s Datapoints" % (group, len(put)))
            print(put)
        try:
            cw.put_metric_data(Namespace="AuroraPostgres", MetricData=put)
        except:
            print(
                "Pushing metrics to CloudWatch failed: exception %s" % sys.exc_info()[1]
            )
            raise

    cursor.close()
    conn.close()
