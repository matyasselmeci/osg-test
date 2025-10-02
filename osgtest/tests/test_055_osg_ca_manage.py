import glob
import os

import osgtest.library.core as core
import osgtest.library.osgunittest as osgunittest


class TestOsgCaManage(osgunittest.OSGTestCase):

    def test_01_setup_ca(self):
        """Test that a CA can be installed via `osg-ca-manage setupCA`"""
        core.skip_ok_unless_installed('osg-ca-scripts')
        command = ('osg-ca-manage', 'setupCA', '--location', 'root', '--url', 'osg')
        status, stdout, stderr = core.system(command)
        fail = core.diagnose('Run osg-ca-manage setupCA', command, status, stdout, stderr)

        self.assertEqual(status, 0, fail)
        pem_count = len(glob.glob('/etc/grid-security/certificates/*.pem'))
        self.assertTrue(pem_count > 0, "No certificates installed")

    def test_02_verify_ca(self):
        """Verify CA installation via `osg-ca-manage verify`"""
        core.skip_ok_unless_installed('osg-ca-scripts')
        command = ('osg-ca-manage', 'verify')
        status, stdout, stderr = core.system(command)
        fail = core.diagnose('Run osg-ca-manage verify', command, status, stdout, stderr)
        
        # Nothing to confirm besides success of verify command
        self.assertEqual(status, 0, fail)
