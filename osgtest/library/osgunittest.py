"""
Extended unit testing framework for OSG.

In order to meet the requirements of OSG testing, some extensions to the
standard Python unittest library have been made:
- additional test statuses 'OkSkip' and 'BadSkip'
"""
# quiet all the 'Method could be a function' or 'Invalid name' warnings;
# I'm following the conventions unittest set.
# pylint: disable=R0201,C0103
import re
import contextlib
import sys
import time
import unittest
from typing import TextIO, List, Tuple, Iterable
from unittest import TestCase
from unittest.runner import TextTestResult
from unittest.util import safe_repr
import warnings

from osgtest.library import service

# Copied from unittest.case
_subtest_msg_sentinel = object()


# Define the classes we need to handle the two new types of test results: ok
# skip, and bad skip.

class OkSkipException(AssertionError):
    """
    This exception represents a test getting skipped for a benign reason,
    for example the component it is testing not being installed.
    """
    pass

class ExcludedException(AssertionError):
    """
    This exception represents a test getting excluded because it is not
    normally run for the given osg release series.
    """
    pass

class BadSkipException(AssertionError):
    """
    This exception represents a test getting skipped because success is
    impossible due to a previous error, for example a service that could
    not run.
    """
    pass

class TimeoutException(AssertionError):
    """
    This exceptions represents a test reaching a timeout described by
    the 'timeout' parameter of core._run_command()
    """
    pass


