"""system_commands — mission_pool 시스템 명령 → 실행 argv(순수, 단위테스트 가능).

bashrc 의 AMR 명령을 참고해 매핑(common/robot.env 의 ROBOT_NAMESPACE/DISCOVERY_IP 기준):
  dock        ros2 action send_goal -f /{ns}/dock   irobot_create_msgs/action/Dock   "{}"
  undock      ros2 action send_goal -f /{ns}/undock irobot_create_msgs/action/Undock "{}"
  ros_restart ssh ubuntu@{ip} "sudo systemctl restart turtlebot4.service"   (amr-restart)
  reboot      ssh ubuntu@{ip} "sudo reboot"                                 (amr-reboot)
  shutdown    ssh ubuntu@{ip} "sudo shutdown -h now"   (bashrc 미정의 → reboot 유추)
"""

SYSTEM_ACTIONS = ("shutdown", "reboot", "ros_restart", "dock", "undock")

# dock/undock: 로컬 PC → create3 ROS2 액션. (verb, ActionType)
_ROS_ACTIONS = {
    "dock": ("dock", "Dock"),
    "undock": ("undock", "Undock"),
}

# ros_restart/reboot/shutdown: 로봇(RPi) SSH sudo. (sudo -S 로 비번 stdin 주입)
_SSH_REMOTE = {
    "ros_restart": "sudo -S systemctl restart turtlebot4.service",
    "reboot": "sudo -S reboot",
    "shutdown": "sudo -S shutdown -h now",
}

# 실행기(subprocess) 타임아웃(초) — db_node 워치독보다 짧게(실행기가 먼저 failed 보고).
ACTION_TIMEOUTS = {
    "dock": 100.0,
    "undock": 100.0,
    "ros_restart": 70.0,
    "reboot": 45.0,
    "shutdown": 45.0,
}
DEFAULT_TIMEOUT = 70.0

# reboot/shutdown 은 ssh 연결이 끊겨 255 로 종료될 수 있음 → 성공으로 간주.
DROP_OK_ACTIONS = ("reboot", "shutdown")


def is_valid(action):
    return action in SYSTEM_ACTIONS


def needs_ssh(action):
    return action in _SSH_REMOTE


def build_argv(action, ns, discovery_ip=None, ssh_pass="turtlebot4"):
    """action → subprocess argv(list). 잘못된 action 이면 ValueError."""
    ns = str(ns).strip("/")
    if action in _ROS_ACTIONS:
        verb, act_type = _ROS_ACTIONS[action]
        return ["ros2", "action", "send_goal", "-f",
                f"/{ns}/{verb}", f"irobot_create_msgs/action/{act_type}", "{}"]
    if action in _SSH_REMOTE:
        if not discovery_ip:
            raise ValueError(f"'{action}' requires discovery_ip (robot.env DISCOVERY_IP)")
        # echo <pw> | sudo -S ... : 비번을 stdin 으로 sudo 에 주입(amr-restart/reboot 방식)
        remote = f"echo {ssh_pass} | {_SSH_REMOTE[action]}"
        return ["sshpass", "-p", ssh_pass, "ssh", "-o", "StrictHostKeyChecking=no",
                f"ubuntu@{discovery_ip}", remote]
    raise ValueError(f"unknown action: {action}")


def success_returncodes(action):
    """성공으로 볼 종료코드 집합."""
    return {0, 255} if action in DROP_OK_ACTIONS else {0}
