#!/bin/bash
# 인스턴스를 처음 켤 때 한 번 돈다(root). 로그 : /var/log/cloud-init-output.log
set -euxo pipefail
dnf install -y docker amazon-ecr-credential-helper
systemctl enable --now docker

# Compose 플러그인 : Amazon Linux 2023 의 docker 패키지에는 들어 있지 않다
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# ECR 로그인 : 비밀번호 대신 인스턴스 역할을 쓴다
mkdir -p /root/.docker
echo '{"credsStore": "ecr-login"}' > /root/.docker/config.json

mkdir -p /opt/eta
