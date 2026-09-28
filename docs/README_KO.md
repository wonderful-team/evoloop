<p align="center">
  <img src="https://www.evoloop.cn/assets/images/WoodenRobot.png" alt="EvoLoop" width="120" />
</p>
<p align="center"><b>EvoLoop Agent - 자율 당직 에이전트, 태스크 편성 가능, 야근 전문</b></p>

<p align="center">
  <img src="https://img.shields.io/github/stars/wonderful-team/evoloop" alt="GitHub stars" />
  <img src="https://img.shields.io/github/v/release/wonderful-team/evoloop" alt="GitHub release" />
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT" />
  <a href="https://github.com/wonderful-team/evoloop/wiki"><img src="https://img.shields.io/badge/Docs-Wiki-blue" alt="Docs" /></a>
</p>

<p align="center">
  <a href="https://github.com/wonderful-team/evoloop/releases">Releases</a> &nbsp;·&nbsp;
  <a href="https://www.evoloop.cn">Website</a> &nbsp;·&nbsp;
  <a href="https://www.evoloop.cn/agent">Try Online</a> &nbsp;·&nbsp;
  <a href="https://github.com/wonderful-team/evoloop/issues">Issues</a>
</p>

<p align="center">
  <a href="README_EN.md">English</a> | <a href="README_CN.md">中文</a> | <a href="README_JA.md">日本語</a> | <a href="README_KO.md">한국어</a>
</p>

---

EvoLoop은 **태스크 편성이 가능한 자율 당직 에이전트**입니다. 에이전트 내부에 삼권 소통 메커니즘 — **의사결정자, 실행자, 심사감찰자** — 을 두어 태스크의 모든 항목이 확실하게 이행되도록 합니다.

Agent를 쓰다 보면 이런 경험 있으신가요: 장기 태스크 계획은 완벽해 보이는데, SKILL 제약이 있어도 실제 실행은 **불완전하고, 뒤끝이 남고, 심지어 방향을 이탈** — 반복해서 검사하고, 몇 판씩 소통하면서 고쳐야만 했던 경험 말입니다.

EvoLoop은 바로 이 문제를 해결하기 위해 새롭게 **당직식 태스크 시스템**을 설계했습니다: 태스크는 시간이 되면 자동 실행, 매 단계 진행률을 실시간 기록. 완료 후에는 **심사감찰자**가 당신의 입장에서 검증합니다 — 실행자의 "다 했습니다"는 통하지 않고, 불완전하면 되돌려 재작업. 자금과 불가역 작업은 **의사결정자**(당신)가 결재합니다. 당신은 태스크를 계획하고 결과를 검수하기만 하면 됩니다.

웹, 데스크톱, 모바일 3단말 커버, 웨이크워드 기반 자연어 음성 대화 지원.

