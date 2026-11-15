---
name: eta-aws-lab
description: 수업 전용 AWS 계정(eta-lab)에서 eta-mini 실습 자원을 만들고·배포하고·지울 때의 우리 규칙. 이름 접두어와 Owner 태그, 권한 경계, 지우는 순서, lab check 확인. "AWS 에 올려 줘", "인스턴스 켜 줘", "내 자원 정리해 줘", "남은 거 있나 봐 줘" 처럼 이 계정의 자원을 만들거나 지우는 모든 부탁에 쓴다. 일반 AWS 지식은 aws-* 스킬이 맡고, 이 스킬은 이 계정에서만 통하는 규칙을 맡는다.
---

# eta-lab 계정에서 일하는 규칙

한 계정을 여러 사람이 함께 쓴다. 규칙을 어긴 자원은 주인을 찾을 수 없고, 남으면 법인카드로 청구된다.
일반 AWS 지식(IMDS, IAM 정책 문법, S3 설정 등)은 `aws-*` 스킬을 따른다. 여기와 어긋나면 **여기가 우선**이다.

## 시작할 때

1. `uv run --group ml lab whoami` 로 아이디·계정·리전을 확인한다. 리전은 `ap-northeast-2` 뿐이다. 다른 리전은 거부된다.
2. 아이디를 `ME` 로 둔다. 사용자에게 묻지 않고 `lab whoami` 의 답을 쓴다.

## 만들 때

- **이름** : `<ME>-eta-…` 로 시작한다. 보안 그룹 `<ME>-eta-web`(`lab launch` 가 이 이름으로 찾는다), 리포지토리 `<ME>-eta-api`·`<ME>-eta-web`, 버킷 `<ME>-eta-models`, 역할 `<ME>-eta-serve`·`-ci`·`-train`·`-batch`, 파라미터·로그 그룹 `/<ME>/eta/…`.
- **태그** : `Project=eta-lab`, `Owner=<ME>` 를 **만드는 명령에서** 붙인다. 인스턴스는 디스크(`volume`)에도 붙인다. `aws-compute` 스킬의 `managed_by` 태그는 쓰지 않는다.
- **역할** : `--permissions-boundary arn:aws:iam::<계정>:policy/eta-lab-boundary` 가 없으면 `AccessDenied` 다. 정책 파일은 `uv run --group ml lab render infra/aws/student/<파일>` 이 낸 경로를 쓴다.
- **인스턴스** : `aws ec2 run-instances` 를 직접 짜지 않고 `lab launch` 를 쓴다. `t3.small` 과 `g4dn.xlarge` 만 켤 수 있다.
- **시간당 돈이 나가는 것**(인스턴스, GPU, ALB, 고정 IP)은 만들기 전에 시간당 단가와 끄는 방법을 한 줄로 말하고 사용자의 답을 기다린다. GPU 는 `lab gpu-bench` 처럼 스스로 꺼지는 방식으로만 켠다.
- 이미 있는 묶음 명령을 먼저 쓴다 : `lab launch | run | deploy | promote | dns | gpu-bench | batch | empty-bucket | check`.

## 셸마다 다른 곳

- **PowerShell** : 쉼표가 든 인자는 큰따옴표로 감싼다 — `"Key=Owner,Value=$ME"`. 안 감싸면 `$ME` 가 글자 그대로 태그에 들어간다. 줄 잇기는 백틱, `curl` 은 `curl.exe`.
- **zsh** : 변수 뒤에 `:` 이 오면 `${ACCT}` 로 감싼다(`$ACCT:role` 은 글자가 깨진다). 여러 값을 담은 변수는 배열로 받아 `${ARR[@]}` 로 펼친다.
- 사용자의 운영체제를 모르면 묻는다. 윈도우 사용자에게 bash 명령을 주지 않는다.

## 이 계정에서 겪은 함정

- **OIDC `sub`** : 문서의 `repo:<소유자>/<저장소>` 를 추측해 쓰지 않는다. `gh api "repos/{owner}/{repo}/actions/oidc/customization/sub" -q .sub_claim_prefix` 로 얻는다(`lab render` 가 채운다).
- **ECR** : 리포지토리는 `--image-tag-mutability IMMUTABLE` 과 `scanOnPush=true` 로 만든다. 그래서 이미지 태그는 커밋 sha. 빌드는 `--platform linux/amd64 --provenance=false`.
- **DNS** : `<ME>.aws.pyhub.kr` 레코드를 만들기 전에 그 이름을 조회하지 않는다. 「없다」가 15분 캐시된다.
- **ACM** : 인증서를 요청하고 15초쯤 뒤에 검증 레코드를 읽는다. 바로 읽으면 `None` 이다.
- **비용 조회**(`aws ce …`)는 한 번에 $0.01 이고 `us-east-1` 에 묻는다. 반복하지 않는다.

## 지울 때

지우기 전에 `uv run --group ml lab check` 의 목록을 사용자에게 보여 주고, **지워도 되는지 답을 받은 뒤** 지운다.

순서 — 의존하는 것부터, 시간당 과금되는 것부터 :

1. DNS 레코드(`lab dns delete <이름> A`, ACM 검증용은 `lab dns delete <이름> CNAME`)
2. ALB → 대상 그룹 → ACM 인증서(ALB 삭제 20초 뒤)
3. 인스턴스 종료를 기다린 뒤 → 고정 IP → 보안 그룹(인스턴스 것, 그다음 ALB 것)
4. ECR 리포지토리(`--force`)
5. 버킷 : `lab empty-bucket`(이전 버전·삭제 표시까지) → `delete-bucket`. `aws s3 rm --recursive` 로는 비지 않는다.
6. 경보 → SNS 주제 → 로그 그룹 → 파라미터
7. 역할 : 인스턴스 프로파일에서 빼기 → 프로파일 삭제 → 정책 떼기·지우기 → 역할 삭제
8. 저장소 변수(`gh variable delete ME`, `AWS_ROLE_ARN`)

## 끝낼 때

- `uv run --group ml lab check` 가 종료 코드 0 이어야 끝이다. 출력을 그대로 보여 준다.
- 태그 검색(`resourcegroupstaggingapi`)은 지운 것을 한동안 보여 주므로 확인에 쓰지 않는다.
- 남긴 것이 있으면 무엇을 왜 남겼는지, 시간당 얼마인지 말한다.