class OSGTestCase(TestCase):
    """
    A class whose instances are single test cases.
    An extension of unittest.TestCase with support for the 'OkSkip' and
    'BadSkip' statuses.

    See documentation for unittest.TestCase for usage.
    """
    def defaultTestResult(self) -> "OSGTestResult":
        return OSGTestResult()

    def skip_ok(self, message=None):
        "Skip (ok) unconditionally"
        raise OkSkipException(message)

    def skip_ok_if(self, expr, message=None):
        "Skip (ok) if the expression is true"
        if expr:
            raise OkSkipException(message)

    def skip_ok_unless(self, expr, message=None):
        "Skip (ok) if the expression is false"
        if not expr:
            raise OkSkipException(message)

    def skip_bad(self, message=None):
        "Skip (bad) unconditionally"
        raise BadSkipException(message)

    def skip_bad_if(self, expr, message=None):
        "Skip (bad) if the expression is true"
        if expr:
            raise BadSkipException(message)

    def skip_bad_unless(self, expr, message=None):
        "Skip (bad) if the expression is false"
        if not expr:
            raise BadSkipException(message)

    def skip_bad_unless_running(self, *services):
        "Skip (bad) if one of the listed services is not running"
        for svc in services:
            self.skip_bad_unless(service.is_running(svc), "%s is not running" % svc)

    def assertSubsetOf(self, a, b, message=None):
        "Ensure that a is a subset of b "
        if not set(a).issubset(set(b)):
            raise AssertionError(message)

    def failIfSubsetOf(self, a, b, message=None):
        "Ensure that a is not a subset of b"
        if set(a).issubset(set(b)):
            raise AssertionError(message)

    def assertEqualVerbose(self, actual, expected, message=None):
        aftermessage = "actual %s != expected %s" % (safe_repr(actual), safe_repr(expected))
        if message:
            fullmessage = "%s (%s)" % (message, aftermessage)
        else:
            fullmessage = aftermessage
        self.assertEqual(actual, expected, fullmessage)

    def assertRegexInList(self, test_list, regex, message=None):
        """Assert that a member of the list matches the regex (using re.search())"""
        self.assertTrue(any(re.search(regex, line) for line in test_list), message)

    def assertRegexNotInList(self, test_list, regex, message=None):
        """Assert that no member of the list matches the regex (using re.search())"""
        self.assertFalse(any(re.search(regex, line) for line in test_list), message)

    # This is mostly a copy of the method from unittest in python 2.4.
    # There is some code here to test if the 'result' object accepts 'skips',
    # since the original TestResult object does not. If it does not, an
    # okSkip is considered a success, and a badSkip is considered a failure
    # (or an error if it happens in setUp).
    def run(self, result=None, **kwargs):
        """
        Run a single test method. Catch any Exceptions the method raises
        and count them as Errors, Failures, OkSkips, or BadSkips depending
        on the exception class.

        Results are counted in a TestResult instance, 'result'. If result
        contains support for skips (which an OSGTestResult instance does),
        then OkSkipExceptions and BadSkipExceptions are counted appropriately.
        If not, an OkSkipException is counted as a success, and a
        BadSkipException is counted as an Error or a Failure depending on when
        it occurs.
        """
        orig_result = result
        if result is None:
            result = self.defaultTestResult()
            startTestRun = getattr(result, 'startTestRun', None)
            if startTestRun is not None:
                startTestRun()

        result.startTest(self)
        testMethod = getattr(self, self._testMethodName)
        isOSGTestResult = isinstance(result, OSGTestResult)
        if (getattr(self.__class__, "__unittest_skip__", False) or
            getattr(testMethod, "__unittest_skip__", False)):
            # If the class or method was skipped.
            try:
                skip_why = (getattr(self.__class__, '__unittest_skip_why__', '')
                            or getattr(testMethod, '__unittest_skip_why__', ''))
                self._addSkip(result, self, skip_why)
            finally:
                result.stopTest(self)
            return
        expecting_failure_method = getattr(testMethod,
                                           "__unittest_expecting_failure__", False)
        expecting_failure_class = getattr(self,
                                          "__unittest_expecting_failure__", False)
        expecting_failure = expecting_failure_class or expecting_failure_method
        outcome = _Outcome(result)

        try:
            self._outcome = outcome

            with outcome.testPartExecutor(self):
                self.setUp()
            if outcome.success:
                outcome.expecting_failure = expecting_failure
                with outcome.testPartExecutor(self, isTest=True):
                    testMethod()
                outcome.expecting_failure = False
                with outcome.testPartExecutor(self):
                    self.tearDown()

            self.doCleanups()
            if isOSGTestResult:
                for test, reason in outcome.okSkipped:
                    result.addOkSkip(test, reason)
                for test, reason in outcome.badSkipped:
                    result.addBadSkip(test, reason)
                for test, reason in outcome.excluded:
                    result.addExclude(test, reason)
                for test, reason in outcome.timedOut:
                    result.addTimeout(test, reason)
            self._feedErrorsToResult(result, outcome.errors)
            if outcome.success:
                if expecting_failure:
                    if outcome.expectedFailure:
                        self._addExpectedFailure(result, outcome.expectedFailure)
                    else:
                        self._addUnexpectedSuccess(result)
                else:
                    result.addSuccess(self)
            return result
        finally:
            result.stopTest(self)
            if orig_result is None:
                stopTestRun = getattr(result, 'stopTestRun', None)
                if stopTestRun is not None:
                    stopTestRun()

            # explicitly break reference cycles:
            # outcome.errors -> frame -> outcome -> outcome.errors
            # outcome.expectedFailure -> frame -> outcome -> outcome.expectedFailure
            outcome.errors.clear()
            outcome.expectedFailure = None

            # clear the outcome, no more needed
            self._outcome = None

    #
    #
    # Private methods copied from parent
    #
    #

    def _feedErrorsToResult(self, result, errors):
        for test, exc_info in errors:
            if isinstance(test, _SubTest):
                result.addSubTest(test.test_case, test, exc_info)
            elif exc_info is not None:
                if issubclass(exc_info[0], self.failureException):
                    result.addFailure(test, exc_info)
                else:
                    result.addError(test, exc_info)

    def _addExpectedFailure(self, result, exc_info):
        try:
            addExpectedFailure = result.addExpectedFailure
        except AttributeError:
            warnings.warn("TestResult has no addExpectedFailure method, reporting as passes",
                          RuntimeWarning)
            result.addSuccess(self)
        else:
            addExpectedFailure(self, exc_info)

    def _addUnexpectedSuccess(self, result):
        try:
            addUnexpectedSuccess = result.addUnexpectedSuccess
        except AttributeError:
            warnings.warn("TestResult has no addUnexpectedSuccess method, reporting as failure",
                          RuntimeWarning)
            # We need to pass an actual exception and traceback to addFailure,
            # otherwise the legacy result can choke.
            try:
                raise _UnexpectedSuccess from None
            except _UnexpectedSuccess:
                result.addFailure(self, sys.exc_info())
        else:
            addUnexpectedSuccess(self)


