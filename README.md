# 업무 규칙 기반 API 검증 누락 탐지 Agent

기존 실습과 같은 Python/FastAPI · LangGraph · MCP · Vue(CDN) 구성을 사용한 독립 프로젝트입니다.
실제 Ollama 모델이 다음 조사 도구를 선택하고 관찰 결과에 따라 재조사/테스트/종료를 결정합니다.

## 실행

Ollama를 실행하고 `ollama list`에 `qwen3:8b`가 있는지 확인합니다. 없으면 `ollama pull qwen3:8b`로 준비합니다.

```bash
cd api_gap_agent
bash sh/run.sh
```

브라우저: http://127.0.0.1:8200
기존 예제의 8100/8600 포트와 겹치지 않습니다. 화면도 FastAPI가 제공하므로 별도 프록시가 필요하지 않습니다.
최초 실행 시 폴더 안의 `.venv`에 의존성을 설치합니다. 정확한 검증 버전은 `requirements.lock.txt`에 있습니다.
설정을 바꾸려면 `.env.example`을 `.env`로 복사하여 모델명 등을 조정합니다. OpenAI API 키는 사용하지 않습니다.
모델은 로컬에서 실행되며 화면 라이브러리(Vue/Tailwind/daisyUI)는 CDN 인터넷 연결이 필요합니다.
`qwen3:8b`는 조사 횟수와 하드웨어에 따라 수 분이 걸릴 수 있습니다.

## 실행 흐름

1. 주문 생성/조회/취소 중 분석 범위와 평가 환경을 선택합니다.
2. 모델이 규칙·스키마·기존 테스트 조사 도구를 선택합니다.
3. 공통 테스트까지 읽어 이미 검증하는 항목과 누락 후보를 구분하고, 테스트 실행 전 기존 검증 판정을 저장합니다.
4. 모델이 누락 후보의 HTTP 요청/기대값을 구조화하여 제안합니다.
5. 도구가 입력을 검증하고 Python 테스트로 변환하여 별도 pytest 프로세스에서 실행합니다.
6. 모델이 관찰 결과를 보고 실행 해석을 수정하거나 최종 결과를 제출합니다. 새 테스트의 통과가 기존 누락 판정을 바꾸지 않도록 분리합니다.
7. 보고서, 조사 기록, 생성 코드, 실행 관찰을 `outputs/<run_id>/`에 저장합니다.

`decide → execute → decide` 루프를 LangGraph로 구현했습니다. 고정된 코드가 조사 순서를 지정하지 않습니다.
전체 자료를 반환하는 검색은 성공 후 반복 선택에서 제외하고, 미조회 명세·미열람 파일·실행한 후보를 상태 요약으로 전달합니다. 나머지 행동의 선택은 모델이 수행합니다.
최대 24회 판단 및 약 10분 예산을 기본으로 사용합니다(모델 호출 중에는 개별 180초 타임아웃 적용).
한도 도달 시 `incomplete`로 보고하며 완전 분석으로 평가하지 않습니다.
구조적 종료 검사는 조사 파일 읽기와 실행 여부를 확인합니다. 인용의 의미와 진단의 정확성을 보장하지 않으므로 평가가 별도로 필요합니다.

## 데이터와 세 가지 평가 환경

| 환경 | 기존 테스트 | 구현 |
|---|---|---|
| healthy | 수량 경계값, 배송 후 취소 검증 누락 | 정상 |
| buggy | healthy와 동일 | 배송 후 취소를 허용하는 의도적 결함 |
| covered | 경계값·배송 취소 검증도 존재 | 정상 |

실제 기존 테스트에는 공통 파일의 타인 주문 조회 거절 검증이 있습니다. 이를 추가 조사로 찾아 중복 제안을 피해야 합니다.
각 실행은 새 앱/주문 데이터를 사용합니다. 실제 운영 API는 호출하지 않습니다.
업무 규칙의 기대값과 실행 준비 조건은 `data/`에서 확인할 수 있습니다.

## 평가 및 테스트

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest sample_service/tests -q
bash sh/evaluate.sh --variant healthy
bash sh/evaluate.sh --variant buggy
bash sh/evaluate.sh --variant covered
```

`evaluate.sh`는 실제 Ollama 모델을 호출합니다. 서버의 분석과 동시에 실행하지 않는 것이 좋습니다.
정답은 `evaluation/ground_truth.json`이며 MCP의 파일 접근 대상에는 포함되지 않습니다.
covered 구성에 추가되는 테스트 코드만 기존 테스트 자료로 노출됩니다.
평가 결과는 실행 폴더의 `metrics.json`에 저장됩니다.
누락 precision/recall, 잘못된 누락/결함 제안, 결함 recall, 후보 실행 가능 비율, 판단 횟수, 토큰 수, 시간을 측정합니다.
후보 실행 가능 비율은 pytest가 통과 또는 검증문 실패까지 도달한 비율이며, 테스트의 의미가 올바르다는 자동 보장은 아닙니다.
분모가 0인 지표는 `null`이며 성공률 100%로 처리하지 않습니다.

테스트 누락과 구현 결함은 별개입니다. 새 테스트가 통과해도 기존 검증은 누락일 수 있습니다.
실패한 테스트도 올바르게 결함을 발견한 결과일 수 있습니다.
현재 평가는 고정된 소규모 평가 사례이며, 일반 프로젝트 탐지 정확도를 의미하지 않습니다.
고정 파이프라인 대비 성능 비교, 다양한 문서/테스트 형식, 반복 실행 통계는 후속 작업입니다.

## 주요 파일

- `server.py`: 분석 시작/조회, SSE, 화면, 실행 기록
- `agent/graph.py`: 자율 도구 선택 루프와 종료 조건
- `agent/llm.py`: Ollama JSON 구조화 출력
- `agent/prompts.py`: 규칙 비교와 결과 해석 지침
- `agent/mcp_client.py`, `mcp_server.py`: 실제 stdio MCP 연결
- `tools/repository.py`: 규칙/명세/허용된 기존 테스트 조회
- `tools/runner.py`: 구조화 시나리오 검증·코드 생성·pytest 실행
- `sample_service/`: API 3개와 기존 테스트
- `evaluation/`: 평가용 정답과 측정 코드
- `tests/`: Agent 시스템 및 도구 검증

## 결과 읽기

- `coverage`: missing / covered / uncertain
- `implementation`: conforms / violates / unknown
- 테스트 실행: passed / assertion_failed / execution_error
- 분석 종료: completed / incomplete / error

이 첫 버전은 미리 정한 세 규칙과 세 API를 대상으로 합니다.
규칙별 후보 형식 검증에는 기대 경계값/상태 검증 조건이 포함되어 있습니다.
이는 잘못 생성된 후보를 실행 전에 거절하기 위한 장치이며, 임의의 규칙을 자동 해석하는 범용 검증기는 아닙니다.
모델이 자유 Python 코드를 생성해 실행하는 기능은 없습니다. 검증된 JSON 요청을 고정 템플릿으로 변환합니다.
별도 pytest 프로세스와 초기화 앱은 재현을 위한 실행 분리이며 OS 보안 샌드박스는 아닙니다.

## 실제 모델 실행 기록

첫 실제 평가와 알려진 권한 검증 오탐은 [doc/first_run.md](doc/first_run.md)에 기록했습니다.
현재는 소규모 주문 서비스용 첫 버전이며, 생성 결과와 근거는 사람이 검토해야 합니다.

## 개발 진행 보고서

[2026-10-20 개발 진행 보고서](doc/progress_report_2026-10-20.md)에 설계, 구현 내용, 실제 평가와 남은 한계를 정리했습니다.
