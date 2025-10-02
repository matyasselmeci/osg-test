import cagen

import osgtest.library.core as core
import osgtest.library.files as files
import osgtest.library.voms as voms
import osgtest.library.osgunittest as osgunittest

class TestStartVOMS(osgunittest.OSGTestCase):

    def test_01_config_certs(self):
        core.config['certs.vomscert'] = '/etc/grid-security/voms/vomscert.pem'
        core.config['certs.vomskey'] = '/etc/grid-security/voms/vomskey.pem'

    def test_04_config_voms(self):
        core.config['voms.vo'] = voms.VONAME
        core.config['voms.lock-file'] = '/var/lock/subsys/voms.osgtestvo'
        # The DB created by voms-admin would have the user 'admin-osgtestvo',
        # but the voms_install_db script provided by voms-server does not
        # like usernames with '-' in them.
        core.config['voms.dbusername'] = 'voms_' + core.config['voms.vo']

    def test_08_advertise(self):
        voms.skip_ok_unless_can_make_proxy()

        voms.advertise_lsc(core.config['voms.vo'], core.config['certs.hostcert'])
        files.preserve('/etc/vomses', owner='voms')
        voms.advertise_vomses(core.config['voms.vo'], core.config['certs.hostcert'])

        core.system('ls -ldF /etc/*vom*', shell=True)
        core.system(('find', '/etc/grid-security/vomsdir', '-ls'))
