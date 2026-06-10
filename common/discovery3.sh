#!/bin/bash
# robot3 전용 디스커버리 설정 — robot6 세팅(discovery.sh / robot.env)을 건드리지 않고
# robot3 환경이 필요한 터미널에서만 source 해서 쓴다.
#
# 사용:  source ~/MediCart/common/discovery3.sh
#         (scenario A 실행 전 discovery.sh 대신 이걸 source)

_ROBOT_ENV="$(dirname "${BASH_SOURCE[0]}")/robot3.env"
set -a; source "${_ROBOT_ENV}"; set +a

source /opt/ros/humble/setup.bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_DOMAIN_ID="${ROBOT_DOMAIN_ID}"

_ds_prefix="$(printf ';%.0s' $(seq 1 "${DISCOVERY_SERVER_ID}"))"
export ROS_DISCOVERY_SERVER="${_ds_prefix}${DISCOVERY_IP}:11811;"
unset _ds_prefix _ROBOT_ENV

[ -t 0 ] && export ROS_SUPER_CLIENT=True || export ROS_SUPER_CLIENT=False
