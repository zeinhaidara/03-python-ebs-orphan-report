"""List unattached EBS volumes across an AWS Organization and write them to a CSV."""
import argparse
import csv
from datetime import UTC, datetime, timedelta

import boto3
from botocore.exceptions import BotoCoreError, ClientError

# Check current AWS pricing for your region. 0.08 is a rough gp3 figure.
DEFAULT_PRICE = 0.08

FIELDS = [
    "account", "region", "volume_id", "size_gb", "volume_type",
    "created", "age_days", "estimated_monthly_cost", "delete_candidate",
]


def monthly_cost(size_gb, price_per_gb_month):
    return round(size_gb * price_per_gb_month, 2)


def scan_region(ec2, account, region, min_age_days, price, now):
    """Return CSV rows for old, untagged, available volumes in one region."""
    rows = []
    pages = ec2.get_paginator("describe_volumes").paginate(
        Filters=[{"Name": "status", "Values": ["available"]}]
    )
    for page in pages:
        for vol in page["Volumes"]:
            age = now - vol["CreateTime"]
            tags = {t["Key"]: t["Value"] for t in vol.get("Tags", [])}
            if age < timedelta(days=min_age_days):
                continue
            if tags.get("keep", "").lower() == "true":
                continue
            rows.append({
                "account": account,
                "region": region,
                "volume_id": vol["VolumeId"],
                "size_gb": vol["Size"],
                "volume_type": vol["VolumeType"],
                "created": vol["CreateTime"].isoformat(),
                "age_days": age.days,
                "estimated_monthly_cost": f"{monthly_cost(vol['Size'], price):.2f}",
                "delete_candidate": "yes",
            })
    return rows


def scan_account(account_id, role_name, min_age_days, price, now):
    """Assume the role in one account and scan every enabled region."""
    arn = f"arn:aws:iam::{account_id}:role/{role_name}"
    creds = boto3.client("sts").assume_role(
        RoleArn=arn, RoleSessionName="ebs-orphans"
    )["Credentials"]
    session = boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
    )
    # Without opt-in filter, DescribeRegions returns only regions that are enabled.
    regions = session.client("ec2", region_name="us-east-1").describe_regions()["Regions"]
    rows = []
    for r in regions:
        name = r["RegionName"]
        ec2 = session.client("ec2", region_name=name)
        rows += scan_region(ec2, account_id, name, min_age_days, price, now)
    return rows


def active_accounts():
    pages = boto3.client("organizations").get_paginator("list_accounts").paginate()
    return [a["Id"] for p in pages for a in p["Accounts"] if a["Status"] == "ACTIVE"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-age-days", type=int, default=30)
    ap.add_argument("--role-name", default="OrganizationAccountAccessRole")
    ap.add_argument("--price-per-gb-month", type=float, default=DEFAULT_PRICE)
    ap.add_argument("--out", default="orphans.csv")
    args = ap.parse_args()

    now = datetime.now(UTC)
    rows = []
    for account_id in active_accounts():
        try:
            rows += scan_account(
                account_id, args.role_name, args.min_age_days, args.price_per_gb_month, now
            )
        except (ClientError, BotoCoreError) as err:
            print(f"warning: skipping {account_id}: {err}")

    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    total_gb = sum(r["size_gb"] for r in rows)
    total_cost = monthly_cost(total_gb, args.price_per_gb_month)
    print(f"{len(rows)} orphan volumes, {total_gb} GB, ~${total_cost:.2f}/month -> {args.out}")


if __name__ == "__main__":
    main()
