# 모니터링 설정 가이드 (Prometheus + Grafana + vLLM)

`docker compose ... --profile monitoring --profile vllm up -d` 로 5개 서비스
(bot · worker · vLLM · Prometheus · Grafana)를 띄운 뒤, **웹에서 모니터링을
구성하는 전체 과정**을 순서대로 안내합니다.

| 서비스 | URL | 로그인 |
|--------|-----|--------|
| Grafana | http://localhost:3000 | `admin` / `.env` 의 `GRAFANA_ADMIN_PASSWORD` (기본 `changeme`) |
| Prometheus | http://localhost:9090 | 없음 |
| vLLM | http://localhost:8000 | 없음 (OpenAI 호환 API) |

> 모든 포트는 `127.0.0.1` 바인딩이라 **같은 PC 에서만** 접속됩니다.

**데이터소스·대시보드는 자동 프로비저닝**됩니다(아래 *자동 대시보드* 참고). 수집 대상:
- **worker** (앱 사용량: 작업 처리율·지연·라우트/백엔드별 사용량)
- **vLLM** (추론 지표) · **Qdrant** (벡터 DB) · **cAdvisor/node-exporter** (컨테이너·호스트 리소스)
- **Postgres** (Task 이력 DB — 작업 로그). DB 대시보드는 `--profile postgres` 동시 실행 시 동작.

리소스·DB 패널까지 모두 보려면:
```powershell
docker compose --profile monitoring --profile postgres --profile vllm up -d
```

---

## 0. 사전 점검 — 컨테이너 상태

```powershell
docker compose -f docker-compose.yml -f docker-compose.registry.yml `
  --profile monitoring --profile vllm ps
```

기대 상태:

| 컨테이너 | 상태 | 비고 |
|----------|------|------|
| bot | healthy | |
| worker | healthy | |
| prometheus | healthy | |
| grafana | healthy | |
| vllm | **unhealthy 여도 정상** | 헬스체크 표시 문제일 뿐 — 아래 8번 참고 |

---

## 1. Prometheus — 수집 대상부터 확인

### 1-1. 타겟 상태
브라우저에서 **http://localhost:9090/targets** 접속.

| job | 기대 상태 | 안 되면 |
|-----|-----------|---------|
| `prometheus` | 🟢 UP | — |
| `vllm` | 🟢 UP | vLLM 컨테이너 확인 |
| `worker` | 🔴 DOWN (현재) | **5번**에서 활성화 (이미지 업데이트 필요) |

### 1-2. 쿼리 테스트
**http://localhost:9090/graph** 에서 쿼리 입력 후 *Execute*:

```promql
up
```
→ 각 타겟이 `1`(살아있음)/`0`(죽음)으로 표시되면 Prometheus 정상.

vLLM 지표 예시:
```promql
vllm:num_requests_running
vllm:gpu_cache_usage_perc
rate(vllm:request_success_total[5m])
```

---

## 2. vLLM — API 동작 확인

### 2-1. 헬스/모델 목록
```powershell
curl.exe http://localhost:8000/health          # 200
curl.exe http://localhost:8000/v1/models        # 서빙 중 모델 JSON
```

### 2-2. 실제 추론 테스트 (PowerShell)
```powershell
$body = @{
  model    = "Qwen/Qwen2.5-0.5B-Instruct"
  messages = @(@{ role = "user"; content = "한 문장으로 자기소개 해줘" })
} | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:8000/v1/chat/completions `
  -Method Post -ContentType "application/json" -Body $body |
  Select-Object -ExpandProperty choices
```
→ 응답이 오면 vLLM 추론 정상. 이 호출이 `vllm:*` 지표를 증가시켜 Grafana 에서 변화를 볼 수 있습니다.

---

## 3. Grafana — 로그인 & 데이터소스 확인

### 3-1. 로그인
**http://localhost:3000** → `admin` / `changeme` (또는 `.env` 의 `GRAFANA_ADMIN_PASSWORD`).
첫 로그인 시 비밀번호 변경 화면이 나오면 새 비번 설정(또는 *Skip*).

### 3-2. 데이터소스 확인 (자동 구성됨)
좌측 메뉴 **Connections → Data sources** → **Prometheus** 가 이미 등록되어 있고
`http://prometheus:9090`, *default* 표시. 하단 **Save & test** → "Data source is working".

> 이 데이터소스는 [provisioning](../monitoring/grafana/provisioning/datasources/prometheus.yml) 으로
> 자동 주입되므로 수동 추가 불필요합니다.

---

## 4. Grafana — Explore 로 즉시 확인

좌측 **Explore** → 데이터소스 `Prometheus` 선택 → 쿼리 입력 → *Run query*.

```promql
up                                  # 타겟 생존
vllm:num_requests_running           # vLLM 동시 요청
rate(vllm:prompt_tokens_total[5m])  # 초당 프롬프트 토큰
```
그래프가 그려지면 Prometheus → Grafana 파이프라인 정상입니다.

---

## 5. vLLM 대시보드 가져오기 (Import)

1. 좌측 **Dashboards → New → Import**.
2. **grafana.com** 에서 "vLLM" 대시보드를 검색해 ID 입력 (예: 공식/커뮤니티 vLLM 대시보드).
3. 데이터소스로 **Prometheus** 선택 → **Import**.
4. GPU 캐시 사용률, TTFT(첫 토큰 지연), 처리량 패널이 채워집니다.

