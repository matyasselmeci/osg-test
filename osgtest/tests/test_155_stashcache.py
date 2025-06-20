import os
import shlex
import subprocess
import sys
import time

from osgtest.library import core
from osgtest.library import files
from osgtest.library.osgunittest import OSGTestCase
from osgtest.library import service
from osgtest.library import xrootd


# These will end up as environment variables in the xrootd configs
# as well core.config["stashcache.KEY"] = var
# Xrootd config syntax doesn't allow underscores so this is CamelCase.
PARAMS = dict(
    CacheRootdir              = "/tmp/sccache",
    CacheXrootPort            = 1094,  # can't change this - stashcp doesn't allow you to specify port
    CacheHTTPPort             = 8001,
    CacheHTTPSPort            = 8444,
    OriginXrootPort           = 1095,
    OriginAuthXrootPort       = 1096,
    OriginRootdir             = "/tmp/scorigin",
    OriginExport              = "/osgtest/PUBLIC",
    OriginAuthExport          = "/osgtest/PROTECTED",
    OriginDummyExport         = "/osgtest/dummy",
    # ^ originexport needs to be defined on caches too because they use the same config.d
    #   This is relative to CacheRootdir, not OriginRootdir
    StashOriginAuthfile       = "/etc/xrootd/Authfile-origin",
    StashOriginPublicAuthfile = "/etc/xrootd/Authfile-origin-public",
    StashCacheAuthfile        = "/etc/xrootd/Authfile-cache",
    StashCachePublicAuthfile  = "/etc/xrootd/Authfile-cache-public",
    OriginResourcename        = "OSG_TEST_ORIGIN",
    CacheResourcename         = "OSG_TEST_CACHE",
)

PARAMS_CFG_PATH = "/etc/xrootd/config.d/01-params.cfg"
# Some statements can take env vars on the right hand side (setenv); others take config vars (set)
# so define both.
PARAMS_CFG_CONTENTS = "\n".join("setenv {0} = {1}\nset {0} = {1}".format(k, v)
                                for k, v in PARAMS.items()) + "\n"


PRE_CFG_PATH = "/etc/xrootd/config.d/11-pre.cfg"
PRE_CFG_CONTENTS = """
set DisableOsgMonitoring = 1

if named stash-cache-auth
    xrd.port $(CacheHTTPSPort)
    set rootdir = $(CacheRootdir)
    set resourcename = $(CacheResourcename)
    set originexport = $(OriginDummyExport)
    
    ofs.osslib libXrdPss.so
    pss.cachelib libXrdFileCache.so

    pss.origin localhost:$(OriginAuthXrootPort)
    xrd.protocol http:$(CacheHTTPSPort) libXrdHttp.so
    setenv XrdSecGSISRVNAMES=*
else if named stash-cache
    xrd.port $(CacheXrootPort)
    set rootdir = $(CacheRootdir)
    set resourcename = $(CacheResourcename)
    set originexport = $(OriginDummyExport)

    ofs.osslib libXrdPss.so
    pss.cachelib libXrdFileCache.so

    pss.origin localhost:$(OriginXrootPort)
    xrd.protocol http:$(CacheHTTPPort) libXrdHttp.so
else if named stash-origin-auth
    xrd.port $(OriginAuthXrootPort)
    set rootdir = $(OriginRootdir)
    set resourcename = $(OriginResourcename)
    set originexport = $(OriginAuthExport)
else if named stash-origin
    xrd.port $(OriginXrootPort)
    set rootdir = $(OriginRootdir)
    set resourcename = $(OriginResourcename)
    set originexport = $(OriginExport)
fi
{maybe_enable_voms}
"""

CACHE_AUTHFILE_PATH = PARAMS["StashCacheAuthfile"]
# 
# The hash of the vdttest user DN
# "/DC=org/DC=opensciencegrid/C=US/O=OSG Software/OU=People/CN=vdttest"
# is b64f6609.0
#
user_DN_hash = "b64f6609.0"
CACHE_AUTHFILE_CONTENTS = "u %s /osgtest/PROTECTED rl\n" % (user_DN_hash)
CACHE_PUBLIC_AUTHFILE_PATH = PARAMS["StashCachePublicAuthfile"]
CACHE_PUBLIC_AUTHFILE_CONTENTS = """
u * /osgtest/PROTECTED -rl \
/ rl
"""


