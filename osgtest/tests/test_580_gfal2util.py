import os
import osgtest.library.core as core
import osgtest.library.files as files
import osgtest.library.osgunittest as osgunittest
import socket
import tempfile

class TestGFAL2Util(osgunittest.OSGTestCase):

    __data_path = '/usr/share/osg-test/test_gridftp_data.txt'
    __hostname = socket.getfqdn()


    def setUp(self):
        self.skip_ok_unless(core.state['proxy.valid'] or core.state['voms.got-proxy'], "No proxy")
        core.skip_ok_unless_installed('gfal2-util-scripts', 'gfal2-plugin-file')
        core.skip_ok_unless_one_installed('python2-gfal2-util', 'python3-gfal2-util')

    def get_gftp_url_base(self):
        return 'gsiftp://%s/' % (TestGFAL2Util.__hostname)

    def setup_temp_paths(self):
        TestGFAL2Util.__temp_dir = tempfile.mkdtemp()
        TestGFAL2Util.__remote_path = TestGFAL2Util.__temp_dir + '/gfal2util_put_copied_file.txt'
        TestGFAL2Util.__local_path = TestGFAL2Util.__temp_dir + '/gfal2util_get_copied_file.txt'
        os.chmod(TestGFAL2Util.__temp_dir,0o777)

    def test_01_copy_server_to_local_gfal2_gftp_util(self):
         core.skip_ok_unless_installed('globus-gridftp-server-progs', 'gfal2-plugin-gridftp')
         self.skip_ok_unless(core.state['gridftp.running-server'], 'gridftp server not running')
         self.setup_temp_paths()
         command = ('gfal-copy', '-v', '-f', self.get_gftp_url_base() + TestGFAL2Util.__data_path, 'file://' + TestGFAL2Util.__local_path)
         core.check_system(command, "gfal2-util copy from  GridFTP URL to local", user='vdttest')
         file_copied = os.path.exists(TestGFAL2Util.__local_path)
         self.assertTrue(file_copied, 'Copied file missing')

    def test_02_copy_local_to_server_gfal2_util(self):
        core.skip_ok_unless_installed('globus-gridftp-server-progs', 'gfal2-plugin-gridftp')
        self.skip_ok_unless(core.state['gridftp.running-server'], 'gridftp server not running')
        file_not_created = not os.path.exists(TestGFAL2Util.__remote_path)
        self.assertTrue(file_not_created, 'to be copied files does not exist')
        command = ('gfal-copy', '-v', 'file://' + TestGFAL2Util.__local_path, self.get_gftp_url_base() + TestGFAL2Util.__remote_path)
        core.check_system(command, "gfal2-util copy from  local to GridFTP URL", user='vdttest')
        file_copied = os.path.exists(TestGFAL2Util.__remote_path)
        self.assertTrue(file_copied, 'Copied file missing')

    def test_03_remove_server_file_gfal2_util_gftp(self):
        core.skip_ok_unless_installed('globus-gridftp-server-progs', 'gfal2-plugin-gridftp')
        self.skip_ok_unless(core.state['gridftp.running-server'], 'gridftp server not running')
        command = ('gfal-rm', '-v', self.get_gftp_url_base() + TestGFAL2Util.__remote_path)
        core.check_system(command, "gfal2-util remove, URL file", user='vdttest')
        file_removed = not os.path.exists(TestGFAL2Util.__remote_path)
        self.assertTrue(file_removed, 'Copied file still exists')
        files.remove(TestGFAL2Util.__remote_path)
        files.remove(TestGFAL2Util.__local_path)
