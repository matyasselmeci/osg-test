import cagen

import osgtest.library.core as core
import osgtest.library.files as files
import osgtest.library.osgunittest as osgunittest
import osgtest.library.condor as condor
import osgtest.library.service as service


class TestStartCondorCE(osgunittest.OSGTestCase):
    def test_01_configure_condor(self):
        core.skip_ok_unless_installed('condor', 'htcondor-ce', 'htcondor-ce-client')

        core.config['condor-ce.condor-cfg'] = '/etc/condor/config.d/99-osgtest.condor.conf'
        contents = """SCHEDD_INTERVAL=1
QUEUE_SUPER_USER_MAY_IMPERSONATE = .*

ENABLE_KERNEL_TUNING = FALSE
COLLECTOR_MAX_FILE_DESCRIPTORS = 1024
SHARED_PORT_MAX_FILE_DESCRIPTORS = 1024
SCHEDD_MAX_FILE_DESCRIPTORS = 1024
MAX_FILE_DESCRIPTORS = 1024
"""

        files.write(core.config['condor-ce.condor-cfg'],
                    contents,
                    owner='condor-ce',
                    chmod=0o644)

    def test_02_reconfigure_condor(self):
        core.skip_ok_unless_installed('condor', 'htcondor-ce', 'htcondor-ce-client')
        self.skip_bad_unless(core.state['condor.running-service'], 'Condor not running')

        # Ensure that the Condor master is available for reconfig
        self.failUnless(condor.wait_for_daemon(core.config['condor.collectorlog'],
                                               core.config['condor.collectorlog_stat'],
                                               'Master',
                                               300.0),
                        'Condor Master not available for reconfig')

        command = ('condor_reconfig', '-debug')
        core.check_system(command, 'Reconfigure Condor')
        self.assertTrue(service.is_running('condor', timeout=10), 'Condor not running after reconfig')

    def test_02_scitoken_mapping(self):
        core.state['condor-ce.wrote-mapfile'] = False
        core.skip_ok_unless_installed('condor', 'htcondor-ce')
        self.skip_ok_if(core.PackageVersion('condor') <= '8.9.4',
                        'HTCondor version does not support SciToken submission')

        condorce_version = core.PackageVersion('htcondor-ce')
        scitoken_mapping = 'SCITOKENS {issuer} {local_user}\n'

        # Write the mapfile to the admin mapfile directory with the regex format for the issuer
        # required by 'CERTIFICATE_MAPFILE_ASSUME_HASH_KEYS = True'
        # https://github.com/htcondor/htcondor-ce/pull/425
        if condorce_version >= '5.1.0':
            match_str = r'/https:\/\/demo.scitokens.org,.*/'
            core.config['condor-ce.mapfile'] = '/etc/condor-ce/mapfiles.d/01-osg-test.conf'
        else:
            match_str = '"https://demo.scitokens.org"'
            core.config['condor-ce.mapfile'] = '/etc/condor-ce/condor_mapfile'
            mapfile_contents = files.read(core.config['condor-ce.mapfile'], as_single_string=True)
            scitoken_mapping += mapfile_contents

        files.write(core.config['condor-ce.mapfile'],
                    scitoken_mapping.format(issuer=match_str, local_user=core.options.username),
                    owner='condor-ce',
                    chmod=0o644)
        core.state['condor-ce.wrote-mapfile'] = True

    def test_03_configure_ce(self):
        core.skip_ok_unless_installed('condor', 'htcondor-ce', 'htcondor-ce-client')

        # Set up Condor, PBS, and Slurm routes
        # Leave the GRIDMAP knob in tact to verify that it works with the LCMAPS VOMS plugin
        core.config['condor-ce.condor-ce-cfg'] = '/etc/condor-ce/config.d/99-osgtest.condor-ce.conf'

        condor_contents = """GRIDMAP = /etc/grid-security/grid-mapfile
ALL_DEBUG=D_CAT D_ALWAYS:2 D_SECURITY:2

JOB_ROUTER_USE_DEPRECATED_ROUTER_ENTRIES = False
JOB_ROUTER_PRE_ROUTE_TRANSFORM_NAMES = $(JOB_ROUTER_PRE_ROUTE_TRANSFORM_NAMES) DefaultMemory
JOB_ROUTER_TRANSFORM_DefaultMemory @=jrt
    default_MaxMemory = 128
@jrt

JOB_ROUTER_ROUTE_NAMES = PBS_Cluster, Slurm_Cluster, Condor_Pool
JOB_ROUTER_ROUTE_PBS_Cluster @=jrt
    REQUIREMENTS osgTestBatchSystem =?= "pbs"
    TargetUniverse = 9
    GridResource = "batch pbs"
@jrt
JOB_ROUTER_ROUTE_Slurm_Cluster @=jrt
    REQUIREMENTS osgTestBatchSystem =?= "slurm"
    TargetUniverse = 9
    GridResource = "batch slurm"
@jrt
JOB_ROUTER_ROUTE_Condor_Pool @=jrt
    REQUIREMENTS (osgTestBatchSystem =!= "pbs" && osgTestBatchSystem =!= "slurm")
  TargetUniverse = 5
@jrt

JOB_ROUTER_SCHEDD2_SPOOL=/var/lib/condor/spool
JOB_ROUTER_SCHEDD2_NAME=$(FULL_HOSTNAME)
JOB_ROUTER_SCHEDD2_POOL=$(FULL_HOSTNAME):9618

AUTH_SSL_SERVER_CERTFILE = /etc/grid-security/hostcert.pem
AUTH_SSL_SERVER_KEYFILE = /etc/grid-security/hostkey.pem
AUTH_SSL_SERVER_CADIR = /etc/grid-security/certificates
AUTH_SSL_SERVER_CAFILE =
AUTH_SSL_CLIENT_CERTFILE = /etc/grid-security/hostcert.pem
AUTH_SSL_CLIENT_KEYFILE = /etc/grid-security/hostkey.pem
AUTH_SSL_CLIENT_CADIR = /etc/grid-security/certificates
AUTH_SSL_CLIENT_CAFILE =
"""

        if core.rpm_is_installed('htcondor-ce-view'):
            condor_contents += "\nDAEMON_LIST = $(DAEMON_LIST), CEVIEW, GANGLIAD, SCHEDD"
            core.config['condor-ce.view-port'] = condor.ce_config_val('HTCONDORCE_VIEW_PORT')

        files.write(core.config['condor-ce.condor-ce-cfg'],
                    condor_contents,
                    owner='condor-ce',
                    chmod=0o644)

    def test_04_start_condorce(self):
        if core.el_release() >= 7:
            core.config['condor-ce.lockfile'] = '/var/lock/condor-ce/htcondor-ceLock'
        else:
            core.config['condor-ce.lockfile'] = '/var/lock/subsys/condor-ce'
        core.state['condor-ce.started-service'] = False
        core.state['condor-ce.schedd-ready'] = False

        core.skip_ok_unless_installed('condor', 'htcondor-ce', 'htcondor-ce-client')
        core.config['condor-ce.collectorlog'] = condor.ce_config_val('COLLECTOR_LOG')

        if service.is_running('condor-ce'):
            core.state['condor-ce.schedd-ready'] = True
            self.skip_ok('already running')

        stat = core.get_stat(core.config['condor-ce.collectorlog'])

        service.check_start('condor-ce', timeout=20)

        if condor.wait_for_daemon(core.config['condor-ce.collectorlog'], stat, 'Schedd', 300.0):
            core.state['condor-ce.schedd-ready'] = True