class OSGTestResult(unittest.TestResult):
    """
    Extended holder of test result information.

    Like unittest.TestResult, it does not need to be manipulated by test
    writers. In addition to what's in TestResult, each instance also holds
    collections of skipped tests, separated according to whether or not the
    skip was "bad". The collections contain (testcase, exceptioninfo) tuples,
    where exceptioninfo is a formatted traceback, and testcase is the actual
    OSGTestCase object.
    """

    def __init__(self):
        unittest.TestResult.__init__(self)
        self.okSkips = []
        self.badSkips = []
        self.excludes = []
        self.timeouts = []

    def addOkSkip(self, test, err):
        """Called when an ok skip has occurred. 'err' is a tuple as returned by sys.exc_info()"""
        self.okSkips.append((test, self.osg_exc_info_to_string(err, test)))

    def addExclude(self, test, err):
        """Called when a test is excluded. 'err' is a tuple as returned by sys.exc_info()"""
        self.excludes.append((test, self.osg_exc_info_to_string(err, test)))

    def addBadSkip(self, test, err):
        """Called when a bad skip has occurred. 'err' is a tuple as returned by sys.exc_info()"""
        self.badSkips.append((test, self.osg_exc_info_to_string(err, test)))

    def addTimeout(self, test, err):
        """Called when a timeout has occurred. 'err' is a tuple as returned by sys.exc_info()"""
        self.timeouts.append((test, self.osg_exc_info_to_string(err, test)))

    def osg_exc_info_to_string(self, err, test):
        """Get the string description out of an Ok/BadSkipException.
        Pass it up to the parent if the exception is not one of those.
        """
        exctype, value, _ = err

        if exctype in (OkSkipException, ExcludedException, BadSkipException, TimeoutException):
            return str(value)
            # TODO Need some way to print out the line that caused the skip
            # if there is no message.
            # This requires using the traceback module and filtering out
            # stack frames we don't care about.
            #return traceback.format_tb(tb)[-1] + ' ' + ''.join(traceback.format_exception_only(exctype, value))
        else:
            return self._exc_info_to_string(err, test)

    def wasSuccessful(self):
        """Tells whether or not this result was a success, considering bad skips as well."""
        return len(self.failures) == len(self.errors) == len(self.badSkips) == len(self.timeouts) == 0

    def wasPerfect(self):
        """Tells whether or not this result was perfect, i.e. successful and without any skips."""
        return self.wasSuccessful() and len(self.okSkips) == 0

    def __repr__(self):
        cls = self.__class__
        return "<%s.%s run=%d errors=%d failures=%d okSkips=%d badSkips=%d timeouts=%d>" % (
            cls.__module__,
            cls.__name__,
            self.testsRun,
            len(self.errors),
            len(self.failures),
            len(self.okSkips),
            len(self.badSkips),
            len(self.timeouts))


