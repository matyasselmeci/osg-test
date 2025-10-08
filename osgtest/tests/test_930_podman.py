from ..library import podman
from ..library.osgunittest import OSGTestCase


class TestCleanupPodman(OSGTestCase):
    @podman.skip_if_missing
    def setUp(self):  # if podman is missing, skip the whole class
        pass

    def test_00_cleanup(self):
        podman.cleanup()
