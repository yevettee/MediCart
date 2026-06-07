#!/bin/bash
# 디스커버리/네임스페이스 단일 설정 source 스크립트.
# 실제 값은 common/robot.env(단일 소스)에 있음 — 로봇 바꿀 땐 robot.env 만 수정.
#
# 사용:  source ~/MediCart/common/discovery.sh   (MediCart standalone 독립 복사본)

_ROBOT_ENV="$(dirname "${BASH_SOURCE[0]}")/robot.env"
set -a; source "${_ROBOT_ENV}"; set +a   # robot.env 의 KEY=VALUE 를 모두 export

source /opt/ros/humble/setup.bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_DOMAIN_ID="${ROBOT_DOMAIN_ID}"

# server ID 만큼 세미콜론 prefix 생성: ID 6 → ";;;;;;IP:11811;"
_ds_prefix="$(printf ';%.0s' $(seq 1 "${DISCOVERY_SERVER_ID}"))"
export ROS_DISCOVERY_SERVER="${_ds_prefix}${DISCOVERY_IP}:11811;"
unset _ds_prefix _ROBOT_ENV

# 대화식 셸은 super client(전체 토픽 가시), 비대화식은 일반 클라이언트
[ -t 0 ] && export ROS_SUPER_CLIENT=True || export ROS_SUPER_CLIENT=False