class OSGTextTestResult(OSGTestResult, TextTestResult):
    """
    A test result that formats results and prints them to a stream.

    Used by OSGTextTestRunner.

    The user should not have to instantiate this directly; an instance will be
    created by OSGTextTestRunner.
    """
    def __init__(self, stream=None, descriptions=None, verbosity=None):
        super().__init__(stream, descriptions, verbosity)
        self.timeouts = []
        self.badSkips = []
        self.okSkips = []
        self.excludes = []

    def printErrors(self):
        """Print a list of errors, failures and skips to the stream."""
        if self.dots or self.showAll:
            self.stream.writeln()
        self.printErrorList('ERROR', self.errors)
        self.printErrorList('FAIL', self.failures)
        self.printErrorList('TIMEOUT', self.timeouts)
        self.printSkipList('BAD SKIPS', self.badSkips)
        self.printSkipList('OK SKIPS', self.okSkips)
        self.printSkipList('EXCLUDED', self.excludes)

    def printErrorList(self, flavour: str, errors: Iterable[Tuple[TestCase, str]]):
        """Print all of one flavor of error to the stream."""
        for test, err in errors:
            self.stream.writeln(self.separator1)
            self.stream.writeln("%s: %s" % (flavour, self.getDescription(test)))
            self.stream.writeln(self.separator2)
            self.stream.writeln(str(err))

    def printSkipList(self, flavour: str, skips: Iterable[Tuple[TestCase, str]]):
        """Print all of one flavor of skip to the stream."""
        if not skips:
            return

        self.stream.writeln(self.separator1)
        self.stream.writeln("%s:" % flavour)
        self.stream.writeln(self.separator2)
        for test, skip in skips:
            self.stream.writeln("%s %s" % (self.getDescription(test), str(skip)))
        self.stream.writeln("")

    def addOkSkip(self, test, reason):
        OSGTestResult.addOkSkip(self, test, reason)
        if self.showAll:
            self.stream.writeln("okskip")
        elif self.dots:
            self.stream.write("s")
            self.stream.flush()

    def addExclude(self, test, reason):
        OSGTestResult.addExclude(self, test, reason)
        if self.showAll:
            self.stream.writeln("excluded")
        elif self.dots:
            self.stream.write("x")
            self.stream.flush()

    def addBadSkip(self, test, reason):
        OSGTestResult.addBadSkip(self, test, reason)
        if self.showAll:
            self.stream.writeln("BADSKIP")
        elif self.dots:
            self.stream.write("S")
            self.stream.flush()

    def addTimeout(self, test, reason):
        OSGTestResult.addTimeout(self, test, reason)
        if self.showAll:
            self.stream.writeln("TIMEOUT")
        elif self.dots:
            self.stream.write("T")
            self.stream.flush()

class OSGTextTestRunner(unittest.TextTestRunner):
    """Extended unittest.TextTestRunner with support for okSkips / badSkips / timeouts."""
    resultclass = OSGTextTestResult

    def _makeResult(self) -> OSGTextTestResult:
        return self.resultclass(self.stream, self.descriptions, self.verbosity)

    def run(self, test):
        """
        Run an actual set of tests, time the run, collect and
        summarize the results.

        This is an extended version of unittest.TextTestRunner.run() which
        displays okSkips, badSkips, and timeouts.
        """
        result = self._makeResult()
        unittest.signals.registerResult(result)
        result.failfast = self.failfast
        result.buffer = self.buffer
        result.tb_locals = self.tb_locals
        with warnings.catch_warnings():
            if self.warnings:
                # if self.warnings is set, use it to filter all the warnings
                warnings.simplefilter(self.warnings)
                # if the filter is 'default' or 'always', special-case the
                # warnings from the deprecated unittest methods to show them
                # no more than once per module, because they can be fairly
                # noisy.  The -Wd and -Wa flags can be used to bypass this
                # only when self.warnings is None.
                if self.warnings in ['default', 'always']:
                    warnings.filterwarnings('module',
                            category=DeprecationWarning,
                            message=r'Please use assert\w+ instead.')
            startTime = time.time()
            startTestRun = getattr(result, 'startTestRun', None)
            if startTestRun is not None:
                startTestRun()
            try:
                test(result)
            finally:
                stopTestRun = getattr(result, 'stopTestRun', None)
                if stopTestRun is not None:
                    stopTestRun()
            stopTime = time.time()
        timeTaken = stopTime - startTime
        result.printErrors()
        if hasattr(result, 'separator2'):
            self.stream.writeln(result.separator2)
        run = result.testsRun
        self.stream.writeln("Ran %d test%s in %.3fs" %
                            (run, run != 1 and "s" or "", timeTaken))
        self.stream.writeln()

        expectedFails = unexpectedSuccesses = skipped = 0
        try:
            results = map(len, (result.expectedFailures,
                                result.unexpectedSuccesses,
                                result.okSkips,
                                result.badSkips,
                                result.timeouts))
        except AttributeError:
            pass
        else:
            expectedFails, unexpectedSuccesses, okSkipped, badSkipped, timeouts = results

        infos = []
        if not result.wasSuccessful():
            failed, errored, okSkipped, badSkipped, timeouts = map(len,
                (result.failures, result.errors, result.okSkips, result.badSkips, result.timeouts))
            if failed:
                infos.append("failures=%d" % failed)
            if errored:
                infos.append("errors=%d" % errored)
            if badSkipped:
                infos.append("badSkips=%d" % badSkipped)
            if timeouts:
                infos.append("timeouts=%d" % timeouts)
            if okSkipped:
                infos.append("okSkips=%d" % okSkipped)
        else:
            self.stream.write("OK")
        if skipped:
            infos.append("skipped=%d" % skipped)
        if expectedFails:
            infos.append("expected failures=%d" % expectedFails)
        if unexpectedSuccesses:
            infos.append("unexpected successes=%d" % unexpectedSuccesses)
        if infos:
            self.stream.writeln(" (%s)" % (", ".join(infos),))
        else:
            self.stream.write("\n")

        return result

