import os
import time
from datetime import date

import osgtest.library.core as core
import osgtest.library.files as files
import osgtest.library.osgunittest as osgunittest
import osgtest.library.service as service

class TestStartPBS(osgunittest.OSGTestCase):

    pbs_config = """
create queue batch queue_type=execution
set queue batch started=true
set queue batch enabled=true
set queue batch resources_default.nodes=1
set queue batch resources_default.walltime=3600
set server default_queue=batch
set server keep_completed = 600
set server job_nanny = True
set server scheduling=true
set server acl_hosts += *
set server acl_host_enable = True
"""
    required_rpms = ['torque',
                     'torque-mom',
                     'torque-server',
                     'torque-scheduler',
                     'torque-client', # for qmgr
                     'munge']


    def test_01_start_mom(self):
        core.state['pbs_mom.started-service'] = False
        core.skip_ok_unless_installed(*self.required_rpms, by_dependency=True)
        self.skip_ok_if(service.is_running('pbs_mom'), 'PBS mom already running')

        core.config['torque.mom-config'] = '/var/lib/torque/mom_priv/config'
        files.write(core.config['torque.mom-config'],
                    "$pbsserver %s\n" % core.get_hostname(),
                    owner='pbs')
        core.config['torque.mom-layout'] = '/var/lib/torque/mom_priv/mom.layout'
        files.write(core.config['torque.mom-layout'],
                    "nodes=0",
                    owner='pbs')
        service.check_start('pbs_mom')

    def test_02_start_pbs_sched(self):
        core.state['pbs_sched.started-service'] = False
        core.skip_ok_unless_installed(*self.required_rpms, by_dependency=True)
        self.skip_ok_if(service.is_running('pbs_sched'), 'PBS sched already running')
        service.check_start('pbs_sched')

    def test_03_start_trqauthd(self):
        core.state['trqauthd.started-service'] = False
        core.config['torque.pbs-servername-file'] = '/var/lib/torque/server_name'
        core.skip_ok_unless_installed(*self.required_rpms, by_dependency=True)
        self.skip_ok_if(service.is_running('trqauthd'), 'trqauthd is already running')
        # set hostname as servername instead of localhost
        # config required before starting trqauthd
        files.write(core.config['torque.pbs-servername-file'],
                    "%s" % core.get_hostname(),
                    owner='pbs')
        service.check_start('trqauthd')

    def test_04_configure_pbs(self):
        core.config['torque.pbs-nodes-file'] = '/var/lib/torque/server_priv/nodes'
        core.config['torque.pbs-serverdb'] = '/var/lib/torque/server_priv/serverdb'
        core.skip_ok_unless_installed(*self.required_rpms, by_dependency=True)
        self.skip_bad_unless(service.is_running('trqauthd'), 'pbs_server requires trqauthd')
        self.skip_ok_if(service.is_running('pbs_server'), 'pbs server already running')

        files.preserve(core.config['torque.pbs-serverdb'], 'pbs')
        if not os.path.exists(core.config['torque.pbs-serverdb']):
            command = ('/usr/sbin/pbs_server -d /var/lib/torque -t create -f && '
                       'sleep 10 && /usr/bin/qterm')
            stdout, stderr, fail = core.check_system(command, 'create initial pbs serverdb config', shell=True)
            self.assertNotIn("error", stdout + "\n" + stderr, fail)

        # This gets wiped if we write it before the initial 'service pbs_server create'
        # However, this file needs to be in place before the service is started so we
        # restart the service after 'initial configuration'
        files.write(core.config['torque.pbs-nodes-file'], # add the local node as a compute node
                    "%s np=1 num_node_boards=1\n" % core.get_hostname(),
                    owner='pbs')

    def test_05_start_pbs(self):
        core.state['pbs_server.started-service'] = False
        core.state['torque.nodes-up'] = False

        core.skip_ok_unless_installed(*self.required_rpms, by_dependency=True)
        self.skip_bad_unless(service.is_running('trqauthd'), 'pbs_server requires trqauthd')
        self.skip_ok_if(service.is_running('pbs_server'), 'pbs server already running')

        server_log = '/var/log/torque/server_logs/' + date.today().strftime('%Y%m%d')
        try:
            server_log_stat = os.stat(server_log)
        except OSError:
            server_log_stat = None

        service.check_start('pbs_server')

        # Wait until the server is up before writing the rest of the config
        core.monitor_file(server_log, server_log_stat, '.*Server Ready.*', 60.0)
        core.check_system("echo '%s' | qmgr %s" % (self.pbs_config, core.get_hostname()),
                          "Configuring pbs server",
                          shell=True)

        # wait up to 5 minutes for the server to recognize the node
        start_time = time.time()
        while (time.time() - start_time) < 600:
            command = ('/usr/bin/qnodes', '-s', core.get_hostname())
            stdout, stderr, fail = core.check_system(command, 'Get pbs node info')
            output = stdout + "\n" + stderr
            self.assertNotIn("error", output, fail)
            if "state = free" in output:
                core.state['torque.nodes-up'] = True
                break
        if not core.state['torque.nodes-up']:
            self.fail('PBS nodes not coming up')
