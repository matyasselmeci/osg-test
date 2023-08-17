"""
Functions for dealing with writing and tracking of files.

The most important part of this module is the backup mechanism.
Backups are identified by a (filepath, owner) pair--where owner is an
arbitraty string identifying the test component responsible for the file,
specifically its cleanup.

preserve() does the backup. It raises an error if a pair has been used.
Normally you would not call it directly, but call write(), append() or
replace(), and pass either the value of owner, or backup=False.
restore() puts the backup back to its original location.

Since one owner cannot back up the same file twice, if you modify a file
twice in one module then you must either call preserve() directly, or pass
an owner for the first append/replace/write call, and backup=False for all
subsequent calls to append/replace/write.

(You could also use a different owner for each change, but then you would
have to restore it for each owner you used else the cleanup test will fail).
"""

import glob
import os
import re
import shutil
import tempfile
import hashlib
from osgtest.library import core


_backup_directory = '/usr/share/osg-test/backups'
_backups = {}


def read(path, as_single_string=False):
    """Read the file at the path and return its contents as a list or string."""
    the_file = open(path, 'r')
    if as_single_string:
        contents = the_file.read()
    else:
        contents = the_file.readlines()
    the_file.close()
    return contents

def get_backup_path(path, owner):
    """Returns the file system path where the backup for 'path' for 'owner' is/will be kept"""
    return os.path.join(_backup_directory, os.path.basename(path) + '#' + owner)

def remove_stale_backup(path, owner):
    """Delete a backup file that we lost track of.

    Returns True if the file was removed, False otherwise.
    """
    if filesBackedup(path, owner):
        raise ValueError(f"Backup of '{path}' for '{owner}' is not stale")

    try:
        remove(get_backup_path(path, owner))
    except FileNotFoundError:
        pass

def preserve(path, owner):
    """Backup the file at path and remember it with the given owner.

    owner must be specified. The (path, owner) pair must not have been
    previously used in a call to preserve. Raises ValueError if either
    of these are not true.

    """
    if owner is None:
        raise ValueError('Must have owner string')

    backup_id = (path, owner)
    if backup_id in _backups:
        raise ValueError("Already have a backup of '%s' for '%s'" % (path, owner))

    backup_path = get_backup_path(path, owner)
    if os.path.exists(backup_path):
        raise ValueError("Backup already exists at '%s'" % (backup_path))

    if os.path.exists(path):
        if not os.path.isdir(_backup_directory):
            os.mkdir(_backup_directory)
        shutil.copy2(path, backup_path)
        _backups[backup_id] = {'path': backup_path,
                               'uid': os.stat(path).st_uid,
                               'gid': os.stat(path).st_gid}
        core.log_message("Backed up '%s' as '%s'" % (path, backup_path))
    else:
        _backups[backup_id] = None

def write(path, contents, owner=None, backup=True, chown=(0,0), chmod=0o600):
    """Write the contents to a file at the path.

    The 'owner' argument (default: None) is a string that identifies the owner
    of the file.  If the 'backup' argument is True (default), then any existing
    file at the path will be backed up for later restoration.  However, because
    backups are identified in part by 'owner', if 'backup' is True, then 'owner'
    must be defined.  Typically, a caller specifies either 'backup=False' to
    turn off backups (not recommended) or 'owner=[some string]' to set the owner
    for the backup.

    The 'chown' argument (default: (0, 0)) is a tuple of integers (uid, gid)
    that assigns the owner and group of the written file if the file doesn't
    exist. If the file does exist, the owner and group are copied from the
    previous file.

    The 'chmod' argument (default: 0600) is an integer that assigns the
    permissions of the written file if it doesn't exist. If it does exist, then
    the permissions are copied from the old file.
    """

    # The default arguments are invalid: Either "backup" must be false or the
    # "owner" must be specified.
    if (owner is None) and backup:
        raise ValueError('Must specify an owner or backup=False')

    # Write temporary file
    temp_fd, temp_path = tempfile.mkstemp(prefix=os.path.basename(path) + '.', suffix='.osgtest-new',
                                          dir=os.path.dirname(path))
    temp_file = os.fdopen(temp_fd, 'w')
    if isinstance(contents, (list, tuple)):
        temp_file.writelines(contents)
    else:
        temp_file.write(contents)
    temp_file.close()

    # Copy ownership and permissions
    if os.path.exists(path):
        old_stat = os.stat(path)
        os.chown(temp_path, old_stat.st_uid, old_stat.st_gid)
        os.chmod(temp_path, old_stat.st_mode)
    else:
        os.chown(temp_path, chown[0], chown[1])
        os.chmod(temp_path, chmod)

    # Back up existing file
    if backup:
        preserve(path, owner)

    # Atomically move temporary file into final location
    os.rename(temp_path, path)

    core.log_message('Wrote %d bytes to %s' % (os.stat(path).st_size, path))


