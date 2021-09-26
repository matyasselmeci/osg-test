import osgtest.library.core as core
import osgtest.library.files as files
import osgtest.library.osgunittest as osgunittest


class TestStopCvmfs(osgunittest.OSGTestCase):

    def test_01_stop_cvmfs(self):
        core.skip_ok_unless_installed('cvmfs')
        self.skip_ok_unless(core.state['cvmfs.started-server'], 'did not start server')

        try:
            for temp_dir in core.config['cvmfs.debug-dirs']:
                command = ('umount', temp_dir)
                core.check_system(command, 'Manual cvmfs unmount failed')
                files.remove(temp_dir, force=True)
        except KeyError:
            pass  # tempdir was never created

        stdout, stderr, fail = core.check_system(('cvmfs_config', 'umount'), 'Stop Cvmfs server')
        self.assertNotIn("FAILED", stdout + "\n" + stderr, fail)

        files.restore("/etc/fuse.conf", "cvmfs")
        files.restore("/etc/auto.master", "cvmfs")
        files.restore("/etc/cvmfs/default.local", "cvmfs")
        files.restore("/etc/sysconfig/autofs", "cvmfs")
