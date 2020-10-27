import os
import pwd
import osgtest.library.core as core
import osgtest.library.files as files
import osgtest.library.service as service
import osgtest.library.osgunittest as osgunittest


HTTP_PORT1 = 9001  # chosen so it doesn't conflict w/ the stashcache instances
HTTP_PORT2 = 9002

XROOTD_CFG_TEXT = """\
all.adminpath /var/spool/xrootd
all.pidpath /var/run/xrootd
set resourcename = VDTTEST
continue /etc/xrootd/config.d/
"""


XROOTD_MACAROON_TXT = """\
if named third-party-copy-1
set HttpPort = 9001
macaroons.secretkey /etc/xrootd/macaroon-secret-1
xrd.port 9001
fi
if named third-party-copy-2
set HttpPort = 9002
macaroons.secretkey /etc/xrootd/macaroon-secret-2
xrd.port 9002
fi
"""

XROOTD_STANDALONE_TXT = """\
set EnableHttp = 1
set EnableLcmaps = 1

if named standalone
set HttpPort = 1094
xrd.port $(HttpPort)
fi

all.role server
cms.allow host *

# Logging verbosity                                                                                                                                         
xrootd.trace emsg login stall redirect
ofs.trace -all
xrd.trace conn
cms.trace all

xrd.network keepalive kaparms 10m,1m,5
xrd.timeout idle 60m
"""

class TestStartXrootdTPC(osgunittest.OSGTestCase):
    @core.elrelease(7,8)
    def setUp(self):
        core.skip_ok_unless_installed("osg-xrootd-standalone",
                                      by_dependency=True)
        if core.rpm_is_installed("xcache"):
            self.skip_ok_if(core.PackageVersion("xcache") >= "1.0.2", "xcache 1.0.2+ configs conflict with xrootd tests")

    def test_01_configure_xrootd(self):
        core.config['xrootd.tpc.config-1'] = '/etc/xrootd/xrootd-third-party-copy-1.cfg'
        core.config['xrootd.tpc.config-2'] = '/etc/xrootd/xrootd-third-party-copy-2.cfg'
        core.config['xrootd.tpc.basic-config'] = '/etc/xrootd/config.d/36-osg-test-tpc.cfg'
        core.state['xrootd.started-http-server-1'] = False
        core.state['xrootd.started-http-server-2'] = False
        core.state['xrootd.tpc.backups-exist'] = False

        self.skip_ok_unless(core.options.adduser, 'user not created')
        core.skip_ok_unless_installed('globus-proxy-utils', by_dependency=True)

        user = pwd.getpwnam("xrootd")

        files.write(core.config['xrootd.tpc.config-1'],
                     XROOTD_CFG_TEXT,
                     owner='xrootd', backup=True, chown=(user.pw_uid, user.pw_gid))
        files.write(core.config['xrootd.tpc.config-2'],
                     XROOTD_CFG_TEXT,
                     owner='xrootd', backup=True, chown=(user.pw_uid, user.pw_gid))
        files.write('/etc/xrootd/config.d/40-osg-standalone.cfg', XROOTD_STANDALONE_TXT,
                     owner='xrootd', backup=True, chown=(user.pw_uid, user.pw_gid))
        files.write(core.config['xrootd.tpc.basic-config'],
                     XROOTD_MACAROON_TXT,
                     owner='xrootd', backup=True, chown=(user.pw_uid, user.pw_gid))

        core.state['xrootd.tpc.backups-exist'] = True
 
    def test_02_create_secrets(self):
        core.config['xrootd.tpc.macaroon-secret-1'] = '/etc/xrootd/macaroon-secret-1'
        core.config['xrootd.tpc.macaroon-secret-2'] = '/etc/xrootd/macaroon-secret-2'
        core.check_system(["openssl", "rand", "-base64", "-out",
                               core.config['xrootd.tpc.macaroon-secret-1'], "64"], "Creating symmetric key")
        core.check_system(["openssl", "rand", "-base64", "-out",
                               core.config['xrootd.tpc.macaroon-secret-2'], "64"], "Creating symmetric key")

    def test_03_start_xrootd(self):
        if core.rpm_is_installed("xrootd-multiuser"):
            core.config['xrootd_tpc_service_1'] = "xrootd-privileged@third-party-copy-1"
            core.config['xrootd_tpc_service_2'] = "xrootd-privileged@third-party-copy-2"
        else:
            core.config['xrootd_tpc_service_1'] = "xrootd@third-party-copy-1"
            core.config['xrootd_tpc_service_2'] = "xrootd@third-party-copy-2"

        core.system("cat /etc/xrootd/xrootd-third-party-copy-1.cfg", shell=True)
        core.system("cat /etc/xrootd/config.d/*", shell=True)

        service.check_start(core.config['xrootd_tpc_service_1'], log_to_check = '/var/log/xrootd/third-party-copy-1/xrootd.log', min_up_time = 5)
        service.check_start(core.config['xrootd_tpc_service_2'], log_to_check = '/var/log/xrootd/third-party-copy-2/xrootd.log', min_up_time = 5)
        core.state['xrootd.started-http-server-1'] = True
        core.state['xrootd.started-http-server-2'] = True
