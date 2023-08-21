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
        ("testfile%d" % x, str(random.random()) + "\n")
        for x in range(4)
    ]

    def assertCached(self, name, contents, auth=False):
        OriginExport = getcfg("OriginExport")
        if auth:
            OriginExport = getcfg("OriginAuthExport")
        fpath = os.path.join(getcfg("CacheRootdir"), OriginExport.lstrip("/"), name)
        self.assertTrue(os.path.exists(fpath),
                        name + " not cached")
        self.assertEqualVerbose(actual=core.to_str(files.read(fpath, as_single_string=True)),
                                expected=contents,
                                message="cached file %s mismatch" % name)

    @core.osgrelease(23)
    def setUp(self):
        core.skip_ok_unless_installed("stash-origin",
                                      "stash-cache",
                                      "stashcp",
                                      by_dependency=True)
        if core.rpm_is_installed("pelican"):
            self.skip_ok("pelican is installed, skipping stashcache tests")
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

    def test_03a_http_fetch_from_cache_is_cached(self):
        name, contents = self.testfiles[1]
        self.assertCached(name, contents)

    def test_04_xroot_fetch_from_cache(self):
        name, contents = self.testfiles[2]
        path = os.path.join(getcfg("OriginExport"), name)
        result, _, _ = \
            core.check_system(["xrdcp", "-d1", "-N", "-f",
                               "root://localhost:%d/%s" % (getcfg("CacheXrootPort"), path),
                               "-"], "Checking xroot copy from cache")
        self.assertEqualVerbose(core.to_str(result), contents, "downloaded file mismatch")

    def test_04a_xroot_fetch_from_cache_is_cached(self):
        name, contents = self.testfiles[2]
        self.assertCached(name, contents)

    def test_05_stashcp(self):
        command = ["stashcp", "-d"]
        if not core.rpm_is_installed("stashcache-client"):
            # stashcp (the Go versions) doesn't use caches.json so specify the cache on the command line
            # (it also doesn't use root://)
            command.append("--cache=http://localhost:%d" % getcfg("CacheHTTPPort"))
        name, contents = self.testfiles[3]
        path = os.path.join(getcfg("OriginExport"), name)

        # If we have the namespaces json server running, set STASH_NAMESPACE_URL so stashcp can use it.
        # Also set STASH_TOPOLOGY_NAMESPACE_URL because that is the env var the Pelican version of stashcp uses.
        # (STASH_FEDERATION_TOPOLOGYNAMESPACEURL also works but is a mouthful)
        stash_namespace_url = getcfg("STASH_NAMESPACE_URL")
        with tempfile.NamedTemporaryFile(mode="r+b") as tf:
            with core.environ_context({"STASH_NAMESPACE_URL": stash_namespace_url,
                                       "STASH_TOPOLOGY_NAMESPACE_URL": stash_namespace_url,
                                       "STASH_USE_TOPOLOGY": "1"}):
                core.check_system(command + [path, tf.name],
                                  "Checking stashcp")
            result = tf.read()
        self.assertEqualVerbose(core.to_str(result), contents, "stashcp'ed file mismatch")

    def test_05a_stashcp_is_cached(self):
        name, contents = self.testfiles[3]
        self.assertCached(name, contents)

    def test_06_xrootd_fetch_from_origin_auth(self):
        # TODO This should work with voms certs too
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
        # TODO This should work with voms certs too
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
        # TODO This should work with voms certs too
        core.skip_ok_unless_installed('globus-proxy-utils', 'gfal2-plugin-http', 'gfal2-util-scripts',
                                      'gfal2-plugin-file', by_dependency=True)
        core.skip_ok_unless_one_installed('python2-gfal2-util', 'python3-gfal2-util')
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
