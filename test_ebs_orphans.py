from datetime import timedelta

import boto3
from moto import mock_aws

from ebs_orphans import monthly_cost, scan_region

REGION = "us-east-1"


def make_volume(ec2, tags=None):
    kwargs = {"AvailabilityZone": f"{REGION}a", "Size": 100}
    if tags:
        kwargs["TagSpecifications"] = [{
            "ResourceType": "volume",
            "Tags": [{"Key": k, "Value": v} for k, v in tags.items()],
        }]
    return ec2.create_volume(**kwargs)


def scan(ec2, now):
    return scan_region(ec2, "123456789012", REGION, 30, 0.08, now)


@mock_aws
def test_age_limit():
    ec2 = boto3.client("ec2", region_name=REGION)
    vol = make_volume(ec2)
    created = vol["CreateTime"]
    assert len(scan(ec2, created + timedelta(days=30))) == 1
    assert scan(ec2, created + timedelta(days=29)) == []


@mock_aws
def test_keep_tag_excluded():
    ec2 = boto3.client("ec2", region_name=REGION)
    vol = make_volume(ec2, {"keep": "true"})
    assert scan(ec2, vol["CreateTime"] + timedelta(days=60)) == []


@mock_aws
def test_in_use_excluded():
    ec2 = boto3.client("ec2", region_name=REGION)
    image = ec2.describe_images()["Images"][0]["ImageId"]
    instance = ec2.run_instances(ImageId=image, MinCount=1, MaxCount=1)["Instances"][0]
    vol = make_volume(ec2)
    ec2.attach_volume(VolumeId=vol["VolumeId"], InstanceId=instance["InstanceId"], Device="/dev/sdf")
    assert scan(ec2, vol["CreateTime"] + timedelta(days=60)) == []


def test_cost_math():
    assert f"{monthly_cost(100, 0.08):.2f}" == "8.00"
