import os
import osgtest.library.core as core
from cagen import CA, certificate_info
import osgtest.library.files as files
import osgtest.library.osgunittest as osgunittest
from osgtest.library.voms import VONAME

class TestCert(osgunittest.OSGTestCase):

    def test_01_install_ca(self):
        core.state['certs.ca_created'] = False
        core.config['certs.test-ca'] = '/etc/grid-security/certificates/OSG-Test-CA.pem'
        self.skip_ok_if(os.path.exists(core.config['certs.test-ca']), 'OSG TEST CA already exists')
        core.config['certs.ca-subject'] = '/DC=org/DC=opensciencegrid/C=US/O=OSG Software/CN=OSG Test CA'
        CA(core.config['certs.ca-subject'])
        core.state['certs.ca_created'] = True

    def test_02_install_host_cert(self):
        core.state['certs.hostcert_created'] = False
        grid_dir = '/etc/grid-security/'
        core.config['certs.hostcert'] = os.path.join(grid_dir, 'hostcert.pem')
        core.config['certs.hostkey'] = os.path.join(grid_dir, 'hostkey.pem')

        self.skip_ok_unless(os.path.exists(core.config['certs.test-ca']), "OSG Test CA doesn't exist")

        if core.options.hostcert and not os.path.exists(core.config['certs.hostcert']):
            test_ca = CA.load(core.config['certs.test-ca'])
            test_ca.hostcert()
            test_ca.voms(VONAME)
            core.state['certs.hostcert_created'] = True

    def test_02a_print_host_cert(self):
        hostcert = core.config.get('certs.hostcert', '')
        self.skip_ok_unless(hostcert and os.path.exists(hostcert), "Host cert does not exist")
        core.check_system(
            ['openssl', 'x509', '-in', core.config['certs.hostcert'], '-text', '-noout'],
            message="Printing host cert info with openssl"
        )

    def test_03_generate_user_cert(self):
        core.state['general.user_cert_created'] = False
        core.state['system.wrote_mapfile'] = False

        if core.options.skiptests:
            core.skip('no user needed')
            return

        self.skip_bad_unless(core.state['user.verified'], "User doesn't exist, has HOME=/, or is missing HOME")

        # Set up certificate
        globus_dir = os.path.join(core.state['user.pwd'].pw_dir, '.globus')
        core.state['user.cert_path'] = os.path.join(globus_dir, 'usercert.pem')
        core.state['user.key_path'] = os.path.join(globus_dir, 'userkey.pem')
        test_ca = CA.load(core.config['certs.test-ca'])
        if not os.path.exists(core.state['user.cert_path']):
            test_ca.usercert(core.options.username, core.options.password)
            core.state['general.user_cert_created'] = True

        (core.config['user.cert_subject'],
         core.config['user.cert_issuer']) = certificate_info(core.state['user.cert_path'])

        # Add user to mapfile
        files.append(core.config['system.mapfile'], '"%s" %s\n' %
                     (core.config['user.cert_subject'], core.state['user.pwd'].pw_name),
                     owner='user')
        core.state['system.wrote_mapfile'] = True
        os.chmod(core.config['system.mapfile'], 0o644)
