#!/usr/bin/env bash
# setup_model_monitor.sh — set up CloudWatch-based monitoring for the
# paintshop-anomaly-endpoint (multi-container Direct mode — DataCapture unsupported).
#
# Creates:
#   1. CloudWatch alarms on SageMaker built-in endpoint metrics
#   2. Custom PaintShop/ModelQuality metrics published from DynamoDB anomaly scores
#   3. CloudWatch dashboard: PaintShopModelMonitor
#
# Safe to re-run — updates existing alarms/dashboards.
set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
ENDPOINT="paintshop-anomaly-endpoint"
SNS_ARN="arn:aws:sns:${REGION}:${ACCOUNT}:paintshop-alerts"

echo "==> Setting up CloudWatch alarms for endpoint: $ENDPOINT ..."
python3 - <<PYEOF
import boto3

cw  = boto3.client("cloudwatch", region_name="${REGION}")
sns = "${SNS_ARN}"
ep  = "${ENDPOINT}"

alarms = [
    {
        "AlarmName":          f"paintshop-endpoint-errors",
        "AlarmDescription":   "SageMaker endpoint model invocation errors",
        "MetricName":         "InvocationModelErrors",
        "Namespace":          "AWS/SageMaker",
        "Dimensions":         [{"Name": "EndpointName", "Value": ep},
                               {"Name": "VariantName",  "Value": "AllTraffic"}],
        "Period":             300,
        "EvaluationPeriods":  1,
        "Threshold":          5.0,
        "ComparisonOperator": "GreaterThanOrEqualToThreshold",
        "Statistic":          "Sum",
        "TreatMissingData":   "notBreaching",
        "AlarmActions":       [sns],
    },
    {
        "AlarmName":          f"paintshop-endpoint-latency",
        "AlarmDescription":   "SageMaker model latency p99 > 2s — potential model degradation",
        "MetricName":         "ModelLatency",
        "Namespace":          "AWS/SageMaker",
        "Dimensions":         [{"Name": "EndpointName", "Value": ep},
                               {"Name": "VariantName",  "Value": "AllTraffic"}],
        "Period":             300,
        "EvaluationPeriods":  3,
        "Threshold":          2000000.0,   # microseconds → 2 seconds
        "ComparisonOperator": "GreaterThanOrEqualToThreshold",
        "ExtendedStatistic":  "p99",
        "TreatMissingData":   "notBreaching",
        "AlarmActions":       [sns],
    },
    {
        "AlarmName":          f"paintshop-endpoint-silent",
        "AlarmDescription":   "No invocations for 15 minutes — possible upstream failure",
        "MetricName":         "Invocations",
        "Namespace":          "AWS/SageMaker",
        "Dimensions":         [{"Name": "EndpointName", "Value": ep},
                               {"Name": "VariantName",  "Value": "AllTraffic"}],
        "Period":             900,
        "EvaluationPeriods":  1,
        "Threshold":          1.0,
        "ComparisonOperator": "LessThanThreshold",
        "Statistic":          "Sum",
        "TreatMissingData":   "breaching",
        "AlarmActions":       [sns],
    },
    {
        "AlarmName":          f"paintshop-anomaly-rate-high",
        "AlarmDescription":   "High anomaly rate in PaintShop/ModelQuality — possible drift",
        "MetricName":         "AnomalyRate",
        "Namespace":          "PaintShop/ModelQuality",
        "Dimensions":         [],
        "Period":             900,
        "EvaluationPeriods":  2,
        "Threshold":          0.4,          # >40% tanks anomalous
        "ComparisonOperator": "GreaterThanOrEqualToThreshold",
        "Statistic":          "Average",
        "TreatMissingData":   "notBreaching",
        "AlarmActions":       [sns],
    },
]

for alarm in alarms:
    # Split keys that don't belong in put_metric_alarm
    kwargs = {k: v for k, v in alarm.items() if v != []}
    cw.put_metric_alarm(**kwargs)
    print(f"  Alarm set: {alarm['AlarmName']}")

print("  Done.")
PYEOF

echo "==> Publishing initial custom metrics from DynamoDB tank-status ..."
python3 - <<PYEOF
import boto3
from decimal import Decimal

cw  = boto3.client("cloudwatch",  region_name="${REGION}")
ddb = boto3.resource("dynamodb",  region_name="${REGION}")

