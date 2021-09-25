"""Support and convenience functions for tests."""
import contextlib
import functools
import os
import os.path
import pwd
import re
import rpm
from osgtest.vendor.miscutils import stringToVersion
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import traceback
import socket
import signal
from shlex import quote as shell_quote
from typing import Any, Dict, List, Optional, Union

from osgtest.library import osgunittest

# ------------------------------------------------------------------------------
# Module attributes
# ------------------------------------------------------------------------------

# Global configuration dictionary.  The intent here is to store configuration
# for the test run.  Someday, we may even load this configuration from a file,
# or something like that.  For now, test modules should only add new entries to
# this dictionary, neither modifying nor deleting existing ones.
config: Dict[str, Any] = {}
config['user.home'] = '/var/home'
config['system.mapfile'] = '/etc/grid-security/grid-mapfile'

# Global state dictionary.  Other modules may add, read, change, and delete the
# keys stored herein.  At the moment, no checking is done on its contents, so
# individual tests should be careful about using it.  The recommendation is to
# prefix each key with "COMP.", where "COMP" is a short lowercase string that
# indicates which component the test belongs to, or "general." for truly cross-
# cutting objects.
state: Dict[str, Any] = {'proxy.valid': False}

class DummyClass(object):
    """A class that ignores all function calls; useful for testing"""
    def __getattr__(self, item):
        def handler(*args, **kwargs):
            pass
        return handler

# Global command-line options.  This should be merged into the config object,
# eventually.
options: Any = None

# "Internal" attributes for use within this module.
_log = sys.stderr
_log_filename = ""
_last_log_had_output = True

SLURM_PACKAGES = ['slurm',
                  'slurm-slurmd',
                  'slurm-slurmctld',
                  'slurm-perlapi',
                  'slurm-slurmdbd']

MAX_OUTPUT_LINES = 1000  # The maximum number of lines to print for output

# ------------------------------------------------------------------------------
# Helper Classes
# ------------------------------------------------------------------------------

class PackageVersion:
    """Compare the installed rpm version of a package to an "[E:]V[-R]" string.

       If the Release field is not specified for [E:]V[-R], it will be ignored
       for the package's evr in the comparison.  The default Epoch is "0".

       Example package version tests:

            PackageVersion('osg-release')   == '3.4'
            PackageVersion('xrootd-lcmaps') >= '1.4.0'
            PackageVersion('voms-server')   <  '2.0.12-3.2'

       Version ranges can also be tested in the normal python fashion:

            '8.4.0' <= PackageVersion('condor') < '8.8.0'
    """

    def __init__(self, pkgname):
        e,n,v,r,a = get_package_envra(pkgname)
        self.evr = e,v,r
        self.version = v

    def __repr__(self):
        return "%s:%s-%s" % self.evr

    def __cmp__(self, evr):
        if isinstance(evr, str):
            evr = stringToVersion(evr)
        else:
            raise TypeError('PackageVersion compares to "[E:]V[-R]" string')

        if evr[2] is None:
            pkg_evr = (self.evr[0], self.evr[1], None)
        else:
            pkg_evr = self.evr

        return rpm.labelCompare(pkg_evr, evr)

    if not hasattr(__builtins__, 'cmp'):
        def __eq__(self, evr): return self.__cmp__(evr) == 0
        def __ne__(self, evr): return self.__cmp__(evr) != 0
        def __lt__(self, evr): return self.__cmp__(evr) <  0
        def __le__(self, evr): return self.__cmp__(evr) <= 0
        def __gt__(self, evr): return self.__cmp__(evr) >  0
        def __ge__(self, evr): return self.__cmp__(evr) >= 0


# ------------------------------------------------------------------------------
# Global Functions
# ------------------------------------------------------------------------------

def init_dummy():
    """Initialize 'options' and '_log' with dummy instances"""
    global options, _log

    options = DummyClass()