def replace(path, old_line, new_line, owner=None, backup=True):
    """Replace an old line with a new line in given path.

    The 'owner' and 'backup' arguments are passed to write().
    """
    lines_to_write = []
    lines = read(path)
    for line in lines:
        if line.rstrip('\n') == old_line.rstrip('\n'):
            lines_to_write.append(new_line + '\n')
        else:
            lines_to_write.append(line.rstrip('\n') + '\n')
    write(path, lines_to_write, owner, backup)

def replace_regexpr(path, regexp, repl, owner=None, backup=True):
    """Replace an old line that matches regexp with repl in given path.
    The 'owner' and 'backup' arguments are passed to write().
    """
    lines = read(path)
    lines_to_write = [re.sub(regexp, repl, line) for line in lines]
    write(path, lines_to_write, owner, backup)

def append(path, contents, force=False, owner=None, backup=True):
    """Append the contents to the given file.

    Normally, if the contents already exist in the file, no action is taken.
    However, if the force argument is True, then the extra contents are always
    appended.

    The 'owner' and 'backup' arguments are the same as in write().
    """
    # The default arguments are invalid: Either "backup" must be false or the
    # "owner" must be specified.
    if backup:
        if owner is None:
            raise ValueError('Must specify an owner or backup=False')
        preserve(path, owner)

    if os.path.exists(path):
        old_contents = read(path)
    else:
        old_contents = []

    if (not force) and (contents in old_contents):
        return

    new_contents = old_contents + [contents]
    write(path, new_contents, backup=False)


def restore(path, owner, ignore_missing=False):
    """Restores the path to its state prior to being written by its owner."""
    backup_id = (path, owner)
    if backup_id not in _backups:
        if ignore_missing:
            return
        raise ValueError("No backup of '%s' for '%s'" % (path, owner))

    if os.path.exists(path):
        os.remove(path)
        core.log_message('Removed test %s' % (path))
    try:
        backup_path = _backups[backup_id]['path']
    except TypeError:
        backup_path = None
    if (backup_path is not None) and os.path.exists(backup_path):
        shutil.move(backup_path, path)
        os.chown(path, _backups[backup_id]['uid'], _backups[backup_id]['gid'])
        core.log_message('Restored original %s' % (path))
    del _backups[backup_id]


def remove(path, force=False):
    """Remove the path, which could be a file, symlink, empty directory, or file glob.
    Does nothing if the path is already missing.

    If the force argument is True, then this function will remove non-empty directories.
    """
    if re.search(r'[]*?]', path):
        for glob_path in glob.glob(path):
            if os.path.isfile(glob_path):
                os.unlink(glob_path)
            elif os.path.isdir(glob_path):
                if force:
                    shutil.rmtree(glob_path)
                else:
                    os.rmdir(glob_path)                    
    elif os.path.isdir(path):
        if not os.listdir(path):
            os.rmdir(path)
        else:
            if force:
                shutil.rmtree(path)
            else:
                # Go ahead and try the rmdir to raise an exception
                os.rmdir(path)
    elif os.path.isfile(path) or os.path.islink(path):
        os.unlink(path)

def filesBackedup(path, owner):
    """ Returns true if there already exists a backup for a file otherwise
    returns False
    """
    if owner is None:
        raise ValueError('Must have owner string')

    backup_id = (path, owner)
    if backup_id in _backups:
        return True
    else:
        return False


def safe_makedirs(directory, mode=0o777):
    """Create a directory and all its parent directories, unless it already
    exists.

    """
    if not os.path.isdir(directory):
        os.makedirs(directory, mode)

def checksum_file(path):
    """Return the md5 checksum of a file """
    if os.path.exists(path):
        return hashlib.md5(open(path,'rb').read()).hexdigest()
    else:
        return False

def checksum_files_match(file1, file2):
    """Returns true if the checksum of the files matches
    
    """
    checksum1 = checksum_file(file1)
    checksum2 = checksum_file(file2)
    if checksum1 and checksum2:
        return checksum1==checksum2
    else:
        return False

def preserve_and_remove(path, owner):
    remove_stale_backup(path, owner)
    preserve(path, owner)
    try:
        remove(path)
    except FileNotFoundError:
        pass
