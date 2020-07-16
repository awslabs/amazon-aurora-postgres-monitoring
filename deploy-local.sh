#!/usr/bin/env bash

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

ver=1.0

#for r in `aws ec2 describe-regions --query Regions[*].RegionName --output text`; do aws s3api create-bucket --bucket paramsey-cfn-$r --region $r --create-bucket-configuration LocationConstraint=$r; done

for r in `aws ec2 describe-regions --query Regions[*].RegionName --output text`; do aws s3 cp dist/aurora-postgres-advanced-monitoring-$ver.zip s3://paramsey-cfn-$r/AuroraPostgresAdvancedMonitoring/aurora-postgres-advanced-monitoring-$ver.zip --acl public-read --region $r; done

for r in `aws ec2 describe-regions --query Regions[*].RegionName --output text`; do aws s3 cp deploy-vpc.yaml s3://paramsey-cfn-$r/AuroraPostgresAdvancedMonitoring/deploy-vpc.yaml --acl public-read --region $r; done

for r in `aws ec2 describe-regions --query Regions[*].RegionName --output text`; do aws s3 cp deploy-non-vpc.yaml s3://paramsey-cfn-$r/AuroraPostgresAdvancedMonitoring/deploy-non-vpc.yaml --acl public-read --region $r; done