table = ddb.Table("tank-status")
resp  = table.scan(ProjectionExpression="tank_id,if_score,lstm_score,#s",
                   ExpressionAttributeNames={"#s": "status"})
items = resp.get("Items", [])

if not items:
    print("  No tank-status records yet — metrics will populate once stream is live.")
else:
    if_scores   = [float(i["if_score"])   for i in items if "if_score"   in i]
    lstm_scores = [float(i["lstm_score"]) for i in items if "lstm_score" in i]
    anomalous   = sum(1 for i in items if i.get("status") == "degraded")
    n           = len(items)

    data = []
    if if_scores:
        data.append({"MetricName": "MeanIFScore",    "Value": sum(if_scores)/len(if_scores),
                     "Unit": "None",  "Dimensions": []})
    if lstm_scores:
        data.append({"MetricName": "MeanLSTMScore",  "Value": sum(lstm_scores)/len(lstm_scores),
                     "Unit": "None",  "Dimensions": []})
    if n > 0:
        data.append({"MetricName": "AnomalyRate",    "Value": anomalous / n,
                     "Unit": "None",  "Dimensions": []})

    cw.put_metric_data(Namespace="PaintShop/ModelQuality", MetricData=data)
    print(f"  Published: tanks={n}  anomaly_rate={anomalous/n:.2f}  "
          f"mean_if={sum(if_scores)/len(if_scores):.3f}  mean_lstm={sum(lstm_scores)/len(lstm_scores):.3f}")
PYEOF

echo "==> Creating CloudWatch dashboard: PaintShopModelMonitor ..."
python3 - <<PYEOF
import boto3, json

cw = boto3.client("cloudwatch", region_name="${REGION}")
ep = "${ENDPOINT}"

dashboard = {
    "widgets": [
        {
            "type": "metric", "x": 0, "y": 0, "width": 12, "height": 6,
            "properties": {
                "title": "Endpoint Invocations & Errors",
                "metrics": [
                    ["AWS/SageMaker", "Invocations",           "EndpointName", ep, "VariantName", "AllTraffic"],
                    [".",             "InvocationModelErrors", ".",             ep, ".",           "AllTraffic"],
                ],
                "view": "timeSeries", "period": 300, "stat": "Sum", "region": "${REGION}",
            }
        },
        {
            "type": "metric", "x": 12, "y": 0, "width": 12, "height": 6,
            "properties": {
                "title": "Model Latency (p99)",
                "metrics": [
                    ["AWS/SageMaker", "ModelLatency", "EndpointName", ep, "VariantName", "AllTraffic",
                     {"stat": "p99"}],
                ],
                "view": "timeSeries", "period": 300, "region": "${REGION}",
            }
        },
        {
            "type": "metric", "x": 0, "y": 6, "width": 12, "height": 6,
            "properties": {
                "title": "Anomaly Scores (Custom)",
                "metrics": [
                    ["PaintShop/ModelQuality", "MeanIFScore"],
                    [".",                      "MeanLSTMScore"],
                ],
                "view": "timeSeries", "period": 900, "stat": "Average", "region": "${REGION}",
            }
        },
        {
            "type": "metric", "x": 12, "y": 6, "width": 12, "height": 6,
            "properties": {
                "title": "Tank Anomaly Rate",
                "metrics": [["PaintShop/ModelQuality", "AnomalyRate"]],
                "view": "timeSeries", "period": 900, "stat": "Average", "region": "${REGION}",
                "yAxis": {"left": {"min": 0, "max": 1}},
            }
        },
    ]
}

cw.put_dashboard(DashboardName="PaintShopModelMonitor", DashboardBody=json.dumps(dashboard))
print("  Dashboard 'PaintShopModelMonitor' created/updated.")
PYEOF

echo ""
echo "==> Model Monitor setup complete."
echo "    Alarms:    paintshop-endpoint-errors / -latency / -silent / -anomaly-rate-high"
echo "    Metrics:   PaintShop/ModelQuality namespace (populated by stream processor)"
echo "    Dashboard: https://console.aws.amazon.com/cloudwatch/home?region=${REGION}#dashboards:name=PaintShopModelMonitor"
echo ""
echo "NOTE: DataCapture is not supported for Direct InferenceExecutionMode (multi-container MCE)."
echo "      Custom anomaly metrics are derived from DynamoDB tank-status (if_score, lstm_score)."
