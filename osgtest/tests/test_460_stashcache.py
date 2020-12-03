import os
import pwd
import random
import tempfile

from osgtest.library import core
from osgtest.library import files
from osgtest.library.osgunittest import OSGTestCase
from osgtest.library import service
try:
    from urllib2 import urlopen
except ImportError:
    from urllib.request import urlopen


NAMESPACE = "stashcache"

def getcfg(key):
    return core.config["%s.%s" % (NAMESPACE, key)]


# TODO Work with authed origin/cache as well.  A separate class would probably be the best.
class TestStashCache(OSGTestCase):
    # testfiles with random contents
    testfiles = [
        ("testfile%d" % x, str(random.randint(1000000, 9999999)) + "\n")
        for x in range(4)
    ]

    def assertCached(self, name, contents, auth=False):
        fpath = os.path.join(getcfg("CacheRootdir"), getcfg("OriginExport").lstrip("/"), name)
        self.assertTrue(os.path.exists(fpath),
                        name + " not cached")
        self.assertEqualVerbose(actual=core.to_str(files.read(fpath, as_single_string=True)),
                                expected=contents,
                                message="cached file %s mismatch" % name)

    def skip_bad_unless_running(self, *services):
        for svc in services:
            self.skip_bad_unless(service.is_running(svc), "%s not running" % svc)

    @core.elrelease(7,8)
    def setUp(self):
        core.skip_ok_unless_installed("stash-origin",
                                      "stash-cache",
                                      "stashcache-client",
                                      by_dependency=True)
        if core.rpm_is_installed("xcache"):
            self.skip_ok_if(core.PackageVersion("xcache") < "1.0.2", "needs xcache 1.0.2+")
        self.skip_bad_unless_running("xrootd@stash-origin", "xrootd@stash-cache", "xrootd@stash-origin-auth",
                                     "xrootd@stash-cache-auth")

    def test_01_create_files(self):
        xrootd_user = pwd.getpwnam("xrootd")
        for name, contents in self.testfiles:
            files.write(os.path.join(getcfg("OriginRootdir"), getcfg("OriginExport").lstrip("/"), name),
                        contents, backup=False, chmod=0o644,
                        chown=(xrootd_user.pw_uid, xrootd_user.pw_gid))
            files.write(os.path.join(getcfg("OriginRootdir"), getcfg("OriginAuthExport").lstrip("/"), name),
                        contents, backup=False, chmod=0o644,
                        chown=(xrootd_user.pw_uid, xrootd_user.pw_gid))

    def test_02_xrootd_fetch_from_origin(self):
        name, contents = self.testfiles[0]
        path = os.path.join(getcfg("OriginExport"), name)
        result, _, _ = \
            core.check_system(["xrdcp", "-d1", "-N", "-f",
                               "root://localhost:%d/%s" % (getcfg("OriginXrootPort"), path),
                               "-"], "Checking xroot copy from origin")
        self.assertEqualVerbose(core.to_str(result), contents, "downloaded file mismatch")

    def test_03_http_fetch_from_cache(self):
        name, contents = self.testfiles[1]
        path = os.path.join(getcfg("OriginExport"), name)
        try:
            f = urlopen(
                "http://localhost:%d/%s" % (getcfg("CacheHTTPPort"), path)
            )
            result = core.to_str(f.read())
        except IOError as e:
            self.fail("Unable to download from cache via http: %s" % e)
        self.assertEqualVerbose(result, contents, "downloaded file mismatch")
        self.assertCached(name, contents)

    def test_04_xroot_fetch_from_cache(self):
        name, contents = self.testfiles[2]
        path = os.path.join(getcfg("OriginExport"), name)
        result, _, _ = \
            core.check_system(["xrdcp", "-d1", "-N", "-f",
                               "root://localhost:%d/%s" % (getcfg("CacheXrootPort"), path),
                               "-"], "Checking xroot copy from cache")
        self.assertEqualVerbose(core.to_str(result), contents, "downloaded file mismatch")
        self.assertCached(name, contents)

    def test_05_stashcp(self):
        command = ["stashcp", "-d"]
        if core.PackageVersion('stashcache-client') < '5.1.0-5':
            command.append("--cache=root://localhost")
        name, contents = self.testfiles[3]
        path = os.path.join(getcfg("OriginExport"), name)
        with tempfile.NamedTemporaryFile(mode="r+b") as tf:
            core.check_system(command + [path, tf.name],
                              "Checking stashcp")
            result = tf.read()
        self.assertEqualVerbose(core.to_str(result), contents, "stashcp'ed file mismatch")
        self.assertCached(name, contents)

    def test_06_xrootd_fetch_from_origin_auth(self):
        core.skip_ok_unless_installed('globus-proxy-utils', by_dependency=True)
        self.skip_bad_unless(core.state['proxy.valid'], 'requires a proxy cert')
        name, contents = self.testfiles[0]
        path = os.path.join(getcfg("OriginAuthExport"), name)
        dest_file = '/tmp/testfileFromOriginAuth'
        os.environ["XrdSecGSISRVNAMES"] = "*"
        result, _, _ = core.check_system(["xrdcp", "-d1", '-f', 
                                          "root://localhost:%d/%s" % (getcfg("OriginAuthXrootPort"), path),
                                          dest_file],
                                         "Checking xrootd copy from authenticated origin", user=True)
        origin_file = os.path.join(getcfg("OriginRootdir"), getcfg("OriginAuthExport").lstrip("/"), name)
        checksum_match = files.checksum_files_match(origin_file, dest_file)
        self.assert_(checksum_match, 'Origin and directly downloaded file have the same contents')

    def test_07_xrootd_fetch_from_auth_cache(self):
        core.skip_ok_unless_installed('globus-proxy-utils', by_dependency=True)
        self.skip_bad_unless(core.state['proxy.valid'], 'requires a proxy cert')
        name, contents = self.testfiles[2]
        path = os.path.join(getcfg("OriginAuthExport"), name)
        os.environ["XrdSecGSISRVNAMES"] = "*"
        dest_file = '/tmp/testfileXrootdFromAuthCache'
        result, _, _ = \
            core.check_system(["xrdcp", "-d1","-f",
                               "root://%s:%d/%s" % (core.get_hostname(),getcfg("CacheHTTPSPort"), path),
                               dest_file], "Checking xrootd copy from Authenticated cache", user=True)
        origin_file = os.path.join(getcfg("OriginRootdir"), getcfg("OriginAuthExport").lstrip("/"), name)
        checksum_match = files.checksum_files_match(origin_file, dest_file)
        self.assert_(checksum_match, 'Origin and file downloaded via cache have the same contents')

    def test_08_https_fetch_from_auth_cache(self):
        core.skip_ok_unless_installed('globus-proxy-utils', 'gfal2-plugin-http', 'gfal2-util', 
                                      'gfal2-plugin-file', by_dependency=True)
        self.skip_bad_unless(core.state['proxy.valid'], 'requires a proxy cert')
        name, contents = self.testfiles[3]
        path = os.path.join(getcfg("OriginAuthExport"), name)
        dest_file = '/tmp/testfileHTTPsFromAuthCache'
        uid = pwd.getpwnam(core.options.username)[2]
        usercert = '/tmp/x509up_u%d' % uid
        userkey = '/tmp/x509up_u%d' % uid
        result, _, _ = \
            core.check_system(["gfal-copy", "-vf",
                               "--cert", usercert, "--key", userkey,
                               "https://%s:%d%s" % (core.get_hostname(),getcfg("CacheHTTPSPort"), path),
                               "file://%s"%dest_file],
                              "Checking xrootd copy from Authenticated cache", user=True)
        origin_file = os.path.join(getcfg("OriginRootdir"), getcfg("OriginAuthExport").lstrip("/"), name)
        checksum_match = files.checksum_files_match(origin_file, dest_file)
        self.assert_(checksum_match, 'Origin and file downloaded via cache have the same contents')
