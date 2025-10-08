from ..library import core, podman
from ..library.osgunittest import BadSkipException, OSGTestCase

TESTIMAGE = "hub.opensciencegrid.org/library/alpine:3"
NAMESPACE = "podman"


def setstate(key, val):
    core.state["%s.%s" % (NAMESPACE, key)] = val


def getstate(key, default=None):
    return core.state.get("%s.%s" % (NAMESPACE, key), default)


class TestInitPodman(OSGTestCase):

    @podman.skip_if_missing
    def setUp(self):  # if podman is missing, skip the whole class
        pass

    def test_00_init(self):
        setstate("pull-ok", None)
        podman.pull(TESTIMAGE)
        setstate("pull-ok", True)

    def test_01_say_hi(self):
        if not getstate("pull-ok"):
            raise BadSkipException("pull failed")
        result = podman.run(TESTIMAGE, "podmantest", command="echo hi", detach=False)
        self.assertEqual("hi\n", result.stdout)