def start_log():
    """Creates the detailed log file; not for general use."""
    global _log_filename, _log
    (log_fd, _log_filename) = tempfile.mkstemp()
    _log = os.fdopen(log_fd, 'w')
    _log.write(('-' * 80) + '\n')
    _log.write('OSG-TEST LOG\n')
    _log.write('Start time: ' + time.strftime('%Y-%m-%d %H:%M:%S') + '\n\n')
    _log.write('Options:\n')
    _log.write('  - Add user: %s\n' % str(options.adduser))
    _log.write('  - Config file: %s\n' % options.config)
    _log.write('  - Dump output: %s\n' % str(options.dumpout))
    _log.write('  - Dump file: %s\n' % options.dumpfile)
    _log.write('  - Install: %s\n' % ', '.join(options.packages))
    _log.write('  - Update repo: %s\n' % ', '.join(options.updaterepos))
    _log.write('  - Update release: %s\n' % options.updaterelease)
    _log.write('  - No cleanup: %s\n' % str(options.skip_cleanup))
    _log.write('  - Extra repos: %s\n' % ', '.join(options.extrarepos))
    _log.write('  - Print test names: %s\n' % str(options.printtest))
    _log.write('  - Enable SELinux: %s\n' % str(options.selinux))
    _log.write('  - Skip tests: %s\n' % str(options.skiptests))
    _log.write('  - Test user: %s\n' % options.username)
    _log.write('  - Timeout: %s\n' % str(options.timeout))
    _log.write('  - Create hostcert: %s\n' % str(options.hostcert))
    _log.write('  - Backup MySQL: %s\n' % str(options.backupmysql))
    _log.write('  - Nightly: %s\n' % str(options.nightly))
    _log.flush()


def log_message(message):
    """Writes the message to the detailed log file.

    Following the format of the log file, the message is preceded by 'message:'
    and the current timestamp.  Note that the log file is only visible using the
    '-d' command-line option.
    """
    global _last_log_had_output
    if _last_log_had_output:
        _log.write('\n')
    _log.write('message: ')
    _log.write(time.strftime('%Y-%m-%d %H:%M:%S: '))
    _log.write(message + '\n')
    _last_log_had_output = False


def end_log():
    """Closes the detailed log file; not for general use."""
    _log.close()


def dump_log(outfile=None):
    if outfile is None:
        logfile = open(_log_filename, 'r')
        print('\n')
        for line in logfile:
            print(line.rstrip('\n'))
        logfile.close()
    else:
        shutil.copy(_log_filename, outfile)


def remove_log():
    """Removes the detailed log file; not for general use."""
    if _log_filename:
        os.remove(_log_filename)


def get_stat(filename):
    """Return stat for 'filename', None if the file does not exist"""
    try:
        return os.stat(filename)
    except FileNotFoundError:
        return None


