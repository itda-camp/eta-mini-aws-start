"""AWS 실습 도우미. 윈도우·macOS·리눅스에서 같은 명령으로 돈다(셸 스크립트를 쓰지 않는다).

    uv run --group ml lab whoami                  내 아이디·계정·리전
    uv run --group ml lab render <정책 틀.json>   ${ME} ${ACCT} … 를 채워 .aws-out/ 에 쓰고 경로를 낸다
    uv run --group ml lab launch                  서빙 인스턴스 한 대를 켠다
    uv run --group ml lab run "<셸 명령>"         내 인스턴스에서 명령을 돌린다(SSM Run Command, SSH 없음)
    uv run --group ml lab deploy <이미지 태그>    서버용 Compose 파일을 보내고 그 태그로 띄운다
    uv run --group ml lab promote <판>            current.json 이 그 판을 가리키게 한다(승격·롤백)
    uv run --group ml lab gpu-bench               GPU 인스턴스에서 학습 시간을 재고, 끝나면 스스로 종료한다
    uv run --group ml lab batch                   작은 인스턴스에서 S3 의 입력을 한꺼번에 예측하고, 끝나면 스스로 종료한다
    uv run --group ml lab dns upsert <이름> A <IP>  수업 영역에 레코드를 만든다 (alias <이름> A <ALB 이름>, delete <이름> <유형>)
    uv run --group ml lab empty-bucket            모델 버킷을 이전 버전까지 비운다 (버킷을 지우기 전에)
    uv run --group ml lab check                   남은 내 자원을 서비스마다 물어서 모은다. 비어 있어야 통과

내 아이디(ME)는 로그인한 IAM 사용자 이름에서 얻는다. CI 처럼 역할로 도는 곳에서는 환경변수 ME 를 준다.
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import boto3

REGION = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "ap-northeast-2"
ROOT = Path(__file__).resolve().parents[2]
STUDENT = Path(__file__).resolve().parent / "student"
OUT = ROOT / ".aws-out"

session = boto3.Session(region_name=REGION)


def identity() -> tuple[str, str]:
    """(내 아이디, 계정 번호)."""
    who = session.client("sts").get_caller_identity()
    me = os.getenv("ME") or (who["Arn"].rsplit("/", 1)[-1] if ":user/" in who["Arn"] else "")
    if not me:
        sys.exit("내 아이디를 알 수 없다. 환경변수 ME 를 준다 (IAM 사용자가 아닌 역할로 로그인했다)")
    return me, who["Account"]


def tags(me: str, **extra: str) -> list[dict[str, str]]:
    pairs = {"Project": "eta-lab", "Owner": me, **extra}
    return [{"Key": k, "Value": v} for k, v in pairs.items()]


def my_instance(me: str) -> str:
    found = session.client("ec2").describe_instances(
        Filters=[
            {"Name": "tag:Owner", "Values": [me]},
            {"Name": "tag:Name", "Values": [f"{me}-eta"]},
            {"Name": "instance-state-name", "Values": ["running"]},
        ]
    )
    ids = [i["InstanceId"] for r in found["Reservations"] for i in r["Instances"]]
    if not ids:
        sys.exit(f"켜져 있는 {me}-eta 인스턴스가 없다 (lab launch)")
    return ids[0]


def ssm_run(instance_id: str, command: str, *, quiet: bool = False) -> str:
    """인스턴스에서 셸 명령을 돌리고 끝날 때까지 기다린다. 실패하면 이 프로그램도 실패한다."""
    ssm = session.client("ssm")
    cid = ssm.send_command(
        InstanceIds=[instance_id], DocumentName="AWS-RunShellScript", Parameters={"commands": [command]}
    )["Command"]["CommandId"]
    while True:
        time.sleep(2)
        try:
            inv = ssm.get_command_invocation(CommandId=cid, InstanceId=instance_id)
        except ssm.exceptions.InvocationDoesNotExist:
            continue  # 보낸 직후에는 아직 기록이 없다
        if inv["Status"] not in ("Pending", "InProgress", "Delayed"):
            break
    out = inv["StandardOutputContent"]
    if not quiet:
        sys.stdout.write(out)
        sys.stderr.write(inv["StandardErrorContent"])
    if inv["Status"] != "Success":
        sys.exit(f"명령 실패: {inv['Status']}")
    return out


# ------------------------------------------------------------------ 명령


def cmd_whoami(args: argparse.Namespace) -> None:
    me, acct = identity()
    print(f"ME={me}\nACCT={acct}\nREGION={REGION}")


def cmd_render(args: argparse.Namespace) -> None:
    me, acct = identity()
    sub_prefix = os.getenv("SUB_PREFIX", "")
    if "${SUB_PREFIX}" in (text := Path(args.template).read_text(encoding="utf-8")) and not sub_prefix:
        # GitHub 이 OIDC 토큰의 sub 에 넣는 저장소 표기. 저장소마다 다르므로 물어서 얻는다
        sub_prefix = subprocess.run(
            ["gh", "api", "repos/{owner}/{repo}/actions/oidc/customization/sub", "-q", ".sub_claim_prefix"],
            capture_output=True, text=True, check=True, cwd=ROOT,
        ).stdout.strip()
    values = {"ME": me, "ACCT": acct, "ZONE": os.getenv("ZONE", ""), "SUB_PREFIX": sub_prefix, "EMAIL": os.getenv("EMAIL", "")}
    for key, value in values.items():
        text = text.replace("${" + key + "}", value)
    json.loads(text)  # 틀이 깨졌으면 여기서 멈춘다
    OUT.mkdir(exist_ok=True)
    target = OUT / Path(args.template).name
    target.write_text(text, encoding="utf-8", newline="\n")
    print(target.relative_to(ROOT).as_posix())  # aws … --policy-document file://<이 경로>


def cmd_launch(args: argparse.Namespace) -> None:
    me, _ = identity()
    ec2 = session.client("ec2")
    ami = session.client("ssm").get_parameter(
        Name="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
    )["Parameter"]["Value"]
    sg = ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": [f"{me}-eta-web"]}])["SecurityGroups"]
    if not sg:
        sys.exit(f"보안 그룹 {me}-eta-web 이 없다")
    # 윈도우에서 받은 저장소는 줄 끝이 CRLF 일 수 있다. 서버의 bash 는 LF 만 읽는다
    user_data = (STUDENT / "user-data.sh").read_text(encoding="utf-8").replace("\r\n", "\n")
    iid = ec2.run_instances(
        ImageId=ami,
        InstanceType=args.type,
        MinCount=1,
        MaxCount=1,
        IamInstanceProfile={"Name": f"{me}-eta-serve"},
        SecurityGroupIds=[sg[0]["GroupId"]],
        UserData=user_data,
        MetadataOptions={"HttpTokens": "required", "HttpPutResponseHopLimit": 2},
        TagSpecifications=[
            {"ResourceType": "instance", "Tags": tags(me, Name=f"{me}-eta")},
            {"ResourceType": "volume", "Tags": tags(me)},
        ],
    )["Instances"][0]["InstanceId"]
    print(f"{iid} 켜는 중 …", file=sys.stderr)
    ec2.get_waiter("instance_running").wait(InstanceIds=[iid])
    ssm = session.client("ssm")
    while not ssm.describe_instance_information(Filters=[{"Key": "InstanceIds", "Values": [iid]}])["InstanceInformationList"]:
        time.sleep(5)  # SSM 에 나타날 때까지
    ssm_run(iid, "cloud-init status --wait", quiet=True)  # 사용자 데이터(도커 설치)가 끝날 때까지
    ip = ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0].get("PublicIpAddress", "")
    print(f"{iid} {ip}")


def cmd_run(args: argparse.Namespace) -> None:
    me, _ = identity()
    ssm_run(my_instance(me), args.command)


def cmd_deploy(args: argparse.Namespace) -> None:
    me, acct = identity()
    registry = f"{acct}.dkr.ecr.{REGION}.amazonaws.com"
    files = ["docker-compose.aws.yml"]
    # 로그 그룹이 있을 때만 CloudWatch 로 보낸다(없으면 awslogs 드라이버가 컨테이너를 못 띄운다)
    if session.client("logs").describe_log_groups(logGroupNamePrefix=f"/{me}/eta").get("logGroups"):
        files.append("docker-compose.awslogs.yml")
    send = ""
    for i, name in enumerate(files):
        text = (ROOT / name).read_text(encoding="utf-8").replace("\r\n", "\n")
        target = "docker-compose.yml" if i == 0 else name
        send += f"echo {base64.b64encode(text.encode()).decode()} | base64 -d > {target}\n"
    compose_file = ":".join(["docker-compose.yml"] + files[1:])
    # HTTPS 길 1 의 nginx 설정. COMPOSE_PROFILES=https 일 때만 쓰이지만 늘 보내 둔다
    conf = (ROOT / "web" / "nginx.https.conf").read_text(encoding="utf-8").replace("\r\n", "\n")
    send += f"echo {base64.b64encode(conf.encode()).decode()} | base64 -d > nginx-https.conf\n"
    print(f"로그: {'CloudWatch /' + me + '/eta' if len(files) > 1 else '서버 안(docker logs)'}")
    ssm_run(
        my_instance(me),
        f"""set -eu
