# ebs-orphan-report

Unattached EBS volumes keep costing money after the instance they belonged to is gone.
In an AWS Organization with many accounts and regions, nobody sees them all in one place.
This tool scans every account and region and writes the old ones to a CSV for a person to review.

```mermaid
flowchart LR
    A[Admin account] --> B[Assume role in each member account]
    B --> C[Scan enabled regions for available volumes]
    C --> D[orphans.csv]
    D --> E[Human review and delete]
```

## Usage

Run it with credentials for the Organization management account (or a delegated admin):

```
pip install -r requirements.txt
python ebs_orphans.py --min-age-days 30 --role-name OrganizationAccountAccessRole --price-per-gb-month 0.08 --out orphans.csv
```

It prints a short total and writes one row per volume. It never deletes anything.

## IAM

Permissions policy on the role in each member account (read-only):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["ec2:DescribeVolumes", "ec2:DescribeRegions"],
    "Resource": "*"
  }]
}
```

Trust policy, so the admin account can assume it (123456789012 is the admin account):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"AWS": "arn:aws:iam::123456789012:root"},
    "Action": "sts:AssumeRole"
  }]
}
```

The admin side also needs `organizations:ListAccounts` and `sts:AssumeRole`.

## Limits

- CreateTime is not detach time, so a volume detached yesterday can look old.
- Snapshots and AMI dependencies are not checked.
- Cost is an estimate from one flat price.
- Only accounts reachable through the role are scanned.

## Tests

```
pip install -r requirements.txt
pytest
```
