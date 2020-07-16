#!/usr/bin/env python

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import aurora_postgres_monitoring

def lambda_handler(event, context):
    # resolve the configuration from the sources required
    config_sources = [event, os.environ]
    aurora_postgres_monitoring.monitor_cluster(config_sources)
    return 'Finished'

if __name__ == "__main__":
    lambda_handler(sys.argv[0], None)