cd /opt/eta
{send}umask 077
# 비밀값 : /{me}/eta/ 아래 파라미터를 이름=값 으로. 서버에 손으로 적지 않는다
aws ssm get-parameters-by-path --path /{me}/eta --with-decryption --region {REGION} \\
  --query 'Parameters[].[Name,Value]' --output text | sed 's|^/{me}/eta/||' | tr '\\t' '=' > .env.params
if grep -q '^POSTGRES_PASSWORD=' .env.params; then
  mv .env.params .env.secrets
elif [ -f .env.secrets ]; then
  rm .env.params; echo '비밀값 : Parameter Store 에 없어 지난번에 서버에서 만든 값을 쓴다'
else
  rm .env.params; echo '비밀값 : Parameter Store 에 없어 서버에서 난수로 만들었다'
  for k in POSTGRES_PASSWORD SEED_ADMIN_PASSWORD SEED_VIEWER_PASSWORD; do echo "$k=$(openssl rand -hex 16)"; done > .env.secrets
fi
cat .env.secrets > .env
cat >> .env <<ENV
REGISTRY={registry}
ME={me}
TAG={args.tag}
MODEL_S3_BUCKET={me}-eta-models
COMPOSE_FILE={compose_file}
ENV
docker compose pull -q
# HTTPS 길 1 : 인증서가 없으면 nginx 를 띄우기 전에 받는다. 이때만 certbot 이 80 포트를 직접 연다
if grep -q '^COMPOSE_PROFILES=.*https' .env && \\
   ! docker compose run --rm --no-deps --entrypoint test certbot -s /etc/letsencrypt/live/eta/fullchain.pem; then
  DOMAIN=$(grep '^DOMAIN=' .env | cut -d= -f2-)
  echo "인증서 : 처음이라 Let's Encrypt 에서 받는다 ($DOMAIN)"
  docker compose stop proxy
  docker compose run --rm --no-deps -p 80:80 --entrypoint certbot certbot certonly --standalone -q \\
    --cert-name eta -d "$DOMAIN" --agree-tos --register-unsafely-without-email -n