> 2번 추론 테스트(2-2)를 몇 번 실행하면 패널에 값이 들어옵니다.

---

## 6. 워커 메트릭 활성화 (실제 봇 사용량 모니터링)

> ⚠️ **현재 실행 중인 `:latest` 워커 이미지에는 `/metrics` 엔드포인트가 없습니다.**
> (해당 기능이 추가된 커밋이 아직 레지스트리 이미지에 반영되지 않음)
> 아래로 이미지를 갱신해야 `worker` 타겟이 UP 됩니다.

### 6-1. 이미지 갱신
```powershell
# 1) 코드 푸시 → GitHub Actions 가 새 이미지 빌드·푸시 (Actions 탭에서 통과 확인)
git push origin main

# 2) 새 이미지 pull + 컨테이너 재생성
docker compose -f docker-compose.yml -f docker-compose.registry.yml `
  --profile monitoring --profile vllm pull worker bot
docker compose -f docker-compose.yml -f docker-compose.registry.yml `
  --profile monitoring --profile vllm up -d
```

### 6-2. 활성화 확인
- http://localhost:9090/targets → `worker` 가 🟢 UP.
- Grafana Explore 에서:
```promql
worker_inflight                          # 처리 중 작업 수
worker_queue_size                        # 대기 큐 길이
rate(worker_tasks_total[5m])             # 초당 완료 작업
sum by (status) (worker_tasks_total)     # done/failed 누적
histogram_quantile(0.95, rate(worker_task_duration_seconds_bucket[5m]))  # p95 처리시간
```

### 6-3. 실제 데이터 생성
Telegram 에서 봇에게 작업을 시키면 위 지표가 움직입니다:
```
/task .env 보호 모범사례 3가지 정리해줘
/code app/worker/server.py 보안 점검
/lint
```
→ `worker_inflight` 가 올라갔다 내려가고, `worker_tasks_total{status="done"}` 가 증가.

---

## 7. 자동 프로비저닝된 대시보드

별도로 만들 필요 없이, Grafana 좌측 **Dashboards** → `devops-pipeline` 태그에 3개가 자동 등록됩니다
([provisioning/dashboards](../monitoring/grafana/provisioning/dashboards/)):

| 대시보드 | 내용 | 필요 데이터소스 |
|----------|------|-----------------|
| **DevOps Pipeline — 개요** | 처리율·지연·성공률, 라우트/백엔드별 사용량, Qdrant, vLLM | Prometheus |
| **작업 로그(DB)** | 상태 분포·시간별 처리량·최근 작업 50건 테이블 | Postgres (`--profile postgres`) |
| **시스템 리소스** | 컨테이너 CPU/메모리/네트워크, 호스트 CPU/메모리 | Prometheus (cAdvisor·node-exporter) |

- 라우트/백엔드 사용량 패널은 워커가 `worker_route_total` / `worker_route_duration_seconds`
  지표를 노출합니다(라우트별 작업 수·지연, 백엔드 vLLM/Claude 분해).
- **작업 로그(DB)** 대시보드는 `Postgres` 데이터소스를 쓰므로 `--profile postgres` +
  `.env` 의 `DB_BACKEND=postgres` 로 워커가 같은 DB 를 사용해야 데이터가 채워집니다.
- 대시보드 JSON 을 고치려면 Grafana UI 에서 편집 → *Export* 후 위 경로 파일을 교체하세요.

> Docker Desktop(Windows/Mac)에서 cAdvisor·node-exporter 는 **Linux VM 기준**으로 측정됩니다
> (호스트 Windows 자원이 아님). 컨테이너별 사용량은 정상 표시됩니다.

---

## 8. 트러블슈팅

### vLLM 이 `unhealthy` 로 표시됨
- **대부분 정상입니다.** `curl.exe http://localhost:8000/health` 가 200 이면 서비스는 동작 중.
- 원인: compose 헬스체크가 `python` 명령을 쓰는데 vLLM 이미지 환경에서 해석이 안 되어 체크만 실패. 기능에는 영향 없음.
- 의존 서비스가 vLLM 헬스에 묶여있지 않아 무시해도 됩니다.

### `worker` 타겟이 계속 DOWN
- 6번(이미지 갱신) 미수행 시 정상. 갱신 후에도 DOWN 이면:
  - `docker compose ... logs worker --tail 50` 로 `/metrics` 등록 여부 확인.

### Grafana 패널이 "No data"
- 해당 지표를 만드는 트래픽이 없었던 경우. 2-2(vLLM) 또는 6-3(봇 작업)을 먼저 실행.
- 시간 범위(우상단)를 *Last 15 minutes* 등으로 좁혀 확인.

---

## 9. 정리 / 종료

```powershell
# 중지 (데이터 볼륨 유지)
docker compose -f docker-compose.yml -f docker-compose.registry.yml `
  --profile monitoring --profile vllm down

# 볼륨까지 삭제 (Prometheus/Grafana 데이터 초기화)
docker compose -f docker-compose.yml -f docker-compose.registry.yml `
  --profile monitoring --profile vllm down -v
```
