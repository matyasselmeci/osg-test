import re

from collections import OrderedDict
import osgtest.library.core as core
import osgtest.library.yum as yum
import osgtest.library.osgunittest as osgunittest

class TestInstall(osgunittest.OSGTestCase):

    def test_01_yum_repositories(self):
        pre = ('rpm', '--verify', '--nomd5', '--nosize', '--nomtime')
        core.check_system(pre + ('epel-release',), 'Verify epel-release')
        osg_release_rpm = core.osg_release_rpm()
        self.assertIsNotNone(osg_release_rpm, 'No osg-release RPM installed')
        osg_release_rpm: str  # let the type checker know what's up
        core.check_system(pre + (osg_release_rpm,), f'Verify osg-release ({osg_release_rpm})')

        original_release = core.osg_release().version
        if '.' not in original_release:  # 23, 24, etc.
            original_release = f'{original_release}-main'
        core.config['install.original-release-ver'] = original_release

    def test_02_install_packages(self):
        core.state['install.success'] = False
        core.state['install.installed'] = []
        core.state['install.updated'] = []
        core.state['install.replace'] = []
        core.state['install.orphaned'] = []
        core.state['install.os_updates'] = []

        # Install packages
        core.state['install.transaction_ids'] = set()
        fail_msg = ''
        pkg_repo_dict = OrderedDict((x, core.options.extrarepos) for x in core.options.packages)

        # HACK: Install x509-scitokens-issuer-client out of development (SOFTWARE-3649)
        x509_scitokens_issuer_packages = ['xrootd-scitokens', 'osg-tested-internal']
        for pkg in x509_scitokens_issuer_packages:
            if pkg in pkg_repo_dict:
                pkg_repo_dict["x509-scitokens-issuer-client"] = ["osg-development"]
                break

        for pkg, repos in pkg_repo_dict.items():
            # Do not try to re-install packages
            if core.rpm_is_installed(pkg):
                continue

            # Attempt installation
            command = ['yum', '-y']
            command += ['--enablerepo=%s' % x for x in repos]
            command += ['install', pkg]

            retry_fail, _, stdout, _ = yum.retry_command(command)
            if retry_fail == '':   # the command succeeded
                core.state['install.transaction_ids'].add(yum.get_transaction_id())
                verify_dependency(pkg)
                yum.parse_output_for_packages(stdout)

            fail_msg += retry_fail

        if fail_msg:
            self.fail(fail_msg)
        core.state['install.success'] = True

    def test_03_update_osg_release(self):
        core.state['install.release-updated'] = False
        if not core.options.updaterelease:
            return

        self.skip_bad_unless(core.state['install.success'], 'Install did not succeed')

        update_release = core.options.updaterelease
        self.assertTrue(re.match(r'\d+[.]?\d+$', update_release), "Unrecognized updaterelease format")

        if '.' not in update_release:  # 23, 24, etc.
            update_release = f'{update_release}-main'
        if core.is_x86_64_v2():
            rpm_name = f"osg-{update_release}-el{core.el_release()}-release-latest.x86_64_v2.rpm"
        else:
            rpm_name = f"osg-{update_release}-el{core.el_release()}-release-latest.rpm"
        rpm_url = f"https://repo.osg-htc.org/osg/{update_release}/{rpm_name}"
        if core.el_release() == 8:
            # https://bugzilla.redhat.com/show_bug.cgi?id=2036434
            core.check_system(["rpm", "-e", "--nodeps", core.osg_release_rpm()], "Remove old osg-release")
            core.check_system(["yum", "install", "-y", rpm_url], "Install new version of osg-release")
        else:
            command = ['yum', '-y', 'swap', core.osg_release_rpm(), rpm_url]
            core.check_system(command, 'Install new version of osg-release')

        core.config['yum.clean_repos'] = ['osg'] + core.options.updaterepos
        yum.clean(*core.config['yum.clean_repos'])

        # If update repos weren't specified, just use osg-release
        if not core.options.updaterepos:
            core.options.updaterepos = ['osg']

        core.state['install.release-updated'] = True
        core.osg_release(update_state=True)

    def test_04_update_packages(self):
        if not (core.options.updaterepos and core.state['install.installed']):
            return

        self.skip_bad_unless(core.state['install.success'], 'Install did not succeed')

        # Update packages
        command = ['yum', 'update', '-y']
        for repo in core.options.updaterepos:
            command.append('--enablerepo=%s' % repo)
        fail_msg, status, stdout, stderr = yum.retry_command(command)
        yum.parse_output_for_packages(stdout)

        if fail_msg:
            self.fail(fail_msg)
        else:
            core.state['install.transaction_ids'].add(yum.get_transaction_id())


def verify_dependency(dep):
    """Assert that at least one installed rpm provides the given virtual
    dependency, and verify the first rpm that does."""

    rpms = core.dependency_installed_rpms(dep)

    assert rpms, "Dependency '%s' not installed" % dep

    pkg = rpms[0]

    command = ('rpm', '--verify', pkg)
    core.check_system(command, 'Verify %s' % pkg)
