"""Utilities for starting and stopping init-based services."""
import time

from osgtest.library import core
from osgtest.library import files

STATUS_RUNNING = 0 # LSB: program is running or service is OK
STATUS_STOPPED = 3 # LSB: program is not running according to LSB init standards

def start(service_name, force=False):
    """
    Start a service via init script or systemd.

    'service_name' is used as the base of the keys in the core.config and
    core.state dictionaries.

    The service is started by doing "service service_name start" or "systemctl
    start service_name".

    The service is not started up if core.state[service_name.started-service] is
    True.

    If `force` is True, ignore the above flag and always start the service.

    The following globals are set:
    core.config[service_name.sentinel-file] is set to the value of sentinel_file,
    if specified.

    """
    if not force and core.state.get(service_name + '.started-service'):
        core.skip('service ' + service_name + ' already running (flagged as started)')
        return

    command = ('systemctl', 'start', service_name)
    core.check_system(command, 'Start ' + service_name + ' service')
    core.state[service_name + '.started-service'] = True

def check_start(service_name, timeout=10, log_to_check = None, min_up_time=0, force=False):
    """
    Start a service, 'service_name' via init script or systemd and ensure that
    it starts running within a 'timeout' second window (default=10s).
    Will wait 'min_up_time' seconds before checking; the timeout window starts
    after min_up_time has been reached.
    """
    start(service_name, force)
    time.sleep(min_up_time)
    assert is_running(service_name, timeout=timeout, log_to_check=log_to_check), "%s is not running" % service_name

def stop(service_name, force=False):
    """
    Stop a service via init script or systemd.

    'service_name' is used as the base of the keys in the core.config and
    core.state dictionaries.

    If we started the service, the service is stopped by doing "service
    service_name stop" or "systemctl stop service_name".

    Globals used:
    core.state[service_name.started-service] is used to determine if we started
    the service. After shutdown, this is set to False.

    If `force` is True, ignore the above flag and always stop the service.
    """
    if not force and not core.state.get(service_name + '.started-service'):
        core.skip('did not start service ' + service_name)
        return

    command = ('systemctl', 'stop', service_name)
    core.check_system(command, 'Stop ' + service_name + ' service')
    core.state[service_name + '.started-service'] = False

def check_stop(service_name, timeout=10, force=False):
    """
    Stop a service, 'service_name' via init script or systemd and ensure that it
    stops running within a 'timeout' second window (default=10s)
    """
    stop(service_name, force)
    assert is_stopped(service_name, timeout=timeout), "%s is still running" % service_name

def status(service_name):
    """
    Return exit code of the 'service_name' init script or systemd status check
    """
    command = ('systemctl', 'is-active', service_name)

    status_rc, _, _ = core.system(command, quiet=True)
    return status_rc

def check_status(service_name, expected_status, timeout=10, log_to_check = None):
    """
    Return True if the exit code of the 'service_name' status check is
    expected_status before 'timeout' seconds. Otherwise, False.
    """
    timer = 0
    status_rc = None
    while timer < timeout and status_rc != expected_status:
        status_rc = status(service_name)
        time.sleep(1)
        timer += 1

    if status_rc != expected_status and log_to_check:
        log_file_contents = files.read(log_to_check)
        core.log_message("Last lines of log: %s" % log_to_check)
        for line in log_file_contents[-9:]:
            core.log_message(line)
    return status_rc == expected_status

def is_running(service_name, timeout=1, log_to_check = None):
    """
    Return True if 'service_name' is determined to be running via init script or
    systemd, according to LSB init standards, before 'timeout'
    seconds. Otherwise, False.
    """
    return check_status(service_name, STATUS_RUNNING, timeout, log_to_check)

def is_stopped(service_name, timeout=1):
    """
    Return True if service_name is properly stopped (exit code = 3) via init
    script or systemd, according to LSB, init standards, before 'timeout'
    seconds. Otherwise, False.
    """
    return check_status(service_name, STATUS_STOPPED, timeout)
