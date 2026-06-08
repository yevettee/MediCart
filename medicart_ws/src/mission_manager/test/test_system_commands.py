"""system_commands 순수 로직 테스트(ROS 무관).

실행: cd mission_manager && python3 -m pytest test/test_system_commands.py -v
"""
import pytest

from mission_manager.system_commands import (build_argv, is_valid, needs_ssh,
                                              success_returncodes,
                                              SYSTEM_ACTIONS)


def test_is_valid_whitelist():
    for a in ("shutdown", "reboot", "ros_restart", "dock", "undock"):
        assert is_valid(a)
    assert not is_valid("rm-rf")
    assert not is_valid("")
    assert set(SYSTEM_ACTIONS) == {"shutdown", "reboot", "ros_restart", "dock", "undock"}


def test_build_argv_dock_undock_ros_action():
    argv = build_argv("dock", "robot6")
    assert argv == ["ros2", "action", "send_goal", "-f",
                    "/robot6/dock", "irobot_create_msgs/action/Dock", "{}"]
    argv = build_argv("undock", "/robot3/")          # 슬래시 정제
    assert argv[4] == "/robot3/undock"
    assert argv[5] == "irobot_create_msgs/action/Undock"


def test_build_argv_ssh_commands():
    argv = build_argv("ros_restart", "robot6", discovery_ip="192.168.109.106", ssh_pass="turtlebot4")
    assert argv[0] == "sshpass" and "ssh" in argv
    assert "ubuntu@192.168.109.106" in argv
    assert "systemctl restart turtlebot4.service" in argv[-1]
    assert build_argv("reboot", "robot6", "1.2.3.4")[-1].endswith("sudo -S reboot")
    assert build_argv("shutdown", "robot6", "1.2.3.4")[-1].endswith("sudo -S shutdown -h now")


def test_build_argv_ssh_requires_ip():
    with pytest.raises(ValueError):
        build_argv("reboot", "robot6", discovery_ip="")


def test_build_argv_unknown_raises():
    with pytest.raises(ValueError):
        build_argv("explode", "robot6")


def test_needs_ssh_and_success_codes():
    assert needs_ssh("reboot") and needs_ssh("ros_restart") and needs_ssh("shutdown")
    assert not needs_ssh("dock")
    assert success_returncodes("dock") == {0}
    assert success_returncodes("reboot") == {0, 255}     # ssh 연결 끊김 허용
    assert success_returncodes("shutdown") == {0, 255}
