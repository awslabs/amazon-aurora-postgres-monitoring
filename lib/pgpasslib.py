""":py:meth:`pgpasslib.getpass` will attempt to return the password for the
specified host, port, database name, and username from the PostgreSQL Password
file.

The password file from the ``.pgpass`` file in the current user's home
directory or as specified by the ``PGPASSFILE`` environment variable
or on Windows the pgpass.conf file in the %APPDATA%\postgresql folder

Example:

.. code:: python

    import pgpasslib

    password = pgpasslib.getpass('localhost', 5432, 'postgres', 'postgres')
    if not password:
        raise ValueError('Did not find a password in the .pgpass file')

"""
import getpass as stdlib_getpass
import logging
import os
from os import path
import re
import stat
import sys
import platform

__version__ = '1.1.0'

LOGGER = logging.getLogger(__name__)

PYTHON3 = True if sys.version_info > (3, 0, 0) else False

if PYTHON3:  # pragma: no cover
    unicode = bytes

DEFAULT_HOST = 'localhost'
DEFAULT_PORT = 5432
DEFAULT_USER = stdlib_getpass.getuser()
DEFAULT_DBNAME = DEFAULT_USER

PATTERN = re.compile(r'^(.*):(.*):(.*):(.*):(.*)$', re.MULTILINE)


def getpass(host=DEFAULT_HOST, port=DEFAULT_PORT, dbname=DEFAULT_DBNAME,
            user=DEFAULT_USER):
    """Return the password for the specified host, port, dbname and user.
    :py:const:`None` will be returned if a password can not be found for the
    specified  connection parameters.

    If the password file can not be located, a :py:class:`FileNotFound`
    exception will be raised.

    If the password file is group or world readable, the file will not be read,
    per the specification, and a :py:class:`InvalidPermissions` exception will
    be raised.

    If an entry in the password file is not parsable, a
    :py:class:`InvalidPermissions` exception will be raised.

    :param str host: PostgreSQL hostname
    :param port: PostgreSQL port
    :type port: int or str
    :param str dbname: Database name
    :param str user: Database role/user
    :rtype: str
    :raises: FileNotFound
    :raises: InvalidPermissions
    :raises: InvalidEntry

    """
    if not isinstance(port, int):
        port = int(port)
    for entry in _get_entries():
        if entry.match(host, port, dbname, user):
            return entry.password
    return None


class PgPassException(Exception):
    """Base exception for all pgpasslib exceptions"""
    MESSAGE = 'Base Exception: {}'

    def __str__(self):
        return self.MESSAGE.format(*self.args)


class FileNotFound(PgPassException):
    """Raised when the password file specified in the PGPASSFILE environment
    variable or ``.pgpass`` file in the user's home directory does not exist.

    """
    MESSAGE = 'No such file "{0}"'


class InvalidEntry(PgPassException):
    """Raised when the password file can not be parsed properly due to errors
    in the entry format.

    """
    MESSAGE = 'Error validating {0} value "{1}"'


class InvalidPermissions(PgPassException):
    """Raised when the password file specified in the PGPASSFILE environment
    variable or ``.pgpass`` file in the user's home directory has group or
    world readable permission bits set.

    """
    MESSAGE = 'Invalid Permissions for {0}: {1}'


class _Entry(object):
    """Encapsulate a single entry from the pgpass file and provide a method
    for checking to see if the entry matches the host, port, dbname and user
    vaues.

    :param str host: The hostname or path to the Unix Socket
    :param port: The port
    :type port: int or str
    :param str dbname: The database name
    :param str user: The user or role name
    :param str password: The password

    """

    def __init__(self, host, port, dbname, user, password):
        self.host = self._sanitize_str('host', host)
        if port is not None:
            self.port = self._sanitize_port(port)
        self.dbname = self._sanitize_str('dbname', dbname)
        self.user = self._sanitize_str('user', user)
        self.password = self._sanitize_str('password', password)

    def match(self, host, port, dbname, user):
        """Evaluate the host, port, dbname, and user combination against the
        entry values.

        :param str host: The hostname or path to the Unix Socket
        :param int port: The port
        :param str dbname: The database name
        :param str user: The user or role name
        :rtype: bool

        """
        return all([any([self.host == '*', self.host == host]),
                    any([self.port == '*', self.port == port]),
                    any([self.dbname == '*', self.dbname == dbname]),
                    any([self.user == '*', self.user == user])])

    @staticmethod
    def _sanitize_port(value):
        """Make sure the port is either an integer or ``*``.

        :param value: The port value to sanitize
        :type value: int or str
        :rtype: int or str
        :raises: InvalidEntry

        """
        try:
            return int(value)
        except ValueError:
            if value == '*':
                return value
            else:
                raise InvalidEntry('port', value)

    @staticmethod
    def _sanitize_str(name, value):
        """Ensures that the value passed in is a string, raising an exception
        if not.

        Per the spec, all instances of ``\:`` are replaced with ``:``.

        :param str name: The attribute name
        :param str value: The attribute value
        :rtype: str
        :raises: InvalidEntry

        """
        if not isinstance(value, (bytes, str, unicode)):
            raise InvalidEntry(name, value)
        return value.replace('\:', ':')


def _file_path():
    """Return the path to the Password file, checking first for the value of
    the PGPASSFILE environment variable, falling back to ``.pgpass`` in the
    user's home directory.

    On Microsoft Windows, it is assumed that the file is stored in a directory
    that is secure, so no special permissions check is made.

    :return: str
    :raises: FileNotFound
    :raises: InvalidPermissions

    """
    file_path = os.environ.get('PGPASSFILE', _default_path())
    if not path.exists(file_path):
        raise FileNotFound(file_path)

    if platform.system() != 'Windows':
        s = os.stat(file_path)
        if ((s.st_mode & stat.S_IRGRP == stat.S_IRGRP) or
            (s.st_mode & stat.S_IROTH == stat.S_IROTH)):
            raise InvalidPermissions(file_path, oct(stat.S_IMODE(s.st_mode)))

    return file_path


def _default_path():
    """Return the default path of .pgpass in the current user's home directory

    :rtype: str

    """
    if platform.system() == 'Windows':
        return path.join(os.getenv('APPDATA',
                                   path.join(path.expanduser('~'), 'AppData')),
                         'postgresql', 'pgpass.conf')
    return path.join(path.expanduser('~'), '.pgpass')


def _get_entries():
    """Return a list of the entries in the pgpass file as a list of _Entry
    instances.

    :return: list

    """
    entries = list()
    matches = PATTERN.findall(_read_file())
    for match in matches:
        if match and not match[0].startswith("#"):
            entries.append(_Entry(*match))
    return entries


def _read_file():
    """Read in the file, returning the contents as a single string

    :rtype: str

    """
    with open(_file_path(), 'r') as pgpass_file:
        return pgpass_file.read()
