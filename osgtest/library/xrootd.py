"""Utilities for dealing with XRootD"""
import os
from typing import List

from osgtest.library import core


ROOTDIR = f"/tmp/xrootd-osgtest-{os.getpid()}"


def cconfig_raw(instance, executable="xrootd", quiet=True) -> str:
    """Return the a config dump of an xrootd instance using cconfig, as a
    single string.
    """
    # Using shell=True because cconfig prints output into stderr and there's a
    # bug in core.__run_command()'s stderr handling.
    ret, output, _ = core.system(f"cconfig -x {executable} -n {instance} -c /etc/xrootd/xrootd-{instance}.cfg 2>&1", shell=True, quiet=quiet)

    if ret != 0:
        return ""
    return output


def cconfig(instance, executable="xrootd", quiet=True) -> List[str]:
    """Return the a config dump of an xrootd instance using cconfig, as a processed
    list with non-config lines removed.
    """
    raw_output = cconfig_raw(instance, executable, quiet)
    if not raw_output:
        return []
    return [line for line in raw_output.splitlines() if not line.startswith("Config continuing with file ")]


def dump_log(lines, instance, executable="xrootd"):
    """Dump the last `lines` lines of an xrootd log file for the given instance."""
    # Using tail(1) here because the executable log is actually a nice place
    # to put the output.
    core.system(["tail", "-n", str(lines), f"/var/log/xrootd/{instance}/{executable}.log"])


def logfile(instance, executable="xrootd"):
    return f"/var/log/xrootd/{instance}/{executable}.log"