class OSGTestSuite(unittest.TestSuite):
    """
    An extended version of unittest.TestSuite that passes arbitrary keyword args
    onto the test cases
    """
    def run(self, result):
        for test in self._tests:
            if result.shouldStop:
                break
            test(result)
        return result

class OSGTestLoader(unittest.TestLoader):
    """
    An extended version of unittest.TestSuite that creates OSG Test Suites
    when loading tests
    """
    suiteClass = OSGTestSuite


#
#
# Private classes copied/overridden from unittest.case
#
#
class _ShouldStop(Exception):
    """
    The test should stop.
    """

class _UnexpectedSuccess(Exception):
    """
    The test was supposed to fail, but it didn't!
    """


class _Outcome(object):
    # Test outcome
    # Modified to support badSkipped, excluded, and timedOut.
    # skips are treated like okSkip
    def __init__(self, result=None):
        self.expecting_failure = False
        self.result = result
        self.result_supports_subtests = hasattr(result, "addSubTest")
        self.success = True
        self.okSkipped = []
        self.badSkipped = []
        self.excluded = []
        self.timedOut = []
        self.expectedFailure = None
        self.errors = []

    @contextlib.contextmanager
    def testPartExecutor(self, test_case, isTest=False):
        old_success = self.success
        self.success = True
        try:
            yield
        except KeyboardInterrupt:
            raise
        except (unittest.case.SkipTest, OkSkipException) as e:
            self.success = False
            self.okSkipped.append((test_case, str(e)))
        except BadSkipException as e:
            self.success = False
            self.badSkipped.append((test_case, str(e)))
        except ExcludedException as e:
            self.excluded.append((test_case, str(e)))
        except TimeoutException as e:
            self.success = False
            self.timedOut.append((test_case, str(e)))
        except _ShouldStop:
            pass
        except:
            exc_info = sys.exc_info()
            if self.expecting_failure:
                self.expectedFailure = exc_info
            else:
                self.success = False
                self.errors.append((test_case, exc_info))
            # explicitly break a reference cycle:
            # exc_info -> frame -> exc_info
            exc_info = None
        else:
            if self.result_supports_subtests and self.success:
                self.errors.append((test_case, None))
        finally:
            self.success = self.success and old_success


class _SubTest(unittest.TestCase):

    def __init__(self, test_case, message, params):
        super().__init__()
        self._message = message
        self.test_case = test_case
        self.params = params
        self.failureException = test_case.failureException

    def runTest(self):
        raise NotImplementedError("subtests cannot be run directly")

    def _subDescription(self):
        parts = []
        if self._message is not _subtest_msg_sentinel:
            parts.append("[{}]".format(self._message))
        if self.params:
            params_desc = ', '.join(
                "{}={!r}".format(k, v)
                for (k, v) in sorted(self.params.items()))
            parts.append("({})".format(params_desc))
        return " ".join(parts) or '(<subtest>)'

    def id(self):
        return "{} {}".format(self.test_case.id(), self._subDescription())

    def shortDescription(self):
        """Returns a one-line description of the subtest, or None if no
        description has been provided.
        """
        return self.test_case.shortDescription()

    def __str__(self):
        return "{} {}".format(self.test_case, self._subDescription())
