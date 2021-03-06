import os
import re

from osgtest.library import core
from osgtest.library import service

PACKAGE_NAME = 'mariadb'
PORT = 3306

def pidfile():
    return os.path.join('/var/run', PACKAGE_NAME, PACKAGE_NAME + '.pid')

def server_rpm():
    return PACKAGE_NAME + '-server'

def client_rpm():
    return PACKAGE_NAME

def start():
    service.check_start(PACKAGE_NAME)

def stop():
    service.check_stop(PACKAGE_NAME)

def is_running():
    return service.is_running(PACKAGE_NAME)

def _get_command(user='root', database=None):
    command = ['mysql', '-N', '-B', '--user=' + str(user)]
    if database:
        command.append('--database=' + str(database))
    return command

def execute(statements, database=None):
    """Execute MySQL statements

    `statements` must be a single string, but may contain multiple statements;
    this will be fed to `mysql` as a script. The trailing `;` is necessary
    even if executing a single statement. Query output is tab-separated.
    If `database` is specified, the given database is used.

    Return (exit status, stdout, stderr).

    """
    return core.system(_get_command(database=database), stdin=statements)

def check_execute(statements, message, database=None, exit=0):
    """Execute MySQL statements and check the exit code

    `statements` must be a single string, but may contain multiple statements;
    this will be fed to `mysql` as a script. The trailing `;` is necessary
    even if executing a single statement. Query output is tab-separated.
    If `database` is specified, the given database is used.

    If the return code from the call does not match the expected exit code,
    an error is raised, and `message` is printed.

    Return (standard output, standard error, and the failure
    message generated by core.diagnose()).

    """
    return core.check_system(_get_command(database=database), message, stdin=statements, exit=exit)

def dbdump(destfile, database=None):
    """Dump the contents of one or all databases to the given file

    `destfile` must be a path the user can write to. If `database` is specified,
    only the given database is dumped; otherwise, all databases are dumped.

    The output is suitable for feeding back into `mysql` as a script.

    """
    command = "mysqldump --skip-comments --skip-extended-insert -u root "
    if database:
        command += re.escape(database)
    else:
        command += "--all-databases"
    command += ">" + re.escape(destfile)
    core.system(command, user=None, stdin=None, log_output=False, shell=True)
