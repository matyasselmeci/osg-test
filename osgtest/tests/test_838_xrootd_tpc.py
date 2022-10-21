import osgtest.library.core as core
import osgtest.library.files as files
import osgtest.library.service as service
import osgtest.library.osgunittest as osgunittest
import osgtest.library.xrootd as xrootd

class TestStopXrootdTPC(osgunittest.OSGTestCase):
    @core.elrelease(7,8)
    def setUp(self):
        core.skip_ok_unless_installed("osg-xrootd-standalone",
                                      by_dependency=True)
        self.skip_ok_if(core.rpm_is_installed("xcache"), "xcache configs conflict with xrootd tests")
        self.skip_ok_unless(core.config['xrootd.security'], "no xrootd security available")

    def test_01_dump_logs_if_failures(self):
        self.skip_ok_unless(core.state['xrootd.tpc.had-failures'], "no failures")
        # TODO XXX disable this once we're done debugging
        # self.skip_ok_unless(core.options.manualrun, "only dumping logs on a manual run (osg-test -m)")
        xrootd.dump_log(500, "third-party-copy-1")
        xrootd.dump_log(500, "third-party-copy-2")

    def test_02_stop_xrootd_tpc(self):
        if core.state['xrootd.tpc.backups-exist']:
            files.restore(core.config['xrootd.tpc.config-1'], "xrootd")
            files.restore(core.config['xrootd.tpc.config-2'], "xrootd")
            files.restore(core.config['xrootd.tpc.basic-config'], "xrootd")
            files.restore(xrootd.logfile("third-party-copy-1"), "xrootd", ignore_missing=True)
            files.restore(xrootd.logfile("third-party-copy-2"), "xrootd", ignore_missing=True)

        self.skip_ok_if(not core.state['xrootd.started-http-server-1'] and
                        not core.state['xrootd.started-http-server-2'], 
                        'did not start any of the http servers')
        service.check_stop(core.config['xrootd_tpc_service_1'])
        service.check_stop(core.config['xrootd_tpc_service_2'])

    def test_03_remove_macaroons(self):
        self.skip_ok_unless("GSI" in core.config['xrootd.security'], "Our macaroons tests use GSI")
        files.remove(core.config['xrootd.tpc.macaroon-secret-1'], force=True)
        files.remove(core.config['xrootd.tpc.macaroon-secret-2'], force=True)
