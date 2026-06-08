import math


def test_pose_stamped_fields_zero_yaw():
    from mission_manager.nav_executor import pose_stamped_fields
    f = pose_stamped_fields(1.5, -2.0, 0.0)
    assert f["frame_id"] == "map"
    assert f["x"] == 1.5 and f["y"] == -2.0
    assert abs(f["qz"] - 0.0) < 1e-9 and abs(f["qw"] - 1.0) < 1e-9


def test_pose_stamped_fields_half_pi_yaw():
    from mission_manager.nav_executor import pose_stamped_fields
    f = pose_stamped_fields(0.0, 0.0, math.pi / 2)
    assert abs(f["qz"] - math.sin(math.pi / 4)) < 1e-9
    assert abs(f["qw"] - math.cos(math.pi / 4)) < 1e-9