fi
# DB 비밀번호를 .env 와 맞춘다 — 볼륨이 이미 있으면 postgres 는 새 POSTGRES_PASSWORD 를 무시한다
docker compose up -d --wait db
docker compose exec -T db psql -q -U postgres -c "ALTER USER postgres PASSWORD '$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)'"
docker compose up -d --wait
docker compose ps --format 'table {{{{.Service}}}}\\t{{{{.Image}}}}\\t{{{{.Status}}}}'
curl -fsS localhost:8080/api/health; echo
""",
    )


def cmd_promote(args: argparse.Namespace) -> None:
    me, _ = identity()
    s3 = session.client("s3")
    bucket, prefix = f"{me}-eta-models", f"models/{args.impl}"
    if "Contents" not in s3.list_objects_v2(Bucket=bucket, Prefix=f"{prefix}/{args.version}/", MaxKeys=1):
        sys.exit(f"s3://{bucket}/{prefix}/{args.version}/ 에 올린 판이 없다")
    s3.put_object(
        Bucket=bucket,
        Key=f"{prefix}/current.json",
        Body=json.dumps({"version": args.version}).encode(),
        ContentType="application/json",
    )
    print(f"s3://{bucket}/{prefix}/current.json → {args.version}")


def cmd_gpu_bench(args: argparse.Namespace) -> None:
    """GPU 인스턴스를 켜서 training/bench_torch.py 를 돌리고, 결과를 S3 에 올린 뒤 스스로 종료하게 한다."""
    me, _ = identity()
    ec2, s3 = session.client("ec2"), session.client("s3")
    ami = session.client("ssm").get_parameter(
        Name="/aws/service/deeplearning/ami/x86_64/base-oss-nvidia-driver-gpu-amazon-linux-2023/latest/ami-id"
    )["Parameter"]["Value"]  # 드라이버가 든 Deep Learning AMI
    bucket, run = f"{me}-eta-models", time.strftime("%Y%m%d-%H%M%S")
    script = base64.b64encode((ROOT / "training" / "bench_torch.py").read_bytes().replace(b"\r\n", b"\n")).decode()
    user_data = f"""#!/bin/bash