def monitor_file(filename, old_stat, sentinel, timeout):
    """Monitors a file for the sentinel regex

    This function tries to monitor a growing file for a bit of text.  Because
    the file may already exist prior to the monitoring process, the second
    argument is the object that resulted from an os.stat() call prior to the
    event that is being monitored; the monitoring will start at the file
    position given by the length of the old stat, when appropriate.

    The monitoring will last no longer than the given timeout, in seconds.  If
    the file exists (or comes to exist) and the text is found within the timeout
    period, the function returns the tuple (line, delay), where 'line' is the
    complete line on which the sentinel occurred and 'delay' is the number of
    seconds that passed before the sentinel was found.  Otherwise, the tuple
    (None, None) is returned.

    NOTE: This function handles logrotation when files are moved to a separate
    location and a new file is started in its place. However, it does NOT handle
    the copy and truncate method of logrotation (i.e. the file is copied to a
    different location and the original file is truncated to 0).
    """
    read_delay = 0.5  # Time to wait after reaching EOF and not finding the sentinel before trying again
    sentinel_regex = re.compile(sentinel)
    start_time = time.time()
    end_time = start_time + timeout
    monitored_file = None
    while time.time() <= end_time:
        if monitored_file is None:
            if not os.path.exists(filename):
                time.sleep(0.2)
                continue
            new_stat = os.stat(filename)
            if ((old_stat is None) or
                (new_stat.st_ino != old_stat.st_ino) or
                    (new_stat.st_size < old_stat.st_size)):
                initial_position = 0
            else:
                initial_position = old_stat.st_size
            monitored_file = open(filename, 'r')
            monitored_file.seek(initial_position)

        where = monitored_file.tell()
        line = monitored_file.readline()
        if line:
            if sentinel_regex.search(line):
                monitored_file.close()
                return (line, time.time() - start_time)
        else:
            # If the file got moved from under us, close the old file. Previous iterations of the loop ensure that the
            # remaining contents of the old file got read. On the next iteration, the new file gets opened.
            if os.stat(filename).st_ino != new_stat.st_ino:
                monitored_file.close()
                old_stat = None
                monitored_file = None
            else:
                time.sleep(read_delay)
                monitored_file.seek(where)
    if monitored_file is not None:
        monitored_file.close()
    return (None, None)


