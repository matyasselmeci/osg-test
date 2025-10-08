import functools
import json
import os
import re
import shlex
import subprocess
from json import JSONDecodeError
from subprocess import CalledProcessError, CompletedProcess, TimeoutExpired
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence, Tuple

from . import core
from .core import log_message
from .osgunittest import OkSkipException


class PodmanException(Exception):
    """
    Exception raised when a podman command fails.
    """

    def __init__(self, message: Optional[str], stdout=None, stderr=None):
        self.message = message
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self):
        result = "PodmanException: "
        if self.message:
            result += self.message
        if self.stdout:
            result += f"\nSTDOUT:{{\n{str(self.stdout).rstrip()}\nSTDOUT:}}"
        if self.stderr:
            result += f"\nSTDERR:{{\n{str(self.stderr).rstrip()}\nSTDERR:}}"


def exception_wrap(message: Optional[str]) -> Callable:
    """
    Decorator for functions where a CalledProcessError or TimeoutExpired should be wrapped into a PodmanException

    Args:
        message: An optional message in the exception string
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except (CalledProcessError, TimeoutExpired) as err:
                raise PodmanException(message, err.stdout, err.stderr) from err

        return wrapper

    return decorator


def skip_if_missing(test_function: Callable) -> Callable:
    """
    Decorator for skipping a test if podman is not available.
    """

    @functools.wraps(test_function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not core.dependency_is_installed("podman"):
            raise OkSkipException("podman is not available")
        return test_function(*args, **kwargs)

    return wrapper


def runpodman(args: Sequence[str], *, errmsg=None, **kwargs) -> CompletedProcess:
    """
    Wrapper around subproces.run() for running a podman command and getting
    the output.

    Args:
        args: The arguments to podman; may be a list or a single string
            (which will be split in shell quoting style)
        errmsg: An optional error message in the PodmanException (if it
            gets raised)
        **kwargs:
            Arbitrary keyword arguments passed to subprocess.run()

    Returns:
        The CompletedProcess from subprocess.run()
    """
    # TODO Use some of the logging functions from core to output/errors get into the test logs.
    kwargs.setdefault("stdout", subprocess.PIPE)
    kwargs.setdefault("stderr", subprocess.PIPE)
    kwargs.setdefault("encoding", "latin-1")
    cmd = ["podman"]
    if isinstance(args, str):
        cmd.extend(shlex.split(args))
    else:
        cmd.extend(args)
    try:
        return subprocess.run(cmd, **kwargs)
    except (CalledProcessError, TimeoutExpired) as err:
        raise PodmanException(errmsg, err.stdout, err.stderr) from err


def load(image_tarball_path: str, new_tag: str) -> None:
    """
    Load an image from a tarball and tag it as the given name.

    Args:
        image_tarball_path: The location of a tarball to load.
            Can be anything loadable with the `podman load` command.

        new_tag: The name the image should be tagged as.
    """
    proc = runpodman(
        [
            "load",
            "-q",
            "-i",
            image_tarball_path,
        ],
        check=True,
        errmsg="Could not load image from tarball",
    )
    mm = re.search(r"Loaded image: (\S+)", proc.stdout)
    if mm:
        imported_name = mm.group(1)
        if imported_name != new_tag:
            runpodman(
                ["tag", imported_name, new_tag],
                errmsg="Could not tag loaded image",
                check=True,
            )
    else:
        raise PodmanException("Could not get name of loaded image")


def pull(image: str) -> None:
    """
    Call podman to pull an image.

    Args:
        image: The name of the image to pull.
    """
    runpodman(
        [
            "pull",
            image,
        ],
        check=True,
        errmsg="Could not pull image",
    )


def run(
    image: str,
    name: str,
    *args: str,
    command: Sequence[str] = (),
    detach: bool = True,
    logfile: Optional[str] = None,
    hostname: Optional[str] = None,
    host_networking: bool = False,
    ports: Iterable[Tuple[int, int]] = (),
    pull_policy: str = "never",  # can't call it 'pull'
    volumes: Iterable[Tuple[str, str, str]] = (),
    spargs: Optional[Mapping[str, Any]] = None,
) -> CompletedProcess:
    """
    Use podman run to start a container.

    Args:
        image: The image to use for the container
        name: The name of the running container
        args: Optional arguments to pass to podman
        command: Optional CMD to pass to podman run
        detach: Whether to run the container in the background
        logfile: Optional, a path to a file to use for logging the output to
        hostname: The hostname of the container (if not using host networking)
        host_networking: True if we should use host networking, False otherwise
        ports: If not using host networking, a list of (from, to) pairs
        pull_policy: When to pull an image (one of "always", "never", "missing", "newer")
            Default: 'never'
        volumes: A list of (from, to, options) for bind-mounted volumes.
            options are comma-separated, e.g. "z,ro".
        spargs: Extra keyword arguments to subprocess.run
    """
    cmd = [
        "run",
        f"--name={name}",
        "--annotation=owner=osgtest",
        "--security-opt=label=disable",  # Avoid permission denied due to SELinux
        f"--pull={pull_policy}",
    ]
    if isinstance(command, str):  # a str is a sequence of str
        command = shlex.split(command)
    if detach:
        cmd.append("--detach")
    if host_networking:
        cmd.append("--net=host")
    else:
        cmd.append(f"--hostname={hostname or name}")
        for port in ports:
            outer, inner = port
            cmd.append(f"--publish={outer}={inner}")
    for volume in volumes:
        from_ = os.path.abspath(volume[0])
        to_ = volume[1]
        options_ = volume[2]
        cmd.append(f"--volume={from_}:{to_}:{options_}")
    if logfile:
        cmd.extend(
            [
                "--log-driver=k8s-file",
                f"--log-opt=path={os.path.abspath(logfile)}",
            ]
        )
    cmd.extend(args)
    cmd.append(image)
    cmd.extend(command)
    return runpodman(cmd, **(spargs or {}))


def stop(name: str, **kwargs) -> CompletedProcess:
    return runpodman(["stop", "--ignore", name], **kwargs)


def rm(name: str, **kwargs) -> CompletedProcess:
    return runpodman(["rm", "--force", "--ignore", name], **kwargs)


def logs(name: str) -> Optional[str]:
    """
    Get logs from a running or stopped container.
    :param name: The name of the container
    :return: The logs or None if there was an error getting them.
    """
    proc = runpodman(["logs", name])
    if proc.returncode == 0:
        return proc.stdout
    else:
        log_message(
            f"Getting logs of {name} failed.\n"
            + "\n".join(proc.stderr.splitlines()[0:-25])
        )
        return None


def cleanup():
    """
    Remove all containers owned by osgtest.
    """
    # TODO Delete pulled images too
    containers = runpodman("ps -q -a").stdout.splitlines()
    owned_containers = []
    for cnt in containers:
        try:
            inspection = json.loads(
                runpodman(["inspect", cnt]).stdout,
            )
        except JSONDecodeError as err:
            core.log_message(f"Could not inspect container {cnt}: {err}")
            continue
        try:
            is_owned_by_us = (
                inspection[0]['Config']['Annotations']['owner'] == "osgtest"
            )
        except (IndexError, KeyError):
            is_owned_by_us = False
        if is_owned_by_us:
            owned_containers.append(cnt)

    for cnt in owned_containers:
        runpodman(["rm", "--force", "--ignore", cnt])
