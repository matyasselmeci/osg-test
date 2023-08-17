import os
import pwd

import osgtest.library.core as core
import osgtest.library.files as files
import osgtest.library.osgunittest as osgunittest
import osgtest.library.xrootd as xrootd


ERR_AUTH_FAIL = 52
ERR_PERMISSION_DENIED = 54

HOSTNAME = core.get_hostname() or "localhost"


def xrootd_record_failure(fn):
    """Decorator for xrootd tests that sets the core.state['xrootd.had-failures'] flag
    if there were any test failures.

    """
    def inner(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (osgunittest.OkSkipException, osgunittest.BadSkipException, osgunittest.ExcludedException):
            raise
        except AssertionError:
            core.state['xrootd.had-failures'] = True
            raise
    return inner


def xroot_url(path):
    if path.startswith(xrootd.ROOTDIR):
        path = path[len(xrootd.ROOTDIR):]
    return f"xroot://{HOSTNAME}/{path}"


def https_url(path, token=""):
    if path.startswith(xrootd.ROOTDIR):
        path = path[len(xrootd.ROOTDIR):]
    url = f"https://{HOSTNAME}:1094/{path}"
    if token:
        url += f"?authz=Bearer%20{token}"
    return url


class TestXrootd(osgunittest.OSGTestCase):

    __data_path = '/usr/share/osg-test/test_gridftp_data.txt'
    __fuse_path = '/mnt/xrootd_fuse_test'

    public_copied_file = f"{xrootd.ROOTDIR}/{{public_subdir}}/public_copied_file.txt"
    public_copied_file2 = f"{xrootd.ROOTDIR}/{{public_subdir}}/public_copied_file2.txt"
    user_copied_file_gsi = f"{xrootd.ROOTDIR}/{{user_subdir}}/user_copied_file_gsi.txt"
    user_copied_file_scitoken = f"{xrootd.ROOTDIR}/{{user_subdir}}/user_copied_file_scitoken.txt"
    rootdir_copied_file = f"{xrootd.ROOTDIR}/rootdir_copied_file.txt"
    vo_copied_file = f"{xrootd.ROOTDIR}/{{vo_subdir}}/vo_copied_file.txt"
    public_file_to_download = f"{xrootd.ROOTDIR}/{{public_subdir}}/public_file_to_download.txt"
    user_file_to_download = f"{xrootd.ROOTDIR}/{{user_subdir}}/user_file_to_download.txt"
    vo_file_to_download = f"{xrootd.ROOTDIR}/{{vo_subdir}}/vo_file_to_download.txt"

    download_temp = f"/tmp/osgtest-download-{os.getpid()}"

    def setUp(self):
        self.skip_ok_if(core.rpm_is_installed("xcache"), "xcache configs conflict with xrootd tests")
        core.skip_ok_unless_installed("xrootd", "xrootd-client", "osg-xrootd-standalone", by_dependency=True)
        self.skip_ok_unless(core.state['xrootd.is-configured'], "xrootd is not configured")
        self.skip_bad_unless_running(core.config['xrootd_service'])

    def skip_unless_security(self, security):
        if security not in core.config['xrootd.security']:
            self.skip_ok("Not testing xrootd with %s" % security)
        if security == "GSI":
            self.skip_bad_unless(core.state['proxy.valid'], "no valid proxy")
        elif security == "SCITOKENS":
            self.skip_bad_unless(core.state['token.xrootd_contents'], "xrootd scitoken is missing or empty")
            self.skip_bad_unless(os.path.isfile(core.config['token.xrootd']), "xrootd scitoken file is missing")
        elif security == "VOMS":
            self.skip_bad_unless(core.state['voms.got-proxy'], "no valid proxy with voms attributes")

    def test_00_setup(self):
        public_subdir = core.config['xrootd.public_subdir']
        user_subdir = core.config['xrootd.user_subdir']
        vo_subdir = core.config['xrootd.vo_subdir']
        for var in [
            "public_copied_file",
            "public_copied_file2",
            "user_copied_file_gsi",
            "user_copied_file_scitoken",
            "rootdir_copied_file",
            "vo_copied_file",
            "public_file_to_download",
            "user_file_to_download",
            "vo_file_to_download",
        ]:
            setattr(TestXrootd, var, getattr(TestXrootd, var).format(**locals()))

        for file_to_download in [TestXrootd.public_file_to_download,
                                 TestXrootd.user_file_to_download,
                                 TestXrootd.vo_file_to_download]:
            file_text = f"This is some test data for an xrootd test in {file_to_download}."
            with open(file_to_download, "w") as f:
                f.write(file_text)
            os.chown(file_to_download, core.state['user.uid'], core.state['user.gid'])
            os.chmod(file_to_download, 0o644)

    @xrootd_record_failure
    def test_03a_xrdcp_upload_gsi_authenticated(self):
        self.skip_unless_security("GSI")
        command = ('xrdcp', '--debug', '2', TestXrootd.__data_path, xroot_url(TestXrootd.user_copied_file_gsi))
        with core.no_bearer_token(core.options.username):
            core.check_system(command, "xrdcp upload to user dir with GSI auth", user=True)
        self.assertTrue(os.path.exists(TestXrootd.user_copied_file_gsi), "Uploaded file missing")

    @xrootd_record_failure
    def test_03b_xrdcp_upload_scitoken_authenticated(self):
        self.skip_unless_security("SCITOKENS")
        xrootd_url = xroot_url(TestXrootd.user_copied_file_scitoken)
        command = ('xrdcp', '--force', '--debug', '2', TestXrootd.__data_path, xrootd_url)
        with core.no_x509(core.options.username):
            # TODO: Passing token contents with $BEARER_TOKEN or having the token be in /tmp/bt_u$UID is currently
            # broken (token is not found/not used).  Using $BEARER_TOKEN_FILE or having the token be in
            # $X509_RUNTIME_DIR/bt_u$UID works.  Bug report forthcoming.
            with core.environ_context({"BEARER_TOKEN": core.state['token.xrootd_contents'], "BEARER_TOKEN_FILE": None}):
                message = "xrdcp upload to user dir with scitoken in BEARER_TOKEN"
                expected_exit = 0
                if core.PackageVersion("xrootd-libs") <= "5.3.2":
                    message += " (expected failure)"
                    expected_exit = ERR_AUTH_FAIL
                core.check_system(command, message, exit=expected_exit, user=True)

            with core.environ_context({"BEARER_TOKEN_FILE": core.config['token.xrootd'], "BEARER_TOKEN": None}):
                message = "xrdcp upload to user dir with scitoken file in BEARER_TOKEN_FILE"
                expected_exit = 0
                core.check_system(command, message, exit=expected_exit, user=True)

            # TODO: Test token discovery at $X509_RUNTIME_DIR/bt_u$UID and /tmp/bt_u$UID
        self.assertTrue(os.path.exists(TestXrootd.user_copied_file_scitoken), "Uploaded file missing")

    @xrootd_record_failure
    def test_03c_xrdcp_upload_voms_authenticated(self):
        self.skip_unless_security("VOMS")
        xrootd_url = xroot_url(TestXrootd.vo_copied_file)
        command = ('xrdcp', '--force', '--debug', '2', TestXrootd.__data_path, xrootd_url)
        with core.no_bearer_token(core.options.username):
            core.check_system(command, "xrdcp upload to vo dir with VOMS auth", user=True)
        self.assertTrue(os.path.exists(TestXrootd.vo_copied_file), "Uploaded file missing")

    @xrootd_record_failure
    def test_04a_xrdcp_upload_gsi_authenticated_denied(self):
        self.skip_unless_security("GSI")
        try:
            command = ('xrdcp', '--debug', '2', TestXrootd.__data_path, xroot_url(TestXrootd.rootdir_copied_file))
            with core.no_bearer_token(core.options.username):
                core.check_system(command, "xrdcp upload to dir w/o write access (should be denied)", exit=ERR_PERMISSION_DENIED, user=True)
            self.assertFalse(os.path.exists(TestXrootd.rootdir_copied_file), "Uploaded file wrongly present")
        finally:
            files.remove(TestXrootd.rootdir_copied_file)

    @xrootd_record_failure
    def test_04b_xrdcp_upload_scitoken_authenticated_denied(self):
        self.skip_unless_security("SCITOKENS")
        try:
            with core.no_x509(core.options.username), core.environ_context({"BEARER_TOKEN_FILE": core.config['token.xrootd']}):
                xrootd_url = xroot_url(TestXrootd.rootdir_copied_file)
                command = ('xrdcp', '--debug', '2', TestXrootd.__data_path, xrootd_url)
                core.check_system(command, "Authenticated xrdcp upload to dir w/o write access (should be denied)", exit=ERR_PERMISSION_DENIED, user=True)
                self.assertFalse(os.path.exists(TestXrootd.rootdir_copied_file), "Uploaded file wrongly present")
        finally:
            files.remove(TestXrootd.rootdir_copied_file)

    def _check_ownership(self, uploaded_file):
        # Ownership check; copied from core.check_file_ownership() because I want more detailed info
        self.skip_bad_unless(os.path.exists(uploaded_file), f"{uploaded_file} does not exist")
        self.skip_bad_unless(os.path.isfile(uploaded_file), f"{uploaded_file} exists but is not a regular file")
        try:
            file_stat = os.stat(uploaded_file)
        except OSError as err:
            self.fail(f"Unexpected error while statting {uploaded_file}: {err}")
        file_owner_uid = file_stat.st_uid
        username = core.options.username
        file_owner_name = pwd.getpwuid(file_owner_uid).pw_name
        self.assertEqual(file_owner_name, username,
                         f"{uploaded_file} owner {file_owner_name} does not match expected user {username}")

    @xrootd_record_failure
    def test_05a_xrootd_multiuser_gsi(self):
        core.skip_ok_unless_installed('xrootd-multiuser', by_dependency=True)
        self.skip_bad_unless(core.config['xrootd.multiuser'], 'Xrootd not configured for multiuser')
        self.skip_unless_security("GSI")
        self._check_ownership(TestXrootd.user_copied_file_gsi)

    @xrootd_record_failure
    def test_05b_xrootd_multiuser_scitoken(self):
        core.skip_ok_unless_installed('xrootd-multiuser', by_dependency=True)
        self.skip_bad_unless(core.config['xrootd.multiuser'], 'Xrootd not configured for multiuser')
        self.skip_unless_security("SCITOKENS")
        self._check_ownership(TestXrootd.user_copied_file_scitoken)

    def _test_download(self, remote_file, command, message):
        files.remove(TestXrootd.download_temp)
        try:
            core.check_system(command, message ,user=True)
            self.assertTrue(os.path.isfile(TestXrootd.download_temp), "Downloaded file missing")
            self.assertEqualVerbose(files.read(TestXrootd.download_temp, as_single_string=True),
                                    files.read(remote_file, as_single_string=True),
                                    "Downloaded contents differ from expected")
        finally:
            files.remove(TestXrootd.download_temp)

    @xrootd_record_failure
    def test_06a_xrdcp_download_gsi(self):
        self.skip_unless_security("GSI")
        remote_file = TestXrootd.user_file_to_download
        remote_url = xroot_url(remote_file)
        command = ('xrdcp', '--nopbar', '--debug', '2', remote_url, TestXrootd.download_temp)
        message = "xrdcp download with GSI"
        with core.no_bearer_token(core.options.username):
            self._test_download(remote_file, command, message)

    @xrootd_record_failure
    def test_06b_xrdcp_download_scitoken(self):
        self.skip_unless_security("SCITOKENS")
        remote_file = TestXrootd.user_file_to_download
        remote_url = xroot_url(remote_file)
        command = ('xrdcp', '--nopbar', '--debug', '2', remote_url, TestXrootd.download_temp)
        message = "xrdcp download with scitoken"
        with core.no_x509(core.options.username), core.environ_context({"BEARER_TOKEN_FILE": core.config['token.xrootd']}):
            self._test_download(remote_file, command, message)

    @xrootd_record_failure
    def test_06c_xrdcp_download_voms(self):
        self.skip_unless_security("VOMS")
        remote_file = TestXrootd.vo_file_to_download
        remote_url = xroot_url(remote_file)
        command = ('xrdcp', '--nopbar', '--debug', '2', remote_url, TestXrootd.download_temp)
        message = "xrdcp download with VOMS"
        with core.no_bearer_token(core.options.username):
            self._test_download(remote_file, command, message)

    @xrootd_record_failure
    def test_07_https_download_public(self):
        remote_file = TestXrootd.public_file_to_download
        remote_url = https_url(remote_file)
        command = ('curl', '-kLs', remote_url, '-o', TestXrootd.download_temp)
        message = "HTTPS download from public dir"
        self._test_download(remote_file, command, message)

    @xrootd_record_failure
    def test_08a_https_download_scitoken_in_url(self):
        self.skip_unless_security("SCITOKENS")
        remote_file = TestXrootd.user_file_to_download
        remote_url = https_url(remote_file, token=core.state['token.xrootd_contents'])
        command = ('curl', '-kLs', remote_url, '-o', TestXrootd.download_temp)
        message = "HTTPS download from user dir with token in the URL"
        self._test_download(remote_file, command, message)

    @xrootd_record_failure
    def test_08b_https_download_scitoken_in_header(self):
        self.skip_unless_security("SCITOKENS")
        remote_file = TestXrootd.user_file_to_download
        remote_url = https_url(remote_file)
        command = ('curl', '-kLs',
                   '-H', f"Authorization: Bearer {core.state['token.xrootd_contents']}",
                   remote_url, '-o', TestXrootd.download_temp)
        message = "HTTPS download from user dir with token in the header"
        self._test_download(remote_file, command, message)

    # TODO Maybe some HTTPS upload tests?