ORIGIN_AUTHFILE_PATH = PARAMS["StashOriginAuthfile"]
ORIGIN_AUTHFILE_CONTENTS = "u * /osgtest/PROTECTED rl\n"

ORIGIN_PUBLIC_AUTHFILE_PATH = PARAMS["StashOriginPublicAuthfile"]
ORIGIN_PUBLIC_AUTHFILE_CONTENTS = "u * /osgtest/PUBLIC rl\n"

CACHES_JSON_PATH = "/etc/stashcache/caches.json"
CACHES_JSON_CONTENTS = """\
[
{"name":"root://localhost", "status":1, "longitude":-89.4012, "latitude":43.0731}
]
"""

GRID_MAPFILE = "/etc/grid-security/grid-mapfile"
ORIGIN_SCITOKENS_CONF_PATH = "/run/stash-origin-auth/scitokens.conf"
ORIGIN_GRIDMAP_PATH = "/run/stash-origin-auth/grid-mapfile"
CACHE_SCITOKENS_CONF_PATH = "/run/stash-cache-auth/scitokens.conf"
CACHE_GRIDMAP_PATH = "/run/stash-cache-auth/grid-mapfile"
SCITOKENS_CONF_CONTENTS = """\
[Issuer /unregistered]
issuer = https://scitokens.org/unregistered
base_path = /unregistered
"""

XROOTD_ORIGIN_CFG_PATH = "/etc/xrootd/xrootd-stash-origin.cfg"

NAMESPACE = "stashcache"


def setcfg(key, val):
    core.config["%s.%s" % (NAMESPACE, key)] = val


def setstate(key, val):
    core.state["%s.%s" % (NAMESPACE, key)] = val


def start_xrootd(instance):
    svc = "xrootd@%s" % instance
    config_dump = xrootd.cconfig(instance)
    core.log_message(f"cconfig dump for xrootd instance '{instance}'\n" +
                     "\n".join(config_dump))
    if not service.is_running(svc):
        try:
            service.check_start(svc, min_up_time=3)
        except Exception:
            core.system(["tail", "-n", "75", f"/var/log/xrootd/{instance}/xrootd.log"])
            core.system(["systemctl", "status", svc])
            raise