exec > /var/log/bench.log 2>&1
set -x
shutdown -h +{args.max_minutes}   # 안전장치 : 무슨 일이 있어도 이 시간이 지나면 꺼진다
export HOME=/root
BOOTED=$(date +%s)
echo {script} | base64 -d > /root/bench_torch.py
curl -LsSf https://astral.sh/uv/install.sh | sh
{{
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
  /root/.local/bin/uv run /root/bench_torch.py --sizes {" ".join(args.sizes)}
  /root/.local/bin/uv run /root/bench_torch.py --device cpu --sizes {" ".join(args.sizes[:3])}
  echo "boot_to_finish_seconds $(( $(date +%s) - BOOTED ))"
}} > /root/result.txt
aws s3 cp /root/result.txt s3://{bucket}/bench/{run}/result.txt
aws s3 cp /var/log/bench.log s3://{bucket}/bench/{run}/bench.log
shutdown -h now                    # 끝나면 스스로 꺼진다 → 종료(terminate)
"""
    launched = time.time()
    iid = ec2.run_instances(
        ImageId=ami,
        InstanceType=args.type,
        MinCount=1,
        MaxCount=1,
        IamInstanceProfile={"Name": f"{me}-eta-train"},
        UserData=user_data,
        InstanceInitiatedShutdownBehavior="terminate",  # 꺼지면 멈춤이 아니라 종료 — 디스크도 지워진다
        MetadataOptions={"HttpTokens": "required", "HttpPutResponseHopLimit": 2},
        TagSpecifications=[
            {"ResourceType": "instance", "Tags": tags(me, Name=f"{me}-eta-gpu")},
            {"ResourceType": "volume", "Tags": tags(me)},
        ],
    )["Instances"][0]["InstanceId"]
    print(f"{iid} ({args.type}) 켜는 중 … 끝나면 스스로 종료한다", file=sys.stderr)
    state = "pending"
    while state != "terminated":  # 스스로 꺼질 때까지 지켜본다
        time.sleep(15)
        state = ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0]["State"]["Name"]
        if time.time() - launched > (args.max_minutes + 10) * 60:
            sys.exit(f"{iid} 가 아직 {state} 다. 직접 종료한다: aws ec2 terminate-instances --instance-ids {iid}")
    minutes = (time.time() - launched) / 60
    print(f"{iid} {state} — 켠 뒤 {minutes:.1f}분", file=sys.stderr)
    try:
        print(s3.get_object(Bucket=bucket, Key=f"bench/{run}/result.txt")["Body"].read().decode())
    except s3.exceptions.NoSuchKey:
        sys.exit(f"결과가 없다. s3://{bucket}/bench/{run}/bench.log 를 본다")


def cmd_batch(args: argparse.Namespace) -> None:
    """작은 인스턴스를 켜서 training/batch_predict.py 로 S3 의 입력을 한꺼번에 예측하고, 결과를 올린 뒤 스스로 종료하게 한다."""
    from importlib.metadata import version

    me, _ = identity()
    ec2, s3 = session.client("ec2"), session.client("s3")
    ami = session.client("ssm").get_parameter(
        Name="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
    )["Parameter"]["Value"]
    bucket, run = f"{me}-eta-models", time.strftime("%Y%m%d-%H%M%S")
    script = base64.b64encode((ROOT / "training" / "batch_predict.py").read_bytes().replace(b"\r\n", b"\n")).decode()
    # 모델 파일은 학습한 쪽의 scikit-learn 판으로 읽어야 한다
    pin = f"--with scikit-learn=={version('scikit-learn')} --with joblib=={version('joblib')}"
    user_data = f"""#!/bin/bash
