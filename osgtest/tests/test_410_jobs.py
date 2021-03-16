#pylint: disable=C0301
#pylint: disable=R0201
#pylint: disable=R0904

import os
import shutil
import tempfile

import osgtest.library.core as core
import osgtest.library.service as service
import osgtest.library.osgunittest as osgunittest

class TestRunJobs(osgunittest.OSGTestCase):

    def verify_job_environment(self, output):
        expected_env = {'JOB_ENV': 'vdt',
                        'LOCAL_JOB_ENV': 'osg'}
        env = core.parse_env_output(output)
        self.assertSubsetOf(expected_env, env, 'Could not verify OSG job environment')

    def run_job_in_tmp_dir(self, command, message, verify_environment=True):
        tmp_dir = tempfile.mkdtemp()
        old_cwd = os.getcwd()
        os.chdir(tmp_dir)
        os.chmod(tmp_dir, 0o777)

        try:
            stdout = core.check_system(command, message, user=True, timeout=600)[0]
        except osgunittest.TimeoutException:
            self.fail("Job failed to complete in 10 minute window")

        if verify_environment:
            self.verify_job_environment(stdout)

        os.chdir(old_cwd)
        shutil.rmtree(tmp_dir)

    def test_01_condor_run_pbs(self):
        core.skip_ok_unless_installed('condor', 'blahp')
        core.skip_ok_unless_installed('torque-mom', 'torque-server', 'torque-scheduler', by_dependency=True)
        self.skip_bad_unless(core.state['jobs.env-set'], 'job environment not set')
        self.skip_bad_unless(service.is_running('condor'), 'condor not running')
        self.skip_bad_if(core.system(["/usr/bin/condor_q"])[0] != 0, 'condor_q failed')
        self.skip_bad_unless(service.is_running('pbs_server'), 'pbs not running')

        command = ('condor_run', '-u', 'grid', '-a', 'grid_resource=pbs', '-a', 'periodic_remove=JobStatus==5',
                   '/bin/env')

        # Figure out whether the installed BLAHP package is the same as or later
        # than "blahp-1.18.11.bosco-4.osg*" (in the RPM sense), because it's the
        # first build in which the job environments are correctly passed to PBS.
        blahp_pbs_has_env_vars = core.PackageVersion('blahp') >= '1.18.11.bosco-4.osg'

        self.run_job_in_tmp_dir(command, 'condor_run a Condor job', verify_environment=blahp_pbs_has_env_vars)

    def test_02_condor_ce_run_condor(self):
        core.skip_ok_unless_installed('htcondor-ce', 'htcondor-ce-client', 'htcondor-ce-condor', 'condor')

        self.skip_bad_unless(service.is_running('condor-ce'), 'ce not running')
        self.skip_bad_if(core.system(["/usr/bin/condor_ce_q"])[0] != 0, 'condor_ce_q failed')
        self.skip_bad_unless(service.is_running('condor'), 'condor not running')
        self.skip_bad_if(core.system(["/usr/bin/condor_q"])[0] != 0, 'condor_q failed')
        self.skip_bad_unless(core.state['jobs.env-set'], 'job environment not set')
        self.skip_bad_unless(core.state['proxy.valid'] or core.state['token.condor_write_created'],
                             'requires a scitoken or a proxy')

        command = ['condor_ce_run', '-r', '%s:9619' % core.get_hostname(), '/bin/env']
        if core.state['token.condor_write_created']:
            command.insert(0, f"_condor_SCITOKENS_FILE={core.config['token.condor_write']}")
        self.run_job_in_tmp_dir(command, 'condor_ce_run a Condor job')