class TestStartStashCache(OSGTestCase):
    @core.osgrelease(23)
    def setUp(self):
        core.skip_ok_unless_installed("stash-origin",
                                      "stash-cache",
                                      "stashcp",
                                      by_dependency=True)
        if core.rpm_is_installed("pelican"):
            self.skip_ok("pelican is installed, skipping stashcache tests")

    def test_00_enable_coredumps(self):
        size = 100_000_000  # 100 MB, let's not make it too big
        files.append("/etc/systemd/system.conf", f"DefaultLimitCORE={size}", backup=False)
        core.system(["sysctl", "kernel.core_pattern=/var/log/core_%e_%p_%h_%t"])

    def test_01_configure(self):
        caching_plugin_cfg_path = "/etc/xrootd/config.d/40-stash-cache-plugin.cfg"
        http_cfg_path = "/etc/xrootd/config.d/50-osg-http.cfg"

        for key, val in PARAMS.items():
            setcfg(key, val)

        # Create dirs
        for d in [PARAMS["OriginRootdir"],
                  PARAMS["CacheRootdir"],
                  os.path.join(PARAMS["OriginRootdir"], PARAMS["OriginExport"].lstrip("/")),
                  os.path.join(PARAMS["OriginRootdir"], PARAMS["OriginAuthExport"].lstrip("/")),
                  os.path.join(PARAMS["CacheRootdir"], PARAMS["OriginDummyExport"].lstrip("/")),
                  os.path.dirname(CACHES_JSON_PATH),
                  os.path.dirname(CACHE_SCITOKENS_CONF_PATH),
                  os.path.dirname(ORIGIN_SCITOKENS_CONF_PATH),
                  ]:
            files.safe_makedirs(d)

        core.system(["chown", "-R", "xrootd:xrootd", PARAMS["OriginRootdir"], PARAMS["CacheRootdir"]])

        filelist = []
        setcfg("filelist", filelist)
        # Modify filelist in-place with .append so changes get into core.config too

        # Delete the lines we can't override
        for path, regexp in [
            (XROOTD_ORIGIN_CFG_PATH, "^\s*all.manager.+$"),
            (http_cfg_path, "^\s*xrd.protocol.+$"),
            (caching_plugin_cfg_path, "^\s*(ofs.osslib|pss.cachelib|pss.origin).+$"),
        ]:
            files.replace_regexpr(path, regexp, "", owner=NAMESPACE)
            filelist.append(path)

        maybe_enable_voms = ""
        if core.rpm_is_installed("osg-xrootd"):
            if core.PackageVersion("osg-xrootd") >= "3.6-16":
                maybe_enable_voms = "set EnableVoms = 1"

        gridmap_text = ""
        if os.path.exists(GRID_MAPFILE):
            gridmap_text = files.read(GRID_MAPFILE, as_single_string=True)

        # Write our new files
        for path, contents in [
            (PARAMS_CFG_PATH, PARAMS_CFG_CONTENTS),
            (PRE_CFG_PATH, PRE_CFG_CONTENTS.format(**locals())),
            (ORIGIN_AUTHFILE_PATH, ORIGIN_AUTHFILE_CONTENTS),
            (ORIGIN_PUBLIC_AUTHFILE_PATH, ORIGIN_PUBLIC_AUTHFILE_CONTENTS),
            (CACHE_AUTHFILE_PATH, CACHE_AUTHFILE_CONTENTS),
            (CACHE_PUBLIC_AUTHFILE_PATH, CACHE_PUBLIC_AUTHFILE_CONTENTS),
            (CACHES_JSON_PATH, CACHES_JSON_CONTENTS),
            (CACHE_SCITOKENS_CONF_PATH, SCITOKENS_CONF_CONTENTS),
            (ORIGIN_SCITOKENS_CONF_PATH, SCITOKENS_CONF_CONTENTS),
            (ORIGIN_GRIDMAP_PATH, gridmap_text),
            (CACHE_GRIDMAP_PATH, gridmap_text),
        ]:
            files.write(path, contents, owner=NAMESPACE, chmod=0o644)
            filelist.append(path)
            core.log_message(f"***** Wrote file {path} with the following contents:\n{contents}\n***** END *****")

        # Install certs.  Normally done in the xrootd tests but they conflict with the StashCache tests
        # (both use the same config dir)
        core.config['certs.xrootdcert'] = '/etc/grid-security/xrd/xrdcert.pem'
        core.config['certs.xrootdkey'] = '/etc/grid-security/xrd/xrdkey.pem'
        core.install_cert('certs.xrootdcert', 'certs.hostcert', 'xrootd', 0o644)
        core.install_cert('certs.xrootdkey', 'certs.hostkey', 'xrootd', 0o400)

    def test_02_start_stash_origin(self):
        start_xrootd("stash-origin")

    def test_03_start_stash_origin_auth(self):
        start_xrootd("stash-origin-auth")

    def test_04_start_stash_cache(self):
        start_xrootd("stash-cache")

    def test_05_start_stash_cache_auth(self):
        start_xrootd("stash-cache-auth")

    def test_06_start_namespaces_json_server(self):
        # Start the namespaces JSON server in the background
        # Don't wait for it to finish, but keep track of the process by saving
        # the process object in core.state.

        # TODO: Turn this into a systemd service
        setstate("namespaces_json_server_proc", None)
        setcfg("STASH_NAMESPACE_URL", "")
        q_python = shlex.quote(sys.executable)
        logfile = "/tmp/namespaces_json.log.%d" % os.getpid()
        setcfg("namespaces_json_server_logfile", logfile)
        proc = subprocess.Popen(f"{q_python} -m osgtest.library.namespaces_json_server > {logfile} 2>&1", shell=True)

        # Make sure it didn't immediately crash
        time.sleep(2)
        ret = proc.poll()
        if ret is not None:
            core.system(["/bin/cat", logfile])
            self.assertEqual(ret, None, f"namespaces JSON server terminated prematurely with code {ret}")

        setstate("namespaces_json_server_proc", proc)
        setcfg("STASH_NAMESPACE_URL", "http://localhost:1080")
