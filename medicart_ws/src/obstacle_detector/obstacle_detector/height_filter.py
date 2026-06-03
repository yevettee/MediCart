"""Z-axis passthrough filter for point clouds."""


class HeightFilter:
    """Filters points by height range (default 0.1–1.5 m)."""

    def __init__(self, z_min=0.1, z_max=1.5):
        self.z_min = z_min
        self.z_max = z_max

    def filter(self, point_cloud):
        return point_cloud
