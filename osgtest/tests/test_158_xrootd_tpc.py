import os
import pwd
import osgtest.library.core as core
import osgtest.library.files as files
import osgtest.library.service as service
import osgtest.library.osgunittest as osgunittest
import osgtest.library.xrootd as xrootd


HTTP_PORT1 = 9001  # chosen so it doesn't conflict w/ the stashcache instances
HTTP_PORT2 = 9002

XROOTD_CFG_TEXT = f"""\
all.adminpath /var/spool/xrootd
all.pidpath /var/run/xrootd
set resourcename = VDTTEST
set rootdir = {xrootd.ROOTDIR}
continue /etc/xrootd/config.d/
"""


XROOTD_TPC_TXT = f"""
if named third-party-copy-1
  set HttpPort = {HTTP_PORT1}
  xrd.port {HTTP_PORT1}
fi
if named third-party-copy-2
  set HttpPort = {HTTP_PORT2}
  xrd.port {HTTP_PORT2}
fi
"""

XROOTD_MACAROON_TXT = """
if named third-party-copy-1
  macaroons.secretkey /etc/xrootd/macaroon-secret-1
fi
if named third-party-copy-2
  macaroons.secretkey /etc/xrootd/macaroon-secret-2
fi
"""


class TestStartXrootdTPC(osgunittest.OSGTestCase):
    def setUp(self):
        core.skip_ok_unless_installed("osg-xrootd-standalone",
                                      by_dependency=True)
        self.skip_ok_if(core.rpm_is_installed("xcache"), "xcache configs conflict with xrootd tests")
        self.skip_ok_unless(core.state['xrootd.is-configured'], "xrootd is not configured")

    def test_01_configure_xrootd(self):
        core.config['xrootd.tpc.config-1'] = '/etc/xrootd/xrootd-third-party-copy-1.cfg'
        core.config['xrootd.tpc.config-2'] = '/etc/xrootd/xrootd-third-party-copy-2.cfg'
        core.config['xrootd.tpc.basic-config'] = '/etc/xrootd/config.d/36-osg-test-tpc.cfg'
        core.state['xrootd.started-http-server-1'] = False
        core.state['xrootd.started-http-server-2'] = False
        core.state['xrootd.tpc.backups-exist'] = False
        core.state['xrootd.tpc.had-failures'] = False

        self.skip_ok_unless(core.options.adduser, 'user not created')

        user = pwd.getpwnam("xrootd")

        files.write(core.config['xrootd.tpc.config-1'],
                    XROOTD_CFG_TEXT,
                    owner='xrootd', backup=True, chown=(user.pw_uid, user.pw_gid),
                    chmod=0o644)
        files.write(core.config['xrootd.tpc.config-2'],
                    XROOTD_CFG_TEXT,
                    owner='xrootd', backup=True, chown=(user.pw_uid, user.pw_gid),
                    chmod=0o644)
        files.write(core.config['xrootd.tpc.basic-config'],
                    XROOTD_TPC_TXT +
                    (XROOTD_MACAROON_TXT if "GSI" in core.config['xrootd.security'] else ""),
                    owner='xrootd', backup=True, chown=(user.pw_uid, user.pw_gid),
                    chmod=0o644)

        core.state['xrootd.tpc.backups-exist'] = True

    def test_02_create_macaroons(self):
        self.skip_ok_unless("GSI" in core.config['xrootd.security'],
                            "Our macaroons tests use GSI")
        core.config['xrootd.tpc.macaroon-secret-1'] = '/etc/xrootd/macaroon-secret-1'
        core.config['xrootd.tpc.macaroon-secret-2'] = '/etc/xrootd/macaroon-secret-2'
        core.check_system(["openssl", "rand", "-base64", "-out",
                               core.config['xrootd.tpc.macaroon-secret-1'], "64"], "Creating symmetric key")
        core.check_system(["openssl", "rand", "-base64", "-out",
                               core.config['xrootd.tpc.macaroon-secret-2'], "64"], "Creating symmetric key")

    def test_03_start_xrootd_tpc(self):
        if core.rpm_is_installed("xrootd-multiuser"):
            core.config['xrootd_tpc_service_1'] = "xrootd-privileged@third-party-copy-1"
            core.config['xrootd_tpc_service_2'] = "xrootd-privileged@third-party-copy-2"
        else:
            core.config['xrootd_tpc_service_1'] = "xrootd@third-party-copy-1"
            core.config['xrootd_tpc_service_2'] = "xrootd@third-party-copy-2"
        if core.options.manualrun:
            files.preserve_and_remove(xrootd.logfile("third-party-copy-1"), owner="xrootd")
            files.preserve_and_remove(xrootd.logfile("third-party-copy-2"), owner="xrootd")
        service.check_start(core.config['xrootd_tpc_service_1'], min_up_time = 5)
        service.check_start(core.config['xrootd_tpc_service_2'], min_up_time = 5)
        core.state['xrootd.started-http-server-1'] = True
        core.state['xrootd.started-http-server-2'] = True
