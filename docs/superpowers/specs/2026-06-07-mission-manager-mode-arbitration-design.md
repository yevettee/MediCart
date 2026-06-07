# mission_manager 모드 중재 허브 설계

**날짜:** 2026-06-07
**대상:** `medicart_ws/src/mission_manager` 를 **모드 중재 허브**로 확장 — 여러 모드(회진/순찰/지시/가이드/문진 등)의 우선순위 선점·복귀, cmd_vel/Nav2 단독 소유, 외부 모드 노드 enable/disable·status 중재.

## 배경 / 결정

- 무거운 모드(추종·순찰 등)는 **별개 패키지 노드**(nurse_tracker 등)로 동작. mission_manager는 **중재 허브**(우선순위 중재 + cmd_vel 게이트 + 외부 노드 enable/disable)만 담당 — 모드 행동 로직은 보유하지 않음.
- 중재 코어는 intel1 `ward_robot`(mode_manager_node·control·mode_base)에 검증된 패턴을 **적응 포팅**. 단, intel1은 모드를 in-process로 뒀고 여기서는 **외부 노드 + 경량 토픽 계약**으로 바꾼다.
- 계약 방식 = **경량 토픽(String-JSON/Bool/Twist) + cmd_vel 게이트**(검토된 대안: ROS2 lifecycle, twist_mux — 둘 다 중재 로직을 별도 구현해야 하고 의존↑이라 미채택).

## 아키텍처

```
web ─(mission_pool)→ db_bridge ─/{ns}/mission_request→ mission_manager(HUB)
                                                         · arbitrate(우선순위)
                                                         · cmd_vel 게이트(safety)
                                                         · 외부 모드 enable/disable
        /{ns}/mode/<m>/set(Bool/JSON) │   ▲ /{ns}/mode/<m>/status(JSON)
        /{ns}/mode/<m>/cmd_vel(Twist) ▲   │
   ┌──────────────┬───────────────────┴───┴───────────┐
 nurse_tracker(round, REACTIVE)   patrol/errand/guide/intake(NAV)  … 각자 패키지
        └ cmd_vel 후보→허브 게이트         └ Nav2 주행(cmd_vel 직접 소유)
허브 → /{ns}/robot_mode(String) → (intel1 ward_bridge가 RTDB state.mode 중계)
```

우선순위(높을수록 선점): **mapping6 > 문진(intake)5 > 회진(round)4 > 지시(errand)3 > 가이드(guide)2 > 순찰(patrol)1 > idle0**.

## 모드 계약 (모드 이름 `<m>` 마다)

| 토픽 | 타입 | 방향 | 내용 |
|---|---|---|---|
| `/{ns}/mode/<m>/set` | std_msgs/String(JSON) | 허브→모드 | `{"active":bool,"params":{}}` — 활성/비활성 + 시작 파라미터 |
| `/{ns}/mode/<m>/status` | std_msgs/String(JSON) | 모드→허브 | `{"state":"running\|done\|failed\|lost","detail":str,"ts":int}` |
| `/{ns}/mode/<m>/cmd_vel` | geometry_msgs/Twist | 모드→허브 | 속도 후보 (**REACTIVE 모드만**) |

- **REACTIVE**: 후보 cmd_vel을 허브가 *활성 모드것만* `safety_gate` 통과 후 `/{ns}/cmd_vel` 로 중계. 후보가 stale(최근 미수신)이면 0 발행.
- **NAV**: 모드가 Nav2(BasicNavigator)로 주행 → Nav2가 `/{ns}/cmd_vel` 소유. 허브는 NAV 활성 시 cmd_vel 미발행. `active:false` 수신 시 모드가 Nav2 cancel.
- actuation 종류는 허브 레지스트리에서 관리: `{round:reactive, patrol:nav, errand:nav, guide:nav, intake:nav}` (mapping 특수 — 후속).

## 허브 동작 (control_hz = 10Hz 타이머)