🌐 공식 사이트 [evoloop.cn](https://evoloop.cn) · 💻 [GitHub](https://github.com/wonderful-team/evoloop)

---

## 🎬 제품 데모

<table>
  <tr>
    <td valign="top">
      <img src="images/evoloop-ui.png" alt="EvoLoop Desktop" height="500" />
      <p align="center"><em>Desktop</em></p>
    </td>
    <td valign="top">
      <img src="images/evoloop-mobile.jpg" alt="EvoLoop Mobile" height="500" />
      <p align="center"><em>Mobile</em></p>
    </td>
  </tr>
<tr>
<td colspan="2" align="center">
<img src="images/evoloop-duty.png" alt="EvoLoop Duty" height="500" />
<p align="center"><em>Duty</em></p>

<img src="images/evoloop-duty-2.png" alt="EvoLoop Duty" height="500" />
<p align="center"><em>Duty HITL</em></p>
</td>
</tr>
</table>

**EvoLoop 전체 기능 데모**

https://www.evoloop.cn/assets/video/demo.mp4

**당직 태스크 시스템 데모 1**

https://www.evoloop.cn/assets/video/duty1.webm

**당직 태스크 시스템 데모 2**

https://www.evoloop.cn/assets/video/duty2.webm

---

## 🏗 시스템 아키텍처

<p><img src="images/arch.png" alt="EvoLoop Architecture" /></p>

| 계층 | 구성 |
|------|------|
| 클라이언트 | Web(React + Vite), 데스크톱(Tauri + Rust 음성 파이프라인), 모바일(React Native, 원격 결재/검수 지원) |
| 서비스 | FastAPI: REST + SSE + 음성 WebSocket 채널 |
| 엔진 | [OpenHands](https://github.com/All-Hands-AI/OpenHands) SDK 기반 Agent 엔진: 계획 → 도구 실행 → 구조화 셀프 체크 → 의심되면 중단하고 질문 |
| 라우팅 | 명령 분류: 일반 명령 즉시 실행, 불확실한 것만 Agent에게 위임 |
| 당직 | 태스크 큐 + Supervisor 스케줄링: 기한 실행, 크래시 수렴, 서킷 브레이커 가드레일 |
| 확장 | MCP 도구 서비스, 능력 팩(SOP), 런타임 도구 생성, 매크로 엔진(결정론적 리플레이 + 자가 치유) |
| 데이터 | 데스크톱 내장(SQLite + LanceDB, 데이터는 머신 밖으로 나가지 않음) / SaaS 서버(PostgreSQL + Redis) |

---

## ⏱ 당직 태스크 시스템 (Autonomous Duty)

### 어떤 문제를 해결하는가

LLM은 요구사항을 **불완전하게 이행하거나 부분적으로 이탈**합니다 — 장기 태스크를 절반쯤 진행하면 컨텍스트가 소음에 잠겨 썩고, 모델은 지쳐 조기 종료하며, 완료를 허위 보고하고, 정면 답변을 회피하고, 산출물은 목표에서 표류합니다. 결국 당신은 **반복 검사와 여러 판의 소통**으로 수정해야 하고, 실행 디테일에 끌려 들어갑니다.

당직 태스크 시스템은 바로 이 수정 비용을 없애기 위해 설계되었습니다: 태스크 생성 시 시나리오·목표·검수 기준을 먼저 명확히 합니다. 실행 상태는 전량 영속화되어 중단 후 이어서 재개합니다. 완료 후에는 결과를 **당신의 명의로 최초 요청 대화에 되돌려**, 당초 당신의 요구를 이해했던 Agent가 당신의 입장에서 검증합니다 — 실행자의 입에서 나온 "완료"는 통하지 않고, 되돌림 2회를 넘기면 인간 중재로 에스컬레이션합니다.

### 목표

Agent가 비즈니스를 장기적으로 안정적으로 운영하게 만드는 것: 요구는 한 번만 말하고, 수정은 제도에 맡깁니다. 사람은 결재·검수·중재 세 순간에만 등장합니다.

### 태스크 실행 플로우

<p><img src="images/duty-workflow.png" alt="Duty Workflow" height="500" /></p>

### 적합한 시나리오

- **이커머스 / 리테일 운영 위탁**: 선정 리서치 → 가격 책정 → 상장 → 일일 순찰(품절·악평·이상 주문) — 첫 파일럿 시나리오는 "몰 한 곳 접수"
- **콘텐츠·그로스 파이프라인**: 기획 → 집필 → 소재 제작 → 멀티 플랫폼 발행 → 집행 회고, 단계마다 흔적·검수
- **데이터·순찰 봇**: 경영 일보, 재고 / 자금 / 지표 정기 순찰, 이상 발생 시 즉시 알림·즉시 제안
- **서드파티 이벤트 지속 응답**: 주문·티켓·심사 메시지 자동 큐잉 처리, 전 과정 감사 가능
- **기업 백오피스 SOP**: 승인 보조, 대사, 재고 실사 등 반복 가능·검수 가능한 프로세스
- **R&D 프로젝트 집사**: 코드베이스 순찰, 의존성 보안 점검, 백업 검증, 백로그 정리
- **고객 서비스 응대**: 기업위챗 / 위챗 고객센터 순찰 자동 응대, 자금 관련은 인간에게 에스컬레이션
- **눈 떼고 방치**: 7×24 당직 루프, 사람은 결재·검수·중재 세 순간에만 등장

접수 대상을 교체(몰 → CRM → 공급망 → 콘텐츠 사이트)할 때는 능력 팩과 태스크 데이터만 바꾸면 되고, 스케줄링·실행 계층은 제로 변경입니다.

### 워크벤치

무한 캔버스를 메인 뷰로: 이종 산출물 카드 + 의존성 라인, 시각 포커스가 Agent의 현재 노드를 자동 추적. 결재 / 검수 / 심사 카드는 노드 안에 내장. 언제든 세 가지 질문에 답할 수 있습니다 — **Agent가 지금 뭘 하는가, 이전에 뭘 했는가, 다음에 뭘 할 것인가**.

---

## 🌟 주요 기능

| 기능 | 설명 |
|---|---|
| **장시간 실행** | 단일 태스크 300+ 연속 스텝, 수시간 안정 실행, 자동 오류 복구 |
| **크로스 디바이스 A2A 협업** | 디바이스 간 에이전트가 비동기로 발견·위임·결과 반환 |
| **당직 실행** | 태스크는 기한이 되면 자동 큐잉·실행, 매 단계 진행률 실시간 기록, 완료 시 검증 가능한 증거 첨부. 실행자의 "완료"는 통하지 않음 — 결과는 당신의 명의로 요청 원래 대화에 되돌려져 심사감찰자가 "제대로 했는가"를 검증. 자금과 불가역 작업은 반드시 사람 결재 대기 |
| **모방 학습** | 당신이 한 번 시연하면 한 세트 습득 — 마우스 클릭 과정은 궤적을 기록하고, 녹화 영상은 프레임 단위로 이해하여 재사용 가능한 스킬·'매크로'로 증류. 이후 같은 일은 기계적으로 재실행하며 연산을 태우지 않음. 환경 변화 시 자동으로 AI에 반환해 방법을 강구. AI가 자체 작성한 플로우는 실측 통과 후에만 가동 허가 |
| **수시 호출** | 음성, 웹, 기업위챗 / 위챗 고객센터, 모바일 — 어디서 오든 동등하게 취급. 일반 명령은 LLM을 깨우지 않고 초 단위 처리, 불명확하거나 복잡한 것만 AI가 신중히 사고 |
| **음성 대화** | "你好Evo" 한마디면 대화 시작, 말하는 중 끼어들기와 받아쓰기 대필 가능, 음성은 기기를 벗어나지 않음 |
| **대신 손쓰기** | 이미 가진 기기 위에서 작업 — 브라우저의 웹페이지, 데스크톱 앱, Android / iOS / HarmonyOS 폰. PC 앞을 비워도 폰으로 결재·검수 |
| **도움 요청(A2A)** | 이 머신의 Agent는 당신의 다른 기기 Agent에게 일을 넘길 수 있음 — 위임 중에는 메인 플로가 자동 대기하고, 결과가 돌아오면 즉시 재개. 위임 전 과정이 UI에 실시간 표시 |
| **안전 퓨즈** | 확신이 없으면 멈추고 물어봄, 결코 답을 꾸며내지 않음. 위험 조작은 권한 게이트로 차단, 비밀키는 출력에 노출되지 않음, 제자리 맴돌이 루프는 결단적으로 차단 |
| **생태계 연결** | 외부 도구는 MCP 프로토콜로 수시 접속·해제. 업무 지식은 능력 팩으로 필요에 따라 조립 — 오늘은 몰을 접수, 내일은 다른 시스템으로 교체, 코어 코드 변경 없음 |

---

## 🚀 설치 및 배포

EvoLoop은 세 가지 배포 형태를 제공합니다. 용도에 맞게 선택하세요.

| 모드 | 시나리오 | 스택 | 설정 파일 |
|---|---|---|---|
| **데스크톱 내장** | 개인 PC·로컬 사용 | SQLite + LanceDB + Huey | `.env.prod.desktop` |
| **웹 단일 사용자** | 개인 서버 | SQLite + LanceDB + Huey | `.env.prod.web.single` |
| **웹 다중 사용자** | 팀 / 엔터프라이즈 프로덕션 | PostgreSQL + Redis + Meilisearch + Neo4j + Celery | `.env.prod.web.multi` |

### 데스크톱 내장 모드(개인 PC, 외부 의존성 제로)

백엔드에 SQLite + LanceDB + Huey 내장. 데스크톱 앱과 함께 단독 기동하며 데이터는 머신 밖으로 나가지 않습니다:

```bash
# 저장소 클론
git clone https://github.com/wonderful-team/evoloop.git
cd evoloop

# 백엔드: 의존성 설치 + 원커맨드 기동
cd backend
./bin/evo install
cp .env.prod.desktop .env      # LLM API Key 입력
./bin/evo start                # API + Worker 동시 기동(evo stop 으로 중지)

# 데스크톱(Tauri, 음성 웨이크 포함. 백엔드는 sidecar 로 동봉 기동)
cd frontend
npm install
npm run tauri dev
```

### 웹 단일 사용자 모드(개인 서버)

```bash
cd backend
cp .env.prod.web.single .env
./bin/evo start
```

### 웹 다중 사용자 모드(팀 / 엔터프라이즈 프로덕션)

```bash
cd backend
cp .env.prod.web.multi .env
# PostgreSQL / Redis / Meilisearch / Neo4j 구성, 또는 ./bin/evo install full
./bin/evo start
```

`evo` 명령어 요약: `evo start / stop / status / logs` 서비스 관리, `evo test` 테스트, `evo check` 코드 점검 — 전체 목록은 `./bin/evo help`.

---

## 📦 빌드 및 릴리스

```bash
# 데스크톱 패키징
./deploy/build.sh macos-arm64 --env-file=.env.prod.desktop
./deploy/build.sh macos-x86_64 --env-file=.env.prod.desktop

# 모바일 패키징(Android APK / AAB, iOS, HarmonyOS HAP)
./deploy/build.sh android --env-file=.env.prod.desktop   # APK. Google Play 는 --aab
./deploy/build.sh ios --env-file=.env.prod.desktop
./deploy/build.sh harmony --env-file=.env.prod.desktop
./deploy/build.sh mobile --env-file=.env.prod.desktop    # 3 플랫폼 일괄 빌드

# 웹 정적 애셋 빌드
./deploy/build.sh web --env-file=.env.prod.web.multi

# 모델 다운로드
./deploy/download_models.sh --models nomic-embed,paraformer-zh
```

---

## 🤝 협력과 공건

Agent 관련 커스터마이징 및 현장 적용 협력을 수주하고 있습니다.

기업 생산, 운영, 마케팅, 투자 리서치, 데이터 처리, 콘텐츠 처리 등 업무 프로세스에서 Agent 자동화를 원하는 부분이 있다면 위챗으로 연락해 주세요.

방안이 이미 정리되어 있지 않아도 됩니다. 실제 프로세스, 실제 문제, 실제 니즈만 있다면 Agent로 해결할 수 있는지, 어떻게 할지 함께 판단해 드립니다.

친구 추가 시 비고: **업무 + Agent에게 뭘 도와주길 원하는지**

**본 프로젝트에 관심 있는 분들의 참여와 공동 교류·구축도 환영합니다** — 요구 제기, 버그 보고, 코드 기여, 활용 공유, 무엇이든 이 생태계의 건설자입니다.

Builder도 환영합니다. 비고: **Builder + 지금 하고 있는 일**

- **공식 사이트**: [evoloop.cn](https://evoloop.cn)
- **GitHub**: [wonderful-team/evoloop](https://github.com/wonderful-team/evoloop)
- **Issues**: [GitHub Issues](https://github.com/wonderful-team/evoloop/issues)
- **이메일**: [wonderful@develop-assistant.cn](mailto:wonderful@develop-assistant.cn)
- **위챗**: QR 코드로 연락 가능

<p align="center">
  <img src="images/wechat.png" alt="EvoLoop WeChat" width="200" />
</p>

---

<p align="center">
  <b>Built with ❤️ by EvoLoop Team</b>
</p>
