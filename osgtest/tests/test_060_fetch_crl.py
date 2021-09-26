import glob
import os
import re
import shutil
import tempfile

import osgtest.library.core as core
import osgtest.library.osgunittest as osgunittest

def output_is_acceptable(fetch_crl_output):
    """All lines output from fetch-crl are considered an error. We whitelist
    a few transient ones.
    """
    error_message_whitelist = [
        r'^VERBOSE\(0\)',
        'CRL has lastUpdate time in the future',
        'CRL has nextUpdate time in the past',
        # ERROR CRL verification failed for BrGrid/0 (BrGrid)
        'CRL verification failed for',
        # ERROR verify called on empty data blob
        'verify called on empty data blob',
        # LWP::Protocol::http::Socket: connect: No route to host at /usr/share/perl5/LWP/Protocol/http.pm line 51.
        'LWP::Protocol::http::Socket',
    ]

    all_lines_ok = True
    for line in fetch_crl_output.rstrip('\n').split('\n'):
        if not line:  # skip blank lines
            continue
        line_ok = False
        for error_string in error_message_whitelist:
            if re.search(error_string, line):
                line_ok = True
                break
        if not line_ok:
            all_lines_ok = False
            core.log_message("Found uncaught error message: '%s'" % line.strip())
            break
    return all_lines_ok


class TestFetchCrl(osgunittest.OSGTestCase):

    def test_01_fetch_crl(self):
        core.skip_ok_unless_installed('fetch-crl')
        core.skip_ok_unless_installed('grid-certificates', by_dependency=True)
        if core.options.manualrun:
            command = ('fetch-crl', '-p', '20', '-T', '10')
        else:
            command = ['fetch-crl']
        status, stdout, stderr = core.system(command)
        fail = core.diagnose('Run %s in /etc' % 'fetch-crl', command, status, stdout, stderr)
        if status == 1:
            self.assertTrue(output_is_acceptable(stdout + "\n" + stderr), fail)
        else:
            self.assertEquals(status, 0, fail)
        count = len(glob.glob(os.path.join('/etc/grid-security/certificates', '*.r[0-9]')))
        self.assertTrue(count > 3, f"Expected > 3 crls but found {count}")

    def test_02_fetch_crl_dir(self):
        core.skip_ok_unless_installed('fetch-crl')
        core.skip_ok_unless_installed('grid-certificates', by_dependency=True)
        temp_crl_dir = tempfile.mkdtemp()
        if core.options.manualrun:
            command = ('fetch-crl', '-o', temp_crl_dir, '-p', '20', '-T', '10')
        else:
            command = ('fetch-crl', '-o', temp_crl_dir)
        status, stdout, stderr = core.system(command)
        fail = core.diagnose('Run fetch-crl in temp dir', command, status, stdout, stderr)
        if status == 1:
            self.assertTrue(output_is_acceptable(stdout + "\n" + stderr), fail)
        else:
            self.assertEquals(status, 0, fail)
        count = len(glob.glob(os.path.join(temp_crl_dir, '*.r[0-9]')))
        shutil.rmtree(temp_crl_dir)
        self.assertTrue(count > 3, f"Expected > 3 crls but found {count}")
