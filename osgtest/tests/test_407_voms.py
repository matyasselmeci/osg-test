import os
import pwd
import re

import osgtest.library.core as core
import osgtest.library.osgunittest as osgunittest
import osgtest.library.voms as voms


class TestVOMS(osgunittest.OSGTestCase):

    def proxy_info(self, msg):
        self.skip_bad_unless(core.state['voms.got-proxy'], 'no proxy')

        command = ('voms-proxy-info', '-all')
        stdout = core.check_system(command, 'Run voms-proxy-info', user=True)[0]
        self.assertTrue(('/%s/Role=NULL' % (core.config['voms.vo'])) in stdout, msg)

    def test_00_setup(self):
        core.state.setdefault('proxy.valid', False)

    def test_06_voms_proxy_direct(self):
        core.state['voms.got-proxy'] = False
        core.skip_ok_unless_installed("voms-clients-cpp", by_dependency=True)
        # ^^ voms-proxy-direct is only in (our) voms-clients-cpp

        voms.proxy_direct()
        core.state['voms.got-proxy'] = True

    def test_07_voms_proxy_info(self):
        voms.skip_ok_unless_can_make_proxy()
        self.proxy_info('third voms-proxy-info output is ok')

    def test_08_voms_proxy_check(self):
        """
        Check generated proxies to make sure that they use the same signing
        algorithm as the certificate
        """
        voms.skip_ok_unless_can_make_proxy()
        self.skip_bad_unless(core.state['voms.got-proxy'], 'no proxy')

        pwd_entry = pwd.getpwnam(core.options.username)
        cert_path = os.path.join(pwd_entry.pw_dir, '.globus', 'usercert.pem')
        # Note: We're only looking for the "Signature Algorithm" line which has the same output format
        # regardless of openssl version.
        command = ['openssl', 'x509', '-in', cert_path, '-text']
        signature_re = re.compile(r'Signature Algorithm:\s+(\w+)\s')
        stdout = core.check_system(command, 'Check X.509 certificate algorithm', user=True)[0]
        match = signature_re.search(stdout)
        if match is None:
            self.fail("Can't find user cert's signing algorithm")
        cert_algorithm = match.group(1)
        command[3] = os.path.join('/', 'tmp', "x509up_u%s" % pwd_entry[2])
        stdout = core.check_system(command, 'Check X.509 proxy algorithm', user=True)[0]
        match = signature_re.search(stdout)
        if match is None:
            self.fail("Can't find proxy's signing algorithm")
        proxy_algorithm = match.group(1)
        self.assertEqual(cert_algorithm, proxy_algorithm)

        core.state['proxy.valid'] = True

    def test_09_basic_grid_proxy(self):
        """
        Use voms-proxy-init to create a basic grid proxy (without VOMS attributes)
        if we don't already have one.  We may need this for tests in other modules.
        """
        core.skip_ok_unless_installed("voms-clients", by_dependency=True)
        # ^^ not using voms.can_make_proxy - any voms-clients implementation can make a basic proxy
        self.skip_ok_if(core.state['proxy.valid'], "Already have a proxy")
        self.skip_ok_unless(core.state.get('user.verified', False), "No user")
        self.skip_ok_unless(os.path.isfile(core.state['user.cert_path']) and
                            os.path.isfile(core.state['user.key_path']),
                            "No user cert/key")

        password = core.options.password + '\n'
        core.check_system(['voms-proxy-init', '-rfc'], 'Run voms-proxy-init w/o VO', user=True, stdin=password)
        core.check_system(['voms-proxy-info'], "Check resulting proxy", user=True)
        core.state['proxy.valid'] = True
        core.state['voms.got-proxy'] = False  # got a proxy but without VOMS attrs