exec > /var/log/batch.log 2>&1
set -x
shutdown -h +{args.max_minutes}   # 안전장치 : 무슨 일이 있어도 이 시간이 지나면 꺼진다
export HOME=/root AWS_DEFAULT_REGION={REGION}
BOOTED=$(date +%s)
echo {script} | base64 -d > /root/batch_predict.py
curl -LsSf https://astral.sh/uv/install.sh | sh
/root/.local/bin/uv run {pin} /root/batch_predict.py --bucket {bucket} --input {args.input} --output batch/out/{run}/predictions.csv > /root/summary.json
echo "boot_to_finish_seconds $(( $(date +%s) - BOOTED ))" >> /root/summary.json
aws s3 cp /root/summary.json s3://{bucket}/batch/out/{run}/summary.json
aws s3 cp /var/log/batch.log s3://{bucket}/batch/out/{run}/batch.log
shutdown -h now                    # 끝나면 스스로 꺼진다 → 종료(terminate)
"""
    launched = time.time()
    iid = ec2.run_instances(
        ImageId=ami,
        InstanceType=args.type,
        MinCount=1,
        MaxCount=1,
        IamInstanceProfile={"Name": f"{me}-eta-batch"},
        UserData=user_data,
        InstanceInitiatedShutdownBehavior="terminate",
        MetadataOptions={"HttpTokens": "required", "HttpPutResponseHopLimit": 2},
        TagSpecifications=[
            {"ResourceType": "instance", "Tags": tags(me, Name=f"{me}-eta-batch")},
            {"ResourceType": "volume", "Tags": tags(me)},
        ],
    )["Instances"][0]["InstanceId"]
    print(f"{iid} ({args.type}) 켜는 중 … 끝나면 스스로 종료한다", file=sys.stderr)
    state = "pending"
    while state != "terminated":
        time.sleep(10)
        state = ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0]["State"]["Name"]
        if time.time() - launched > (args.max_minutes + 10) * 60:
            sys.exit(f"{iid} 가 아직 {state} 다. 직접 종료한다: aws ec2 terminate-instances --instance-ids {iid}")
    print(f"{iid} {state} — 켠 뒤 {(time.time() - launched) / 60:.1f}분", file=sys.stderr)
    try:
        print(s3.get_object(Bucket=bucket, Key=f"batch/out/{run}/summary.json")["Body"].read().decode())
    except s3.exceptions.NoSuchKey:
        sys.exit(f"결과가 없다. s3://{bucket}/batch/out/{run}/batch.log 를 본다")


def find_mine(me: str) -> list[tuple[str, str]]:
    """내 것으로 보이는 자원을 서비스마다 직접 물어서 모은다. (종류, 이름) 목록."""
    found: list[tuple[str, str]] = []
    mine = lambda name: name.startswith(f"{me}-") or name.startswith(f"/{me}/")  # noqa: E731
    owned = [{"Name": "tag:Owner", "Values": [me]}]
    ec2 = session.client("ec2")
    for r in ec2.describe_instances(Filters=owned)["Reservations"]:
        for i in r["Instances"]:
            if i["State"]["Name"] != "terminated":
                found.append(("EC2 인스턴스", f"{i['InstanceId']} ({i['State']['Name']})"))
    found += [("EBS 볼륨", v["VolumeId"]) for v in ec2.describe_volumes(Filters=owned)["Volumes"]]
    found += [("EBS 스냅샷", v["SnapshotId"]) for v in ec2.describe_snapshots(OwnerIds=["self"], Filters=owned)["Snapshots"]]
    found += [("고정 IP", a["PublicIp"]) for a in ec2.describe_addresses(Filters=owned)["Addresses"]]
    found += [("보안 그룹", g["GroupName"]) for g in ec2.describe_security_groups()["SecurityGroups"] if mine(g["GroupName"])]
    elb = session.client("elbv2")
    found += [("ALB", b["LoadBalancerName"]) for b in elb.describe_load_balancers()["LoadBalancers"] if mine(b["LoadBalancerName"])]
    found += [("대상 그룹", t["TargetGroupName"]) for t in elb.describe_target_groups()["TargetGroups"] if mine(t["TargetGroupName"])]
    acm = session.client("acm")
    found += [("ACM 인증서", c["DomainName"]) for c in acm.list_certificates()["CertificateSummaryList"] if c["DomainName"].startswith(f"{me}.")]
    r53 = session.client("route53")
    for zone in r53.list_hosted_zones()["HostedZones"]:
        for rec in r53.list_resource_record_sets(HostedZoneId=zone["Id"])["ResourceRecordSets"]:
            if f"{me}." in rec["Name"] or rec["Name"].startswith(f"{me}-"):
                found.append(("Route 53 레코드", f"{rec['Name']} {rec['Type']}"))
    found += [("S3 버킷", b["Name"]) for b in session.client("s3").list_buckets()["Buckets"] if mine(b["Name"])]
    found += [("ECR 리포지토리", r["repositoryName"]) for r in session.client("ecr").describe_repositories()["repositories"] if mine(r["repositoryName"])]
    logs = session.client("logs")
    found += [("로그 그룹", g["logGroupName"]) for g in logs.describe_log_groups(logGroupNamePrefix=f"/{me}/")["logGroups"]]
    cw = session.client("cloudwatch")
    found += [("경보", a["AlarmName"]) for a in cw.describe_alarms(AlarmNamePrefix=f"{me}-")["MetricAlarms"]]
    found += [("SNS 주제", t["TopicArn"].rsplit(":", 1)[-1]) for t in session.client("sns").list_topics()["Topics"] if mine(t["TopicArn"].rsplit(":", 1)[-1])]
    ssm = session.client("ssm")
    params = ssm.get_parameters_by_path(Path=f"/{me}/", Recursive=True)["Parameters"]
    found += [("파라미터", p["Name"]) for p in params]
    iam = session.client("iam")
    found += [("IAM 역할", r["RoleName"]) for page in iam.get_paginator("list_roles").paginate() for r in page["Roles"] if mine(r["RoleName"])]
    found += [("인스턴스 프로파일", p["InstanceProfileName"]) for p in iam.list_instance_profiles()["InstanceProfiles"] if mine(p["InstanceProfileName"])]
    found += [("IAM 정책", p["PolicyName"]) for p in iam.list_policies(Scope="Local")["Policies"] if mine(p["PolicyName"])]
    return found


def _zone() -> tuple[str, str]:
    """(영역 ID, 영역 이름). 수업 계정에는 영역이 하나다."""
    zones = session.client("route53").list_hosted_zones()["HostedZones"]
    if len(zones) != 1:
        sys.exit(f"Route 53 영역이 {len(zones)}개다. 하나여야 한다")
    return zones[0]["Id"], zones[0]["Name"].rstrip(".")


def cmd_dns(args: argparse.Namespace) -> None:
    """수업 영역(aws.pyhub.kr)의 레코드를 만들고 지운다. 이름은 영역 이름을 뺀 앞부분만 적어도 된다."""
    r53 = session.client("route53")
    zone_id, zone_name = _zone()
    name = args.name.rstrip(".")
    if not name.endswith(zone_name):
        name = f"{name}.{zone_name}"
    if args.action == "upsert":
        record = {"Name": name, "Type": args.type, "TTL": 60, "ResourceRecords": [{"Value": args.value}]}
        change = {"Action": "UPSERT", "ResourceRecordSet": record}
    elif args.action == "alias":  # A 레코드가 ALB 를 가리키게 (ALB 는 IP 가 바뀌므로 이름으로 잇는다)
        alb = session.client("elbv2").describe_load_balancers(Names=[args.value])["LoadBalancers"][0]
        target = {"HostedZoneId": alb["CanonicalHostedZoneId"], "DNSName": f"dualstack.{alb['DNSName']}", "EvaluateTargetHealth": False}
        change = {"Action": "UPSERT", "ResourceRecordSet": {"Name": name, "Type": "A", "AliasTarget": target}}
    else:  # delete : 지금 있는 레코드를 그대로 읽어 지운다
        found = r53.list_resource_record_sets(HostedZoneId=zone_id, StartRecordName=name, StartRecordType=args.type, MaxItems="1")
        records = [r for r in found["ResourceRecordSets"] if r["Name"].rstrip(".") == name and r["Type"] == args.type]
        if not records:
            sys.exit(f"{name} {args.type} 레코드가 없다")
        change = {"Action": "DELETE", "ResourceRecordSet": records[0]}
    r53.change_resource_record_sets(HostedZoneId=zone_id, ChangeBatch={"Changes": [change]})
    print(f"{args.action} {name} {args.type if args.action != 'alias' else 'A(alias)'}")


def cmd_empty_bucket(args: argparse.Namespace) -> None:
    """버킷의 모든 객체를 **이전 버전과 삭제 표시까지** 지운다. 버킷 자체는 남는다."""
    me, _ = identity()
    bucket = boto3.resource("s3", region_name=REGION).Bucket(f"{me}-eta-models")
    deleted = bucket.object_versions.delete()
    print(f"s3://{bucket.name} : {sum(len(d.get('Deleted', [])) for d in deleted)}개(버전 포함) 지움")


def cmd_check(args: argparse.Namespace) -> None:
    """남은 자원이 하나도 없어야 통과(종료 코드 0)."""
    me, _ = identity()
    found = find_mine(me)
    for kind, name in found:
        print(f"{kind:<14} {name}")
    if found:
        sys.exit(f"\n{me} 의 자원이 {len(found)}개 남아 있다")
    print(f"{me} 의 자원이 없다 ({REGION})")


def main() -> None:
    parser = argparse.ArgumentParser(prog="lab", description="AWS 실습 도우미")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("whoami").set_defaults(fn=cmd_whoami)
    p = sub.add_parser("render"); p.add_argument("template"); p.set_defaults(fn=cmd_render)
    p = sub.add_parser("launch"); p.add_argument("--type", default="t3.small"); p.set_defaults(fn=cmd_launch)
    p = sub.add_parser("run"); p.add_argument("command"); p.set_defaults(fn=cmd_run)
    p = sub.add_parser("deploy"); p.add_argument("tag"); p.set_defaults(fn=cmd_deploy)
    p = sub.add_parser("promote"); p.add_argument("version"); p.add_argument("--impl", default="sklearn"); p.set_defaults(fn=cmd_promote)
    p = sub.add_parser("gpu-bench")
    p.add_argument("--type", default="g4dn.xlarge")
    p.add_argument("--sizes", nargs="+", default=["20000x64", "200000x256", "2000000x256", "2000000x1024"])
    p.add_argument("--max-minutes", type=int, default=30)
    p.set_defaults(fn=cmd_gpu_bench)
    p = sub.add_parser("batch")
    p.add_argument("--input", default="batch/in/orders.csv")
    p.add_argument("--type", default="t3.small")
    p.add_argument("--max-minutes", type=int, default=15)
    p.set_defaults(fn=cmd_batch)
    p = sub.add_parser("dns")
    p.add_argument("action", choices=["upsert", "alias", "delete"])
    p.add_argument("name")
    p.add_argument("type", nargs="?", default="A")
    p.add_argument("value", nargs="?", default="")
    p.set_defaults(fn=cmd_dns)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    sub.add_parser("empty-bucket").set_defaults(fn=cmd_empty_bucket)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
