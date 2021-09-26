"""Functions for performing common yum tasks.

The most important of these being the retry_command() function. This is 
necessary to overcome transient network issues, especially when running
the tests in VM universe at the CHTC.
"""

import re
import time

from osgtest.library import core

def clean(*repos):
    """Perform 'yum clean' commands that we recommend to our users"""
    if not repos: # clean all repos if none specified
        repos = ['*']

    core.system(['yum'] + ['--enablerepo=' + x for x in repos] + ['clean', 'all'])


def retry_command(command, timeout_seconds=3600):
    """Run a Yum command repeatedly until success, hard failure, or timeout.

    Run the given Yum command.  If it succeeds, return.  If it fails for a
    whitelisted reason, keep trying, otherwise return a failure message.  But,
    do not retry commands for longer than the timeout duration.
    """

    deadline = time.time() + timeout_seconds
    fail_msg, status, stdout, stderr = '', '', '', ''

    # Loop for retries
    while True:

        # Stop (re)trying if the deadline has passed
        if time.time() > deadline:
            fail_msg += "Retries terminated after timeout period"
            break

        status, stdout, stderr = core.system(command)

        # Deal with success
        if status == 0:
            break

        # Deal with failures that can be retried
        elif yum_failure_can_be_retried(stdout + "\n" + stderr):
            time.sleep(30)
            clean()
            core.log_message("Retrying command")
            continue

        # Otherwise, we do not expect a retry to succeed, ever, so fail this
        # package
        else:
            fail_msg = core.diagnose("Command failed", command, status, stdout, stderr)
            break

    return fail_msg, status, stdout, stderr

def yum_failure_can_be_retried(output):
    """Scan yum output to see if a retry might succeed."""
    whitelist = [r'No more mirrors to try',
                 r'Timeout: <urlopen error timed out>',
                 r'Error communicating with server. The message was:\nNo route to host',
                 r'Timeout on.*Operation too slow. Less than 1 bytes/sec transfered the last 30 seconds',
                 r'Could not retrieve mirrorlist',
                 r"curl: \(7\) couldn't connect to host\nerror: skipping.*?transfer failed",
                 r'Error: Cannot retrieve repository metadata',
                 r'Cannot retrieve metalink for repository',
                 r'Error: Temporary failure in name resolution']
    for regex in whitelist:
        if re.search(regex, output):
            return True
    return False

def get_transaction_id():
    """Grab the latest transaction ID from yum"""
    command = ('yum', 'history', 'info')
    history_out = core.check_system(command, 'Get yum Transaction ID')[0]
    m = re.search(r'Transaction ID : (\d+)', history_out)
    return int(m.group(1))

def parse_output_for_packages(yum_output):
    core.log_message('install.installed:' + ', '.join(core.state['install.installed']))
    clean_output = yum_output.strip().split('\n')

    transaction_regexp = re.compile(r'\s+(Installing|Updating|Cleanup|Erasing)\s+:\s+\d*:?(\S+)\s+\d')
    # Try not to match any packages named 'replacing.*'
    obsolete_regexp = re.compile(r'\s+replacing\s+([^\.]+).*\.osg\S+$')
    replacement_regexp = r'\s+(\S+)\s+(?:\S+\s+){2}osg' # Only remove obsoleting packages from the OSG
    previous_line = ''

    for line in clean_output:
        obsoleted = obsolete_regexp.match(line)
        if obsoleted:
            replaced_pkg = obsoleted.group(1)
            try:
                pkg = re.match(replacement_regexp, previous_line).group(1)
                if pkg == replaced_pkg:
                    # xrootd obsoletes older versions of itself so we end up with duplicates in install.installed.
                    # This isn't caught in the transaction logic below since the replaced package is 'cleaned up'
                    # instead of being 'erased'
                    try:
                        core.state['install.installed'].remove(pkg)
                    except ValueError:
                        # EL6 stores packages full NVR while EL5 only stores the name. This causes problems because we
                        # only capture obsoleting/replaced packages by name and try to remove by name. This means that
                        # 'install.installed' gets 'polluted' in EL6 but it doesn't really matter since we use 'yum
                        # undo' in EL6 for yum operations. We don't get rid of 'install.installed' because it currently
                        # (2/1/16) determines whether some tests get run or not
                        continue
                core.state['install.replace'].append(pkg)
            except AttributeError:
                continue # no match and not a transaction line
        else:
            pass # no match

        previous_line = line
        try:
            operation, pkg = transaction_regexp.match(line).groups()
        except AttributeError:
            continue # Not a transaction

        if operation == 'Installing' and pkg != 'kernel': # uninstalling kernel updates is a headache
            core.state['install.installed'].append(pkg)
        elif operation == 'Updating':
            core.state['install.updated'].append(pkg)
        elif operation == 'Cleanup' and pkg not in core.state['install.installed']:
            # Cleanup only occurs on upgrades/downgrades and if we didn't
            # install the package, it already existed on the machine
            core.state['install.os_updates'].append(pkg)
        elif operation == 'Erasing':
            try:
                core.state['install.installed'].remove(pkg)
            except ValueError:
                # We just removed a package that we didn't install, uh-oh!
                core.state['install.orphaned'].append(pkg)
            try:
                core.state['install.updated'].remove(pkg)
            except ValueError:
                # Package wasn't updated
                continue
