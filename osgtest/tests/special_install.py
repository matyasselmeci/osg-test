import re

from collections import OrderedDict
import osgtest.library.core as core
import osgtest.library.yum as yum
import osgtest.library.osgunittest as osgunittest

class TestInstall(osgunittest.OSGTestCase):

    def test_01_yum_repositories(self):
        pre = ('rpm', '--verify', '--nomd5', '--nosize', '--nomtime')
        core.check_system(pre + ('epel-release',), 'Verify epel-release')
        # If osg-release isn't installed, try osg-release-itb
        try:
            core.check_system(pre + ('osg-release',), 'Verify osg-release')
        except AssertionError:
            core.check_system(pre + ('osg-release-itb',), 'Verify osg-release + osg-release-itb')
        core.config['install.original-release-ver'] = core.osg_release().version

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
        pkg_repo_dict.setdefault("binutils", [])  # for strings(1)

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
                if not pkg.startswith("/"):
                    # ^^ rpm --verify doesn't work if you asked for a file instead of a package
                    command = ('rpm', '--verify', pkg)
                    core.check_system(command, 'Verify %s' % (pkg))
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

        command = ['rpm', '-e', 'osg-release']
        core.check_system(command, 'Erase osg-release')

        self.assert_(re.match('\d+\.\d+', core.options.updaterelease), "Unrecognized updaterelease format")
        rpm_url = 'https://repo.opensciencegrid.org/osg/' + core.options.updaterelease + '/osg-' + \
                  core.options.updaterelease + '-el' + str(core.el_release()) + '-release-latest.rpm'
        command = ['rpm', '-Uvh', rpm_url]
        core.check_system(command, 'Update osg-release')

        core.config['yum.clean_repos'] = ['osg'] + core.options.updaterepos
        yum.clean(*core.config['yum.clean_repos'])

        # If update repos weren't specified, just use osg-release
        if not core.options.updaterepos:
            core.options.updaterepos = ['osg']

        core.state['install.release-updated'] = True
        core.osg_release(update_state=True)

    # TODO: Drop this once we stop doing 3.3->3.4 upgrade tests
    def test_04_remove_bestman2_server_dep_libs(self):
        if core.options.updaterelease != "3.4":
            return

        # bestman2 and jetty have been dropped from OSG 3.4. bestman2-server-dep-libs requires a version of jetty-http
        # less than what's available in EPEL, which causes `yum update` fails. We no longer care about bestman2 so we
        # can just remove the offending package
        command = ['yum', '-y', 'remove', 'bestman2-server-dep-libs']
        core.check_system(command, "Failed to remove bestman2-server-dep-libs")

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
