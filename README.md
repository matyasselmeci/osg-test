osg-test
========

- [Motivation](#motivation)
- [Running the OSG Automated Tests](#running-the-osg-automated-tests)
- [osg-test usage](#osg-test-usage)
- [Writing Tests](#writing-tests)

The `osg-test` package contains software that performs automated, functional integration tests an OSG Software installation. `osg-test` acts as the driver for the OSG Software's in the nightly [VM tests](https://github.com/opensciencegrid/vm-test-runs).

Motivation
----------

### Test Framework ###

Why should we consider using a different test framework than other people? Most automated testing frameworks (many, if not most, based on the venerable JUnit) support tests that are mostly independent of each other and consequently can be run in any order. Because we are doing integration tests, ours are necessarily more coupled than that. For example, testing globus-job-run requires that the appropriate RPMs are installed, a test user is created and set up with a certificate, the gatekeeper service is configured and running, and so forth. And then, when tests are done, we want to stop services and remove packages. We want to express all of these steps as tests, because they are all things that could fail as a result of our packaging and hence are part of the system under test.

Other testing frameworks often support fixtures, which bracket a set of tests with set-up and tear-down code. While this feature sounds promising, typically it has the wrong semantics for our use cases. Generally, we want to install, configure, and start a set of services once, then run many tests that use the services, then stop and remove them. The start-up costs are often high; for example, our VOMS setup takes roughly 40 seconds to configure and start, not counting installation time. The problem is that test fixtures are usually applied per test, with the idea that each test needs a clean environment in which to run.

### Design Requirements ###

-   Each test, or perhaps group of related tests, has dependencies that must be met. If they are not met at run time, then the test(s) should be skipped (and reported as such). There seem to be two classes of dependencies. *Sequence dependencies* define a DAG of tests, such that some test(s) must occur before others. This static information is used by the test framework to topologically sort the tests into a valid sequence. *State dependencies* define what state the system must be in for the test(s) to run. For example, a test may require a service to be running. If the prior test that starts the service fails, then the service is marked as not running, and the dependent test is skipped. State dependencies include information about which packages are installed.
-   Framework should be as minimal as possible and (ideally) unaware of our specific contents.
-   Atomic unit of work is a test.
-   All operations are expressed as tests, including installation, configuration, service start/stop, etc.
-   Tests should express requirements clearly and simply, so that distributed team of developers can work independently and with minimal confusion.

Installation
------------

To install `osg-test`, run the following commands as `root`:

```
git clone --recursive git@github.com:opensciencegrid/osg-test.git
cd osg-test
make install
cd osg-ca-generator
make install
```

Running the OSG Automated Tests
-------------------------------

**WARNING!** The tests and associated test framework run as `root` and may destroy your system!
It is **strongly** recommended that `osg-test` be run only on “disposable” systems — ones that can be reimaged or
reinstalled from scratch with little effort.
Virtual machines are ideal for this kind of test.

Run the tests (see below for options).
Be sure to direct the stdout/stderr to a file to get all the information from the test run (the dump-file option only
outputs some of the output to a file):

```
osg-test -vadi <PACKAGE> -r osg-testing > <output file> 2>&1
```

osg-test Script Usage
---------------------

Fundamentally, the `osg-test` script runs tests and reports on their results. However, the script can also perform many of the housekeeping tasks associated with setting up and tearing down the test environment, including adding (and later removing) a test user and its X.509 certificate, installing (and later removing) one or more RPMs, and so on. The following options are available:

| Option                       | Description                                                                                                                                                                                                                                |
|------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `-a`, `--add-user`           | Add and configure the test user account (see also `-u` below). By default, the script assumes that the test user account already exists and is configured with a valid X.509 certificate in its `.globus` directory.                       |
| `-c`, `--config` FILE        | Configuration file to use that specifies command-line options. See below for syntax                                                                                                                                                        |
| `-d`, `--dump-output`        | After all test output, print all commands and their output from the test run. Typically generates **a lot** of output.                                                                                                                     |
| `--df`, `--dump-file` FILE   | Like `--dump-output`, but prints the output to a file instead of the console                                                                                                                                                               |
| `-e`, `--exit-on-fail`       | Stop tests on first failure and output the results                                                                                                                                                                                         |
| `-g`, `--update-repo` REPO   | Enable the given repository when using yum to update packages. Use actual repo names, such as `osg-testing` and `osg-development`.                                                                                                         |
| `-i`, `--install` PACKAGE    | Before running tests, use `yum` to install the given package; may be specified more than once to install more than one top-level package. By default, the script assumes that the user has installed all packages to be tested in advance. |
| `-m`, `--manual-run`         | Speeds up osg-test in the case where it is run by hand. May not be suitable when running multiple instances of osg-test at once.                                                                                                           |
| `-n`, `--no-cleanup`         | Do not run clean-up steps. Opposite of `--cleanup`                                                                                                                                                                                         |
| `-p`, `--password` PASSWORD  | Password for the grid certificate of the test user. Defaults to the password that works with the X.509 certificate for the default test user.                                                                                              |
| `-s`, `--securepass`         | Prompt for the password instead of specifying it in the command line.                                                                                                                                                                      |
| `-r`, `--extra-repo` REPO    | Enable the given extra repository (in addition to production) when using yum to install packages. Use actual repo names, such as `osg-testing` and `osg-development`. Can be used multiple times with different repositories.              |
| `--update-release` RELEASE   | OSG release version (e.g. 3.2) to use when updating packages specified with -i.                                                                                                                                                            |
| `--tarballs`                 | Test client tarballs instead of RPM-based installation.                                                                                                                                                                                    |
| `--tarball-test-dir`         | The location of the tarball test files (if non-standard).                                                                                                                                                                                  |
| `--no-print-test-name`       | Do not print test name before command output                                                                                                                                                                                               |
| `--hostcert`                 | Create host cert                                                                                                                                                                                                                           |
| `-T`, `--no-tests`           | Skip running the tests themselves. Useful for running/testing just the set-up and/or clean-up steps.                                                                                                                                       |
| `-u`, `--test-user` USERNAME | Use the test user account with the given name. See also the `-a` and `-p` options.                                                                                                                                                         |
| `-v`, `--verbose`            | Print the name of each test as it is run; generally a good idea.                                                                                                                                                                           |
| `-h`, `--help`               | Print usage information and exit.                                                                                                                                                                                                          |
| `--version`                  | Print the script version and exit.                                                                                                                                                                                                         |

### Config file syntax ###

Unfortunately, the names of the variables in the config file are not the same as their names on the command line. Below is a translation table and an example config file.

| Command-Line         | Config File   | Default Value |
|:---------------------|:--------------|:--------------|
| --add-user           | adduser       | False         |
| --dump-output        | dumpout       | False         |
| --dump-file          | dumpfile      | None          |
| --extra-repo         | extrarepos    | []            |
| --exit-on-fail       | exitonfail    | False         |
| --update-repo        | updaterepos   | []            |
| --install            | packages      | []            |
| --manual-run         | manualrun     | False         |
| --no-cleanup         | skip_cleanup  | False         |
| --no-print-test-name | printtest     | False         |
| --password           | password      | vdttest       |
| --securepass         | securepass    | False         |
| --update-release     | updaterelease | None          |
| --tarballs           | tarballs      | False         |
| --no-tests           | skiptests     | False         |
| --test-user          | username      | vdttest       |
| --verbose            | verbose       | False         |
|                      | backupmysql   | False         |
|                      | hostcert      | False         |
|                      | nightly       | False         |
|                      | selinux       | False         |


Example configuration file:

``` console
[Config]
adduser=True
dumpout=True
dumpfile=/tmp/dumpfile
updaterepos=osg-development,osg-upcoming-development
packages=osg-gums,osg-voms
skip_cleanup=False
password=test
extrarepos=osg-testing,osg-prerelease
tarballs=False
skiptests=False
username=user
verbose=True
```

Writing Tests
-------------

All of the OSG Software automated tests are located in the `osg-test` software and package.

The software itself is in GitHub repository at <https://github.com/opensciencegrid/osg-test>; current code is kept in the `master` branch.

The software package is defined in our Subversion repository at `native/redhat/trunk/osg-test`.

### Directory Organization

The test software is written in Python and consists of:

-   A driver program, `osg-test`
-   A set of support libraries (Python modules) in `osgtest/library`
-   The tests themselves (also Python modules) in `osgtest/tests`
-   Extra files needed at runtime in `files`

The whole system uses the standard Python `unittest` framework to run. 

### Test Sequence

During a test run, the test modules are run in sequence as follows:

| File                 | When                                          | Purpose                                                               |
|:---------------------|:----------------------------------------------|:----------------------------------------------------------------------|
| `special_user.py`    | Tests not suppressed, or explicitly requested | Add user (if asked), Check user, Set up mapfile                       |
| `special_install.py` | Packages given                                | Check repositories, Clean yum cache, Install packages                 |
| `test_NNN_*.py`      | Tests not suppressed                          | Configure, Test, Tear down                                            |
| `special_cleanup.py` | Explicitly requested                          | Remove user (if added), Remove packages (if installed)                |

The `test_*` modules are organized roughly into three phases, based on the sequence number of the file:

| Test Files         | Purpose   |
|:-------------------|:----------|
| `test_[000-299]_*` | Set up    |
| `test_[300-699]_*` | Tests     |
| `test_[700-999]_*` | Tear down |

Coding Tips
-----------

It is important to know the basics of the Python `unittest` module; [read the documentation for it](http://docs.python.org/2.6/library/unittest.html). We build on top of the `unittest` module, by providing an `osgunittest` module that inherits from it.

### Basic Structure of a Test Module

Each test module must import the `osgunittest` library, plus whichever of the `osg-test` libraries are needed (conventionally with shortened aliases):

```python
import osgunittest

import osgtest.library.core as core
import osgtest.library.files as files
```

Then, a single test class is defined, deriving from `osgunittest.OSGTestCase`; the individual tests are sequentially numbered functions within the class:

```python
class TestFooBarBaz(osgunittest.OSGTestCase):

    def test_01_first_thing(self):
        # test stuff!

    def test_02_more(self):
        # test stuff!

    # Tests return (success) or raise (failure)
```

### Test Assertions

Within each test function, use the [TestCase object functions](http://docs.python.org/2.6/library/unittest.html#unittest.TestCase) to assert things that should be true:

```python
def test_99_example(self):
     result = do_something()
     self.assertTrue(result > 42, 'result too low')
     self.assertEqual(result, 57, 'result ok')
```

Be sure to learn and use all of the assertion functions, for greatest expressive power and clarity! For example, there are also:

-   `assertNotEqual`(*first*, *second*\[, *message*\])
-   `assertRaises`(*exception*, *callable*, …)

### Skipping Tests

There are two cases in which a test should be skipped, and they have different semantics in `osgunittest`:

1.  If the packages they depend on are not installed. This is called an `OkSkip`, since it does not indicate any sort of error.
2.  If the packages they depend on *are* installed, but required services were unavailable. This is called a `BadSkip`, since it indicates a cascading failure -- an error in a previous step that is causing problems in the current step.

One of the extensions that `osgunittest` adds to `unittest` is the ability to report on these kinds of failures.

The following `osgunittest` methods cause the test to be skipped with an `OkSkip` ( `OkSkipException` ):

- `skip_ok`(\[*message*=*None*\]):
  - skip, with optional message
- `skip_ok_if`(*expr*, \[*message*=*None*]):
  - skip if `expr` is True, with optional message
- `skip_ok_unless`(*expr*, \[*message*=*None*]):
  - skip if `expr` is False, with optional message

And the following `osgunittest` methods cause the test to be skipped with a `BadSkip` ( `BadSkipException` ):

- `skip_bad`(\[*message=None*\]):
  - skip, with optional message
- `skip_bad_if`(*expr*, \[*message*=*None*]):
  - skip if `expr` is True, with optional message
- `skip_bad_unless`(*expr*, \[*message*=*None*]):
  - skip if `expr` is False, with optional message

Note that the `OkSkip` methods are often not directly used, and convenience functions in `osgtest.core` are used instead.

#### Skipping Due to Missing Packages (OkSkip)

The following two patterns are used for skipping tests due to missing packages; use the simplest one for your case (or follow conventions of other tests):

Example 1: A single package with custom skip message

```python
def test_01_start_condor(self):
    core.skip_ok_unless_installed('condor',
                                  message='HTCondor not installed')
```

Example 2: A normal check of several packages at once:

```python
def test_02_condor_job(self):
    core.skip_ok_unless_installed('globus-gram-job-manager-condor',
                                  'globus-gram-client-tools',
                                  'globus-proxy-utils')
```

Note that old unit test code might be using the methods `core.rpm_is_installed()` or `core.missing_rpm()` for this purpose. These just printed a message if the test was to be skipped, but the test writer had to actually perform the skip manually.

The following patterns should be converted to match the first and second example, respectively:

Old Example 1:

```python
if not core.rpm_is_installed('condor'): # OLD CODE
    core.skip('not installed')
    return
```

Old Example 2:

```python
if core.missing_rpm('globus-gram-job-manager-condor', # OLD CODE
                    'globus-gram-client-tools',
                    'globus-proxy-utils'):
    return
```

**Note:** Add skip tests to **all** functions that depend on a particular package, not just the first one within a test module.

#### Skipping Due to Failure in Required Service (BadSkip)

Tests often require a service to be up and running. If the service is not running, then it is expected that the test will fail through no fault of the component being tested. These cascading failures often mask the root cause of the problem. In order to avoid that, we instead skip the test, and mark it as having been skipped due to a previous failure (a BadSkip). Note that these should be raised only *after* making sure the service has been installed.

The following examples show how this is done:

```python
core.skip_ok_unless_installed('globus-gram-job-manager-condor')
self.skip_bad_unless(core.state['condor.running-service'], message='HTCondor service not running')
```

```python
core.skip_ok_unless_installed( 'globus-gram-job-manager-pbs',
                               'globus-gram-client-tools',
                               'globus-proxy-utils',
                               'globus-gram-job-manager-pbs-setup-seg')

if (not core.state['torque.pbs-configured'] or
    not core.state['torque.pbs-mom-running'] or
    not core.state['torque.pbs-server-running'] or
    not core.state['globus.pbs_configured']):

    self.skip_bad('pbs not running or configured')
```

**Note:** Add skip tests to **all** functions that depend on a particular service, not just the first one within a test module.

### Running System Commands

Most tests run commands on the system; this is the nature of our testing environment. Thus, the test libraries have extra support for running system commands. Use these functions! Do not reinvent the wheel.

See the PyDoc for the `core` library for full documentation on the functions. Below are examples.

The basic system-call pattern:

```python
def test_99_made_up_example(self):
    command = ('/usr/bin/id','-u')
    status, stdout, stderr = core.system(command, True)
    fail = core.diagnose('id of test user', status, stdout, stderr)
    self.assertEqual(status, 0, fail) # Maybe more checks and assertions
```

In the most common case, you run the `core.system()` function, check its exit status against 0, and then possibly test its stdout and stderr for problems. There is a helper function for this common case:

```python
def test_01_web100clt(self):
    if core.missing_rpm('ndt'):
        return
    command = ('web100clt', '-v')
    stdout, stderr, fail = core.check_system(command, 'NDT client')
    result = re.search('ndt.+version', stdout, re.IGNORECASE)
    self.assertTrue(result is not None)
```

### Configuration and State

The test framework does not automatically preserve values across test modules, so you must do so yourself if needed. But, the test library does provide standard mechanisms for saving configuration values and system state.

Store all cross-module configuration values in `core.config` (a dictionary):

```python
def test_04_config_voms(self):
    core.config['voms.vo'] = 'osgtestvo'
    # ...
```

Record cross-module state values in `core.state` (a dictionary):

```python
def test_01_start_mysqld(self):
    core.state['mysql.started-server'] = False
    # Try to start MySQL service, raise on fail
    core.state['mysql.started-server'] = True
```

### Module-Wide Setup and Teardown

Sometimes a module needs certain operations to be done for setting up tests. For example, the tests for osg-configure involve importing the unit test modules provided by osg-configure itself, and need to add an entry to `sys.path`. This kind of setup should be put *inside* the test class; it will not get reliably run if it is only inside the module. Making separate test functions for the setup and teardown steps (named, for example, `test_00_setup` and `test_99_teardown`) is a good way of handling this.

Testing your changes
--------------------

Before you go and commit your changes, it's a good idea to make sure they don't break everything. Our [nightlies](http://vdt.cs.wisc.edu/tests/latest.html) run tests against the master version of osg-test so to avoid the embarassment of everyone knowing that your code is broken, you'll want to make sure your tests work!

### Fermicloud VMs

1.  Start a fermicloud VM and install the OSG RPMs, the latest build of `osg-test` and `osg-tested-internal`.
2.  Get rid of the old tests:
    ```
    # For RHEL 6, CentOS 6, and SL6
    [root@client ~]$ rm -rf /usr/lib/python2.6/site-packages/osgtest
    # For RHEL 7, CentOS 7, and SL7
    [root@client ~]$ rm -rf /usr/lib/python2.7/site-packages/osgtest
    ```
3.  `cd` into your clone of the `osg-test` repo and copy over your tests to your VM:
    ```
    # For RHEL 6, CentOS 6, and SL6 VMs
    [user@client ~]$ scp -r osgtest/ <VM HOSTNAME>:/usr/lib/python2.6/site-packages
    # For RHEL 7, CentOS 7, and SL7 VMs
    [user@client ~]$ scp -r osgtest/ <VM HOSTNAME>:/usr/lib/python2.7/site-packages
    ```
4.  Run the tests and monitor their output:
    ```
    [root@client ~]$ osg-test -vad > <OUTFILE> 2>&1 &
    [root@client ~]$ tail -f <OUTFILE>
    ```

### VM Universe

It's a good idea to test your changes in the VM Universe if you've made big changes like adding tests or changing entire test modules. Otherwise, you can go ahead and skip this step.

1.  SSH to `osghost.chtc.wisc.edu`
2.  Prepare a test run:
    ```
    [user@client ~]$ osg-run-tests -sl <TEST COMMENT>
    ```
3.  `cd` into the directory that is indicated by the output of `osg-run-tests`
4.  Run `git diff master` from your clone of the `osg-test` repo to get the changes that you're interested in and fill `test-changes.patch` with these changes.
5.  Edit `test-parameters.yaml` so that the `sources` section reads:
    ```
    sources:
       - opensciencegrid:master; 3.3; osg-testing
    ```
6.  Start the tests:
    ```
    [user@client ~]$ condor_submit_dag master-run.dag
    ```