def trim_output(output):
    # type: (Union[str, List, None]) -> List
    if output is None:
        return []
    elif isinstance(output, str):
        output_lines = output.splitlines()
    else:
        output_lines = output
    num_output_lines = len(output_lines)
    if num_output_lines > MAX_OUTPUT_LINES:
        output_lines_trim = (
                output_lines[:MAX_OUTPUT_LINES//2] +
                ['(%d lines trimmed)' % (num_output_lines - MAX_OUTPUT_LINES)] +
                output_lines[-MAX_OUTPUT_LINES//2:]
        )
        output_lines = output_lines_trim
    return output_lines


def system(command, user=None, stdin=None, log_output=True, shell=False, timeout=None, timeout_signal='TERM', quiet=False):
    """Runs a command and returns its exit status, stdout, and stderr.

    The command is provided as a list or tuple, unless the 'shell' argument is
    set to True, in which case the command should be a single string object.

    The command is run as root, unless the 'user' argument is set to True, in
    which case the command is run as the non-root user passed on the command
    line.

    If a 'stdin' string is given, it is piped into the command as its standard
    input.

    If 'log_output' is set to False, the standard output and standard error of
    the command are not written to the detailed log.

    If 'shell' is set to True, a shell subprocess is created and the command is
    run within that shell; in this case, the command should be given as a single
    string instead of a list or tuple.

    If 'timeout' is set to a numeric value (int or float), kill the process group
    of the command after that many seconds has elapsed without it completing.
    If the timeout is hit, the exit status returned is -1.

    If 'timeout_signal' is set to an int or str (eg, 9 or 'KILL'), use that signal
    instead of 'TERM' to kill the subprocess group after the timeout is reached.
    """
    return __run_command(command, user, stdin, subprocess.PIPE,
                         subprocess.PIPE, log_output, shell=shell,
                         timeout=timeout, timeout_signal=timeout_signal,
                         quiet=quiet)


def check_system(command, message, exit=0, user=None, stdin=None, shell=False, timeout=None, timeout_signal='TERM'):
    """Runs the command and checks its exit status code.

    Handles all of the common steps associated with running a system command:
    runs the command, checks its exit status code against the expected result,
    and raises an exception if there is an obvious problem.

    Returns a tuple of the standard output, standard error, and the failure
    message generated by diagnose().  See the system() function for more details
    about the command-line options.
    """
    status, stdout, stderr = system(command, user, stdin, shell=shell,
                                    timeout=timeout, timeout_signal=timeout_signal,
                                    quiet=False)
    fail = diagnose(message, command, status, stdout, stderr)
    if timeout and status == -1:
        raise osgunittest.TimeoutException(fail)
    else:
        assert status == exit, fail
    return stdout, stderr, fail


def rpm_is_installed(a_package):
    """Returns whether the RPM package is installed."""
    status, stdout, stderr = system(('rpm', '--query', a_package),
                                    log_output=False, quiet=True)
    return (status == 0) and stdout.startswith(a_package)


def dependency_is_installed(a_dependency):
    """Returns whether an RPM package providing a dependency is installed.

    Distinct from rpm_is_installed in that this handles virtual dependencies,
    such as 'grid-certificates'.
    """
    return bool(dependency_installed_rpms(a_dependency))


def dependency_installed_rpms(a_dependency):
    """Returns a list of installed rpms satisfying a virtual dependency.
    """
    status, stdout, stderr = system(('rpm', '--query', '--whatprovides', a_dependency),
                                    log_output=False, quiet=True)
    return (stdout.splitlines()
            if (status == 0) and not stdout.startswith('no package provides')
            else [])


def installed_rpms():
    """Returns the list of all installed packages."""
    command = ('rpm', '--query', '--all', '--queryformat', r'%{NAME}\n')
    proc = subprocess.run(command, stdout=subprocess.PIPE, encoding='latin-1')
    return proc.stdout.splitlines()


def rpm_regexp_is_installed(a_regexp):
    """Returns whether any RPM matches the provided regexp."""
    pkg_regexp = re.compile(a_regexp)
    for pkg in installed_rpms():
        if re.search(pkg_regexp, pkg):
            return True
    return False

def skip(message=None):
    """Prints a 'SKIPPED' message to standard out."""
    sys.stdout.flush()
    if message:
        sys.stdout.write('SKIPPED (%s) ... ' % message)
    else:
        sys.stdout.write('SKIPPED ... ')
    sys.stdout.flush()


def missing_rpm(*packages):
    """Checks that all given RPM packages are installed.

    If any package is missing, list all missing packages in a skip() message.
    """
    if isinstance(packages[0], (list, tuple)):
        packages = packages[0]

    missing = []
    for package in packages:
        if not rpm_is_installed(package):
            missing.append(package)
    if len(missing) > 0:
        skip('missing %s' % ' '.join(missing))
        return True
    return False


def skip_ok_unless_installed(*packages_or_dependencies, **kwargs):
    """Check that all given RPM packages or dependencies are installed and skip
    the test if not.

    Accepts the following keyword arguments:
    - 'message' is the text to include in the Exception (a generic 'missing
      $package' will be used otherwise)
    - 'by_dependency' is a bool which, if True, will cause dependencies to be
      queried instead of packages
    Raise osgunittest.OkSkipException if packages/dependencies are missing,
    otherwise return None.
    """
    # Handle the keyword arguments. There is some magic here to make it work
    # with the variable number of arguments that we are using for
    # 'packages_or_dependencies'.  Make sure that we accept the argument not
    # being there, but also raise an error on unexpected keyword arguments.
    message = kwargs.pop('message', None)
    by_dependency = kwargs.pop('by_dependency', False)
    if kwargs:
        raise TypeError("skip_ok_unless_installed() got unexpected keyword argument(s) '%s'" %
                        ("', '".join(kwargs.keys())))

    if isinstance(packages_or_dependencies[0], (list, tuple)):
        packages_or_dependencies = packages_or_dependencies[0]

    is_installed = dependency_is_installed if by_dependency else rpm_is_installed
    missing = [ x for x in packages_or_dependencies if not is_installed(x) ]

    if len(missing) > 0:
        raise osgunittest.OkSkipException(message or 'missing %s' % ' '.join(missing))

def skip_bad_if_more_than_one_installed(*packages):
    """
     Raise osgunittest.BadException if more than one of the packages
     are installed which are mutually exclusive,
     otherwise return None.
    """
    installed = []
    for package in packages:
        if rpm_is_installed(package):
            installed.append(package)
    if len(installed) > 1:
        raise osgunittest.BadSkipException('More than one installed of: %s' % ' '.join(installed))


def skip_ok_unless_one_installed(*packages):
    """
     Raise osgunittest.SkipOkException if at least one of the packages are installed
     otherwise return None.
    """
    if isinstance(packages[0], (list, tuple)):
        packages = packages[0]
    installed = []
    for package in packages:
        if rpm_is_installed(package):
            installed.append(package)
    if len(installed)==0:
        raise osgunittest.OkSkipException('None of these were intalled, skipping %s ' % ' '.join(packages))

def get_package_envra(package_name):
    """Query and return the ENVRA (Epoch, Name, Version, Release, Arch) of an
    installed package as a tuple. Can raise OSError if rpm does not return
    output in the right format.

    """
    command = ('rpm', '--query', package_name, "--queryformat=%{EPOCH} %{NAME} %{VERSION} %{RELEASE} %{ARCH} ")
    status, stdout, stderr = system(command, quiet=True)
    # Not checking stderr because signature warnings get written there and
    # we do not care about those.
    if (status != 0) or (stdout is None):
        raise OSError(status, stdout)

    envra = stdout.strip().split(' ')
    if len(envra) != 5:
        raise OSError(status, stdout)
    (epoch, name, version, release, arch) = envra
    # Missing epoch is displayed as '(none)' but treated by rpm as '0'
    if epoch == '(none)':
        epoch = '0'
    return (epoch, name, version, release, arch)


def diagnose(message, command, status, stdout, stderr):
    """Constructs a detailed failure message based on arguments."""
    result = message + '\n'
    result += 'COMMAND: %s\n' % ' '.join(command)
    if status == -1:
        result += 'EXIT STATUS: %d (command timed out)\n' % status
    else:
        result += 'EXIT STATUS: %d\n' % status
    result += 'STANDARD OUTPUT:'
    stdout_lines = trim_output(stdout)
    if not stdout_lines:
        result += ' [none]\n'
    else:
        result += '\n'.join(stdout_lines) + '\n'
    result += 'STANDARD ERROR:'
    stderr_lines = trim_output(stderr)
    if not stderr_lines:
        result += ' [none]\n'
    else:
        result += '\n'.join(stderr_lines) + '\n'
    return result


def __format_command(command):
    if isinstance(command, str):
        return [command]
    result = []
    for part in command:
        if part == '':
            result.append("''")
        elif re.search(r"[' \\]", part):
            result.append('"' + part + '"')
        else:
            result.append(part)
    return result


_devnull = open(os.devnull, "r+b")


def __run_command(command, use_test_user, a_input, a_stdout, a_stderr, log_output=True, shell=False, timeout=None, timeout_signal='TERM', quiet=False):
    global _last_log_had_output

    # Preprocess command
    if shell:
        if not isinstance(command, str):
            command = ' '.join(command)
    elif not isinstance(command, (list, tuple)):
        try:
            repr(command)
        except TypeError:
            print('Need list or tuple, got %s' % type(command))
    if use_test_user:
        command = ['runuser', options.username, '-c', ' '.join(map(shell_quote, command))]

    # Figure out stdin
    stdin = _devnull
    if a_input is not None:
        stdin = subprocess.PIPE

    if not quiet:
        # Log
        if _last_log_had_output:
            _log.write('\n')
        _log.write('osgtest: ')
        _log.write(time.strftime('%Y-%m-%d %H:%M:%S: '))
        # HACK: print test name
        # Get the current test function name, the .py file it's in, and the line number from the call stack
        if options.printtest:
            stack = traceback.extract_stack()
            for stackentry in reversed(stack):
                filename, lineno, funcname, text = stackentry
                if re.search(r'(test_\d+|special).+\.py', filename):
                    _log.write("%s:%s:%d: " % (os.path.basename(filename), funcname, lineno))
        _log.write(' '.join(__format_command(command)))

    # Run and return command, with timeout if applicable
    preexec_fn = None
    if timeout is not None:
        preexec_fn = os.setsid  # or lambda : os.setpgid(0,0)
        # allow signal names like 'KILL' instead of numbers
        if type(timeout_signal) == str:
            timeout_signal = getattr(signal, 'SIG' + timeout_signal.upper())

    p = subprocess.Popen(command, stdin=stdin, stdout=a_stdout,
                         stderr=a_stderr, shell=shell,
                         preexec_fn=preexec_fn)

    if timeout is not None:
        watcher_pid = os.fork()
        if watcher_pid == 0:
            time.sleep(timeout)
            os.killpg(p.pid, timeout_signal)
            os._exit(0)

    stdout, stderr = p.communicate(to_bytes(a_input))
    stdout, stderr = to_str(stdout), to_str(stderr)

    if timeout is not None:
        if p.returncode >= 0:
            # kill watcher if child exited normally before timeout
            os.kill(watcher_pid, signal.SIGKILL)
        else:
            # return -1 for timeout
            p.returncode = -1
        # always reap zombie watcher
        os.waitpid(watcher_pid, 0)

        # Log
    if not quiet:
        stdout_length = 0
        if stdout is not None:
            stdout_length = len(stdout)
        stderr_length = 0
        if stderr is not None:
            stderr_length = len(stderr)
        _log.write(' >>> %d %d %d\n' % (p.returncode, stdout_length, stderr_length))
        _last_log_had_output = False
        if log_output:
            if (stdout is not None) and (len(stdout.rstrip('\n')) > 0):
                stdout_lines = trim_output(stdout)
                _log.write('STDOUT:{\n')
                _log.write('\n'.join(stdout_lines) + '\n')
                _log.write('STDOUT:}\n')
                _last_log_had_output = True
            if (stderr is not None) and (len(stderr.rstrip('\n')) > 0):
                stderr_lines = trim_output(stderr)
                _log.write('STDERR:{\n')
                _log.write('\n'.join(stderr_lines) + '\n')
                _log.write('STDERR:}\n')
                _last_log_had_output = True
        _log.flush()

    return (p.returncode, stdout, stderr)

def wait_for_file(filename, timeout):
    """Wait maximum 'timeout' seconds for filename to be created. Returns True
    if created within the timeout, False otherwise.

    """
    elapsed_time = 0
    while elapsed_time <= timeout:
        if os.path.exists(filename):
            return True
        else:
            time.sleep(1)
            elapsed_time += 1

    return False


@functools.lru_cache(1)
def el_release() -> int:
    """Return the major version of the Enterprise Linux release the system is
    running. SL/RHEL/CentOS 6.x will return 6; SL/RHEL/CentOS 7.x will return
    7.

    """
    try:
        release_file = open("/etc/redhat-release", 'r')
        try:
            release_text = release_file.read()
        finally:
            release_file.close()
        match = re.search(r"release (\d)", release_text)
        return int(match.group(1))
    except (EnvironmentError, TypeError, ValueError) as e:
        _log.write("Couldn't determine redhat release: " + str(e) + "\n")
        sys.exit(1)


def osg_release_rpm() -> Optional[str]:
    """
    Return the name of the RPM providing osg-release, or None if no such
    RPM is found.
    """
    try:
        return dependency_installed_rpms('osg-release')[0]
    except IndexError:
        return None


@functools.lru_cache(1)
def is_x86_64_v2() -> bool:
    """True if the OS (not necessarily the CPU) is Alma 10 x86_64_v2"""
    proc = subprocess.run(['rpm', '-E', '%{x86_64_v2}'], stdout=subprocess.PIPE)
    return proc.stdout.strip() == b'1'


def osg_release(update_state=False):
    """
    Return a PackageVersion instance of osg-release. If the query fails, the test module fails.
    """
    if not update_state and 'general.osg_release_ver' in state:
        return state['general.osg_release_ver']
    release_rpm = osg_release_rpm()
    assert release_rpm, "No osg-release RPM installed"
    release = PackageVersion(release_rpm)
    state['general.osg_release_ver'] = release
    return release


def get_hostname():
    """
    Returns the hostname of the current system, returns None if it can't
    get the hostname
    """
    try:
        return socket.gethostbyaddr(socket.gethostname())[0]
    except socket.error:
        return None

def check_file_ownership(file_path, owner_name):
    """Return True if at 'file_path' exists, is owned by
    'owner_name' and is a file
    """
    owner_pwentry = pwd.getpwnam(owner_name)
    try:
        file_stat = os.stat(file_path)
        return (file_stat.st_uid == owner_pwentry.pw_uid and
                stat.S_ISREG(file_stat.st_mode))
    except OSError:  # file does not exist
        return False

def check_file_and_perms(file_path, owner_name, permissions):
    """Return True if the file at 'file_path' exists, is owned by
    'owner_name', is a file, and has the given permissions; False otherwise
    """
    try:
        file_stat = os.stat(file_path)
        return (check_file_ownership(file_path, owner_name) and
                file_stat.st_mode & 0o7777 == permissions)
    except OSError:  # file does not exist
        return False

def parse_env_output(output):
    """
    Parse env output and store them in a dict
    """
    env = {}
    for line in output.split('\n'):
        env_match = re.match(r'(\S+)=(\S+)', line)
        try:
            env[env_match.group(1)] = env_match.group(2)
        except AttributeError:
            pass

    return env

def install_cert(target_key, source_key, owner_name, permissions):
    """
    Carefully install a certificate with the given key from the given
    source path, then set ownership and permissions as given.  Record
    each directory and file created by this process into the config
    dictionary; do so immediately after creation, so that the
    remove_cert() function knows exactly what to remove/restore.
    """
    target_path = config[target_key]
    target_dir = os.path.dirname(target_path)
    source_path = config[source_key]
    user = pwd.getpwnam(owner_name)

    # Using os.path.lexists because os.path.exists return False for broken symlinks
    if os.path.lexists(target_path):
        backup_path = target_path + '.osgtest.backup'
        shutil.move(target_path, backup_path)
        state[target_key + '-backup'] = backup_path

    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
        state[target_key + '-dir'] = target_dir
        os.chown(target_dir, user.pw_uid, user.pw_gid)
        os.chmod(target_dir, 0o755)

    shutil.copy(source_path, target_path)
    state[target_key] = target_path
    os.chown(target_path, user.pw_uid, user.pw_gid)
    os.chmod(target_path, permissions)

def remove_cert(target_key):
    """
    Carefully removes a certificate with the given key.  Removes all
    paths associated with the key, as created by the install_cert()
    function.
    """
    if target_key in state:
        os.remove(state[target_key])
    if target_key + '-backup' in state:
        shutil.move(state[target_key + '-backup'],
                    state[target_key])
    if target_key + '-dir' in state:
        target_dir = state[target_key + '-dir']
        if len(os.listdir(target_dir)) == 0:
            os.rmdir(target_dir)

def osgrelease(*releases):
    """
    Return a decorator that will only call its function when the current
    osg_release version is specified in the list of releases; otherwise
    ExcludedException is raised and the test is added to the 'excluded'
    list.

        class TestFoo(osgunittest.OSGTestCase):

            @osgrelease(3.4)
            def test_bar_34_only(self):
                ...
    """
    releases = [str(x) for x in releases]  # convert float args to str
    def osg_release_decorator(fn):
        def run_fn_if_osg_release_ok(*args, **kwargs):
            if osg_release().version in releases:
                return fn(*args, **kwargs)
            else:
                msg = "excluding for OSG %s" % osg_release().version
                raise osgunittest.ExcludedException(msg)
        return run_fn_if_osg_release_ok
    return osg_release_decorator

def elrelease(*releases):
    """
    Return a decorator that will only call its function when the current
    el_release version is specified in the list of releases; otherwise
    ExcludedException is raised and the test is added to the 'excluded'
    list.

        class TestFoo(osgunittest.OSGTestCase):

            @elrelease(7)
            def test_bar_el7_only(self):
                ...
    """
    def el_release_decorator(fn):
        def run_fn_if_el_release_ok(*args, **kwargs):
            if el_release() in releases:
                return fn(*args, **kwargs)
            else:
                msg = "excluding for EL%s" % el_release()
                raise osgunittest.ExcludedException(msg)
        return run_fn_if_el_release_ok
    return el_release_decorator


def to_str(strlike, encoding="latin-1", errors="backslashreplace"):
    """Turns a bytes into a str (Python 3) or a unicode to a str (Python 2)"""
    if strlike is None:
        return
    if not isinstance(strlike, str):
        if str is bytes:
            return strlike.encode(encoding, errors)
        else:
            return strlike.decode(encoding, errors)
    else:
        return strlike


def to_bytes(strlike, encoding="latin-1", errors="backslashreplace"):
    """Turns a str into bytes (Python 3) or a unicode to a str (Python 2)"""
    if strlike is None:
        return
    if not isinstance(strlike, bytes):
        return strlike.encode(encoding, errors)
    return strlike


@contextlib.contextmanager
def environ_context(items):
    """A context manager for running a block with environment variables set,
    restoring the originals afterward.  `items` is either a dict or list of key,value
    pairs; if a value is None, that variable is unset.

    """
    old_values = {}
    if isinstance(items, dict):
        items = list(items.items())
    for key, value in items:
        old_values[key] = os.environ.pop(key, None)
        if value is not None:
            os.environ[key] = value
    try:
        yield
    finally:
        for key, old_value in old_values.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


@contextlib.contextmanager
def no_x509(user):
    """A context manager for hiding and restoring a user's X.509 credentials
    so they won't conflict with other forms of auth.

    """
    baksuffix = f".osgtest{os.getpid()}-bak"
    uid = pwd.getpwnam(user).pw_uid
    globus_dir = os.path.expanduser(f"~{user}/.globus")
    proxy = f"/tmp/x509up_u{uid}"
    moved_globus = False
    moved_proxy = False
    try:
        if os.path.exists(globus_dir):
            shutil.move(globus_dir, globus_dir + baksuffix)
            moved_globus = True
        if os.path.exists(proxy):
            shutil.move(proxy, proxy + baksuffix)
            moved_proxy = True
        with environ_context({"X509_USER_PROXY": None, "X509_USER_CERT": None, "X509_USER_KEY": None}):
            yield
    finally:
        try:
            if moved_globus:
                shutil.move(globus_dir + baksuffix, globus_dir)
        except EnvironmentError as err:
            log_message(f"Couldn't restore {globus_dir}: {err}")
        try:
            if moved_proxy:
                shutil.move(proxy + baksuffix, proxy)
        except EnvironmentError as err:
            log_message(f"Couldn't restore {proxy}: {err}")


@contextlib.contextmanager
def no_bearer_token(user):
    """A context manager for hiding and restoring a user's bearer token
    so it won't conflict with other forms of auth.

    """
    baksuffix = f".osgtest{os.getpid()}-bak"
    uid = pwd.getpwnam(user).pw_uid
    token_file = f"/tmp/bt_u{uid}"
    moved_token_file = False
    try:
        if os.path.exists(token_file):
            shutil.move(token_file, token_file + baksuffix)
            moved_token_file = True
        with environ_context({"BEARER_TOKEN": None, "BEARER_TOKEN_FILE": None, "XDG_RUNTIME_DIR": None}):
            yield
    finally:
        try:
            if moved_token_file:
                shutil.move(token_file + baksuffix, token_file)
        except EnvironmentError as err:
            log_message(f"Couldn't restore {token_file}: {err}")
