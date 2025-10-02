import pwd
import os
import shutil
import tempfile

import cagen
from osgtest.library import core
from osgtest.library import files
from osgtest.library import osgunittest


VONAME = "osgtestvo"
VOPORT = 15151

def advertise_lsc(vo, hostcert='/etc/grid-security/hostcert.pem'):
    """Create the VO directory and .lsc file under /etc/grid-security/vomsdir for the given VO"""
    host_dn, host_issuer = cagen.certificate_info(hostcert)
    hostname = core.get_hostname()
    lsc_dir = os.path.join('/etc/grid-security/vomsdir', vo)
    if not os.path.isdir(lsc_dir):
        os.makedirs(lsc_dir)
    vo_lsc_path = os.path.join(lsc_dir, hostname + '.lsc')
    files.write(vo_lsc_path, (host_dn + '\n', host_issuer + '\n'), backup=False, chmod=0o644)


def advertise_vomses(vo, hostcert='/etc/grid-security/hostcert.pem'):
    """Edit /etc/vomses to advertise the current host as the VOMS server for the given VO.
    Caller is responsible for preserving and restoring /etc/vomses.
    """
    host_dn, _ = cagen.certificate_info(hostcert)
    hostname = core.get_hostname()
    vomses_path = '/etc/vomses'
    contents = ('"%s" "%s" "%d" "%s" "%s"\n' %
                (vo, hostname, VOPORT, host_dn, vo))
    files.write(vomses_path, contents, backup=False, chmod=0o644)


def destroy_lsc(vo):
    """Remove the VO directory and .lsc file from under /etc/grid-security/vomsdir"""
    lsc_dir = os.path.join('/etc/grid-security/vomsdir', vo)
    if os.path.exists(lsc_dir):
        shutil.rmtree(lsc_dir)


def destroy_voms_conf(vo):
    """Remove the VOMS config for the VO"""
    vodir = os.path.join('/etc/voms', vo)
    shutil.rmtree(vodir, ignore_errors=True)


def proxy_direct(username=None, password=None,
                 cert_path=None, key_path=None,
                 fqan=f'/{VONAME}/Role=NULL/Capability=NULL'):
    f"""Generate a user proxy and directly sign VOMS attributes using the test VOMS cert and key
    - username: owner of the generated proxy file (default osg-test username)
    - password: proxy password (default: osg-test password)
    - cert_path: path to the user certificate (default: ~username/.globus/usercert.pem)
    - key_path: path to the user key (default: ~username/.globus/userkey.pem)
    - fqan: VOMS attribute (default: /{VONAME}/Role=NULL/Capability=NULL)
    """
    if username:
        user = pwd.getpwnam(username)
        uid = user.pw_uid
        gid = user.pw_gid
    else:
        username = core.options.username
        uid = core.state['user.uid']
        gid = core.state['user.gid']

    if not password:
        password = core.options.password
    if not password.endswith('\n'):
        password = password + '\n'
    if not cert_path:
        cert_path = os.path.join(os.path.expanduser(f'~{username}'), '.globus/usercert.pem')
    if not key_path:
        key_path = os.path.join(os.path.expanduser(f'~{username}'), '.globus/userkey.pem')

    # voms-proxy-fake requires that the user cert/key are owned by the user running the command
    filemap = dict()
    for src in (cert_path, key_path):
        dest = tempfile.NamedTemporaryFile()
        filemap[src] = dest
        shutil.copy2(src, dest.name)

    proxy_path = f'/tmp/x509up_u{core.state["user.uid"]}'
    command = ('voms-proxy-fake',
               '-rfc',
               '-debug',
               '-bits', '2048',
               '-voms', VONAME,
               '-uri', f'{core.get_hostname()}:{VOPORT}',
               '-fqan', fqan,
               '-cert', filemap[cert_path].name,
               '-key', filemap[key_path].name,
               '-hostcert', core.config['certs.hostcert'],
               '-hostkey', core.config['certs.hostkey'],
               '-out', proxy_path)
    core.check_system(command, 'Run voms-proxy-fake', stdin=password)
    os.chown(proxy_path, uid, gid)


def can_make_proxy():
    """Return True if the packages necessary for making a proxy are installed.
    This is either voms-clients-cpp (which provides voms-proxy-fake),
    or voms-server + dependencies + any voms client.
    """
    return core.dependency_is_installed("voms-clients-cpp")


def skip_ok_unless_can_make_proxy():
    """OkSkip if the dependencies for creating VOMS proxies are not installed."""
    if not can_make_proxy():
        raise osgunittest.OkSkipException('Required packages for creating VOMS proxies not installed')
