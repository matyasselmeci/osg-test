import osgtest.library.core as core
import osgtest.library.files as files
import osgtest.library.osgunittest as osgunittest
import osgtest.library.voms as voms


class TestStopVOMS(osgunittest.OSGTestCase):

    # ==========================================================================

    def test_02_restore_vomses(self):
        voms.skip_ok_unless_can_make_proxy()

        voms.destroy_lsc(core.config['voms.vo'])
        files.restore('/etc/vomses', 'voms')
