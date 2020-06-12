#pylint: disable=C0301
#pylint: disable=R0904

import os
import re
try:
    from urllib2 import urlopen
except ImportError:
    from urllib.request import urlopen
import json

import osgtest.library.core as core
import osgtest.library.files as files
import osgtest.library.service as service
import osgtest.library.osgunittest as osgunittest


class TestCondorCE(osgunittest.OSGTestCase):

    def setUp(self):
        # Enforce SciToken or GSI auth for testing
        os.environ['_condor_SEC_CLIENT_AUTHENTICATION_METHODS'] = 'SCITOKENS, GSI'
        core.skip_ok_unless_installed('condor', 'htcondor-ce')
        self.skip_bad_unless(service.is_running('condor-ce'), 'ce not running')

        self.command = []
        if core.state['token.condor_write_created']:
            self.command = [f"_condor_SCITOKENS_FILE={core.config['token.condor_write']}"]

    def tearDown(self):
        os.environ.pop('_condor_SEC_CLIENT_AUTHENTICATION_METHODS')

    def check_write_creds(self):
        """Check for credentials necessary for HTCondor-CE WRITE
        """
        self.skip_bad_unless(core.state['proxy.valid'] or core.state['token.condor_write_created'],
                             'requires a scitoken or a proxy')

    def check_schedd_ready(self):
        """Check if the HTCondor-CE schedd is up as expected
        """
        self.skip_bad_unless(core.state['condor-ce.schedd-ready'], 'CE schedd not ready to accept jobs')

    def run_trace(self, *args):
        """Run condor_ce_trace along with any additional *args. If trace completes with a held job, also return output
        from 'condor_ce_q -held'.
        """

        cwd = os.getcwd()
        os.chdir('/tmp')
        self.command += ['condor_ce_trace', '--debug'] + list(args) + [core.get_hostname()]
        trace_rc, trace_out, trace_err = core.system(self.command, user=True)
        os.chdir(cwd)

        if trace_rc:
            msg = 'condor_ce_trace failed'
            if trace_out.find(', was held'):
                msg = 'condor_ce_trace job held'
                _, hold_out, hold_err = core.system(('condor_ce_q', '-held'))
            self.fail(core.diagnose(msg,
                                    self.command,
                                    trace_rc,
                                    str(trace_out) + str(hold_out),
                                    str(trace_err) + str(hold_err)))

        return trace_out, trace_err

    def run_blahp_trace(self, lrms):
        """Run condor_ce_trace() against a non-HTCondor backend and verify the cache"""
        trace_out, _ = self.run_trace(f'-a osgTestBatchSystem = {lrms.lower()}')

        try:
            re.search(r'%s_JOBID=(\d+)' % lrms.upper(), trace_out).group(1)
        except AttributeError:
            # failed to find backend job ID
            self.fail('did not run against %s' % lrms.upper())

    def test_01_status(self):
        command = ('condor_ce_status', '-any')
        core.check_system(command, 'ce status', user=True)

    def test_02_queue(self):
        command = ('condor_ce_q', '-verbose')
        core.check_system(command, 'ce queue', user=True)

    def test_03_ping(self):
        self.check_write_creds()
        self.command += ['condor_ce_ping', 'WRITE', '-verbose']
        stdout, _, _ = core.check_system(self.command, 'ping using SCITOKENS or GSI', user=True)
        self.assertTrue(re.search(r'Authorized:\s*TRUE', stdout), 'could not authorize with SCITOKENS or GSI')

    def test_04_trace(self):
        self.check_schedd_ready()
        self.check_write_creds()
        self.run_trace()


    def test_05_pbs_trace(self):
        core.skip_ok_unless_installed('torque-mom', 'torque-server', 'torque-scheduler', 'torque-client', 'munge',
                                      by_dependency=True)
        self.skip_ok_unless(service.is_running('pbs_server'), 'pbs service not running')
        self.check_schedd_ready()
        self.check_write_creds()
        self.run_blahp_trace('pbs')

    def test_06_slurm_trace(self):
        core.skip_ok_unless_installed(core.SLURM_PACKAGES)
        self.skip_bad_unless(core.state['condor-ce.schedd-ready'], 'CE schedd not ready to accept jobs')
        self.skip_ok_unless(service.is_running(core.config['slurm.service-name']), 'slurm service not running')
        self.check_schedd_ready()
        self.check_write_creds()
        self.run_blahp_trace('slurm')

    def test_07_ceview(self):
        core.config['condor-ce.view-listening'] = False
        core.skip_ok_unless_installed('htcondor-ce-view')
        view_url = 'http://%s:%s' % (core.get_hostname(), int(core.config['condor-ce.view-port']))
        try:
            src = core.to_str(urlopen(view_url).read())
            core.log_message(src)
        except EnvironmentError as err:
            debug_file = '/var/log/condor-ce/CEViewLog'
            debug_contents = 'Contents of %s\n%s\n' % (debug_file, '=' * 20)
            try:
                debug_contents += files.read(debug_file, True)
            except EnvironmentError:
                debug_contents += 'Failed to read %s\n' % debug_file
            core.log_message(debug_contents)
            self.fail('Could not reach HTCondor-CE View at %s: %s' % (view_url, err))
        self.assertTrue(re.search(r'HTCondor-CE Overview', src), 'Failed to find expected CE View contents')
        core.config['condor-ce.view-listening'] = True

    def test_08_config_val(self):
        command = ('condor_ce_config_val', '-dump')
        core.check_system(command, 'condor_ce_config_val as non-root', user=True)

    def test_09_ceview_agis_compat(self):
        self.general_requirements()
        self.skip_bad_unless(core.config['condor-ce.view-listening'], "CEView required")
        view_url = "http://%s:%s/json/agis-compat" % (core.get_hostname(), core.config["condor-ce.view-port"])
        try:
            data = json.load(urlopen(view_url))
        except EnvironmentError as err:
            self.fail("Failed to download CEView data at %s: %s" % (view_url, err))
        except Exception as err:
            self.fail("Error parsing CEView data at %s: %s" % (view_url, err))
        if "failed_ces" not in data:
            core.log_message("json data: %s" % json.dumps(data))
            self.fail("failed_ces missing from CEView data - see log for dump")
        if len(data["failed_ces"]) > 0:
            core.log_message("json data: %s" % json.dumps(data))
            self.fail("some failed_ces - see log for dump")
