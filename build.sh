#!/bin/bash

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

ver=1.0

if [ ! -d dist ]; then
	mkdir dist
fi

ARCHIVE=aurora-postgres-advanced-monitoring-$ver.zip

# add required dependencies
pip install pg8000 -t lib
pip install pgpasslib -t lib

# bin the old zipfile
if [ -f dist/$ARCHIVE ]; then
	echo "Removed existing Archive ../dist/$ARCHIVE"
	rm -Rf dist/$ARCHIVE
fi

cmd="zip -r dist/$ARCHIVE lambda_function.py aurora_postgres_monitoring.py monitoring-queries.json lib/"

if [ "$1" == "--include-user-queries" ]; then
	cmd="$cmd user-queries.json" 
fi

if [ $# -eq 1 ]; then
	cmd=`echo $cmd`
fi

echo $cmd

eval $cmd

echo "Generated new Lambda Archive dist/$ARCHIVE"