1. **mission_request 2-lane 라우팅**: 시스템 액션(dock/undock/ros_restart/reboot/shutdown) → 기존 `MissionExecutor`. **모드 액션(start/stop/clear + mode) → `ModeArbiter`**. 둘 다 `/{ns}/mission_feedback` 응답(db_bridge가 mission_pool 정리). 모드 start는 "활성화 수락=done"으로 즉시 응답하고 모드는 계속 구동(연속 모드).
2. **중재**: `mode = arbitrate(_active)`.
3. **선점/복귀 전환**(`mode != _current`): old 모드 `set(active=false)` → zero twist 1회 → new 모드 `set(active=true, params)` → `_current=mode`. (복귀: 저우선 모드가 _active에 남아 있으면 고우선 종료 후 자동 재활성 → 그때 모드 노드가 현재 단계부터 재개.)
4. **actuation**: 활성 REACTIVE → 캐시 cmd_vel(없/stale=0) → safety_gate → `/{ns}/cmd_vel`. 활성 NAV/idle → 허브 미발행(idle은 0 정지).
5. **워치독**(db_node 패턴 재사용): 활성 모드 status가 `status_timeout`(예 3s) 무응답 → `lost` 간주 → abort(_active에서 제거) → 다음 모드. 무한대기 방지.
6. **상태 출력**: 현재 모드 → `/{ns}/robot_mode`(String). (intel1 ward_bridge가 RTDB `state.mode` 로 중계 — 기존 파이프라인.)

## 안전 입력

허브가 `/{ns}/scan`(LaserScan) 구독 → 정면/좌/우 clearance 계산(intel1 `_on_scan` 재사용) → REACTIVE `safety_gate`(정면 LiDAR < 0.30m 시 전진 차단; depth 게이트는 후속). 회전·후진은 허용.

## 파일 (mission_manager 패키지)

- **신규** `mode_arbitration.py` (순수) — `MODE_PRIORITY`, `arbitrate(active)`, `SafetyParams`/`safety_gate`. intel1 control.py에서 해당 부분 포팅.
- **신규** `mode_proxy.py` — `ModeProxy(name, actuation)`: `set(active,params)` 발행, `/cmd_vel` 후보 캐시(+수신시각), `/status` 구독(+최근시각), `latest_twist()`, `is_stale(now,timeout)`, `last_status`.
- **신규** `mode_arbiter.py` — `ModeArbiter`: 모드 레지스트리(proxy 생성), `_active` 집합·`apply(action,mode,params)`, `tick(now, clearance, scan_inputs)` → 전환 lifecycle + cmd_vel 게이트 결과(Twist|None) + 현재 모드, 워치독.
- **수정** `mission_manager_node.py` — ModeArbiter 결선, 모드 레지스트리 파라미터, `/{ns}/scan` 구독, `/{ns}/cmd_vel`·`/{ns}/robot_mode` 발행, control 타이머. mission_request 핸들러에서 시스템 액션/모드 액션 분기. (기존 patrol state_machine·StartPatrol 서비스는 보존하되 모드 경로와 독립.)
- **신규** `test/test_mode_arbitration.py` — arbitrate(빈집합→idle, 선점, 미지원 제외), 우선순위 순서, safety_gate(정면 막힘 전진0·회전유지) 단위테스트.
- **신규** `mission_manager/stub_mode_node.py` (참조/테스트용 더미 REACTIVE 모드) + setup.py 엔트리 `stub_mode_node` — active 시 소twist + status running 발행. 계약 E2E 검증용.

## 검증

- 단위: `python3 -m pytest test/test_mode_arbitration.py` — arbitrate/safety_gate 통과.
- 빌드: `colcon build --packages-select mission_manager` 성공, 노드 import.
- E2E(로봇 없이, 더미 모드): 허브 + stub_mode 2개(우선순위 다르게) 띄움 →
  1) mission_request `start <low>` → 해당 모드 set(active=true), `/cmd_vel` 에 게이트된 후보 흐름.
  2) `start <high>` → 선점(low active=false, high active=true), `/cmd_vel` 이 high 후보로 전환.
  3) `stop <high>` → low 복귀(active=true 재송신).
  4) high status 끊기 → 워치독 lost → abort → 다음.
  5) `/{ns}/robot_mode` 가 현재 모드 반영.

## 범위 밖 (후속 spec)

- 실제 모드 노드: nurse_tracker(round, REACTIVE), patrol/errand/guide/intake(NAV), mapping.
- 웹 `/control`·백엔드 mission whitelist에 모드 명령(start round 등) 확장(소규모).
- depth 기반 safety 게이트 입력(OAK-D front depth).
- 복귀 시 모드 내부 "현재 단계 재개"는 각 모드 노드 책임(계약상 active=true 재수신 시 이어서).
