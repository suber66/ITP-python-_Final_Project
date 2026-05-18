"""
Binary persistence manager with encrypted file names.

Overview
--------
This module provides the :class:`SaveManager` singleton, responsible for
persisting arbitrary Python values to disk in a secure, opaque manner.

Each key is stored as a separate file inside ``<game_dir>/save_data/``.
The file name is derived from an HMAC-SHA256 digest of the key, making
the on-disk layout unreadable without the master key.  The file content
is encrypted with `Fernet <https://cryptography.io/en/latest/fernet/>`_
(AES-128-CBC + HMAC-SHA256), and the value itself is serialised with
:mod:`pickle`.

There is intentionally **no in-memory cache** — every :meth:`SaveManager.get`
and :meth:`SaveManager.set` call goes directly to disk, which keeps the
persistence layer simple and free of stale-state bugs.

Encryption key resolution
--------------------------
The master key is resolved in the following order:

1. The ``SAVE_MASTER_KEY`` environment variable (URL-safe base-64, 44 chars).
2. The ``.key`` file inside the save directory (auto-created on first run).
3. A freshly generated :func:`Fernet.generate_key` that is written to the
   ``.key`` file for all subsequent sessions.

Usage
-----
    >>> from managers.saveManager import SaveManager

    >>> # Instance API
    >>> SaveManager.instance().set('best_time', 42.5)
    >>> best = SaveManager.instance().get('best_time', default=None)

    >>> # Static shorthand
    >>> SaveManager.Set('scores', [100, 200, 300])
    >>> scores = SaveManager.Get('scores')
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import pickle
import tempfile
from typing import Any, Optional

from cryptography.fernet import Fernet

from tools import Console


# --------------------------------------------------------------------------- #
#  Paths                                                                       #
# --------------------------------------------------------------------------- #

_GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SAVE_DIR = os.path.join(_GAME_DIR, 'save_data')
_KEY_FILE = os.path.join(_SAVE_DIR, '.key')


# --------------------------------------------------------------------------- #
#  Internal helpers                                                            #
# --------------------------------------------------------------------------- #

def _load_or_create_master_key() -> bytes:
    """Load or generate the Fernet master key.

    Resolves the encryption key using the following priority order:

    1. The ``SAVE_MASTER_KEY`` environment variable.
    2. The ``.key`` file persisted in the save directory.
    3. A newly generated key written to the ``.key`` file.

    Returns
    -------
    bytes
        A URL-safe base-64–encoded Fernet key (44 bytes).
    """
    env_key = os.environ.get('SAVE_MASTER_KEY')
    if env_key:
        return env_key.encode()

    os.makedirs(_SAVE_DIR, exist_ok=True)
    if os.path.exists(_KEY_FILE):
        with open(_KEY_FILE, 'rb') as fh:
            return fh.read().strip()

    key = Fernet.generate_key()
    _atomic_write(_KEY_FILE, key)
    Console.log(f'[SaveManager] New master key created: {_KEY_FILE}')
    return key


def _atomic_write(path: str, data: bytes) -> None:
    """Write binary data to *path* atomically.

    Uses a sibling temporary file and :func:`os.replace`, which is an atomic
    operation on both POSIX and Windows, preventing partial writes from
    corrupting save files.

    Parameters
    ----------
    path : str
        Destination file path.
    data : bytes
        Raw bytes to write.

    Raises
    ------
    OSError
        If the temporary file cannot be created or replaced.
    """
    dir_ = os.path.dirname(path)
    os.makedirs(dir_, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_)
    try:
        with os.fdopen(fd, 'wb') as fh:
            fh.write(data)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _key_to_filename(key: str, raw_master: bytes) -> str:
    """Derive a deterministic, opaque file name for a save key.

    Computes ``HMAC-SHA256(master_bytes, key_utf8)`` and returns the first
    24 hex characters of the digest.  The result is collision-resistant for
    all practical game save counts and reveals nothing about the original key.

    Parameters
    ----------
    key : str
        The human-readable save key (e.g. ``'best_time'``).
    raw_master : bytes
        The raw master key bytes (URL-safe base-64 encoded).

    Returns
    -------
    str
        A 24-character lowercase hex string used as the on-disk file name.
    """
    try:
        master_bytes = base64.urlsafe_b64decode(raw_master + b'==')
    except Exception:
        master_bytes = raw_master

    digest = hmac.new(master_bytes, key.encode('utf-8'), hashlib.sha256).hexdigest()
    return digest[:24]


# --------------------------------------------------------------------------- #
#  SaveManager                                                                 #
# --------------------------------------------------------------------------- #

class SaveManager:
    """Singleton manager for encrypted, file-based game save persistence.

    Each save entry is stored as an individual encrypted file inside the
    ``save_data/`` directory. File names are derived from an HMAC digest
    of the key, so the directory listing is opaque to external inspection.

    All read and write operations bypass any in-memory cache and go directly
    to disk, ensuring that save data is never lost on an unexpected crash.

    .. note::
        Do **not** instantiate this class directly.  Always obtain the shared
        instance through :meth:`instance` or use the static shorthand methods
        :meth:`Get`, :meth:`Set`, :meth:`Has`, and :meth:`Delete`.
    """

    _instance: Optional['SaveManager'] = None

    # ------------------------------------------------------------------ #
    #  Singleton                                                           #
    # ------------------------------------------------------------------ #

    @classmethod
    def instance(cls) -> 'SaveManager':
        """Retrieve the global singleton instance of the SaveManager.

        Creates and initialises the instance on the first call.

        Returns
        -------
        SaveManager
            The active save manager instance.
        """
        if cls._instance is None:
            cls._instance = cls.__new__(cls)
            cls._instance._init()
        return cls._instance

    def __init__(self) -> None:
        raise RuntimeError('Use SaveManager.instance() to obtain the singleton.')

    def _init(self) -> None:
        """Initialise internal state.

        Loads (or generates) the master encryption key, constructs the
        :class:`~cryptography.fernet.Fernet` cipher, and ensures the save
        directory exists on disk.
        """
        self._save_dir: str = _SAVE_DIR
        self._raw_key: bytes = _load_or_create_master_key()
        self._fernet: Fernet = Fernet(self._raw_key)
        os.makedirs(self._save_dir, exist_ok=True)

    # ------------------------------------------------------------------ #
    #  Internal I/O                                                        #
    # ------------------------------------------------------------------ #

    def _filepath(self, key: str) -> str:
        """Resolve the absolute path to the file that stores *key*.

        Parameters
        ----------
        key : str
            The logical save key.

        Returns
        -------
        str
            Absolute path to the corresponding encrypted file.
        """
        return os.path.join(self._save_dir, _key_to_filename(key, self._raw_key))

    def _write(self, key: str, value: Any) -> None:
        """Serialise, encrypt, and atomically write *value* to disk.

        Parameters
        ----------
        key : str
            The logical save key that determines the target file.
        value : Any
            Any picklable Python object to persist.

        Raises
        ------
        pickle.PicklingError
            If *value* cannot be serialised by :mod:`pickle`.
        cryptography.fernet.InvalidToken
            If encryption fails unexpectedly.
        OSError
            If the file cannot be written to disk.
        """
        raw   = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
        token = self._fernet.encrypt(raw)
        _atomic_write(self._filepath(key), token)

    def _read(self, key: str) -> Any:
        """Decrypt and deserialise the value stored under *key*.

        Parameters
        ----------
        key : str
            The logical save key to read.

        Returns
        -------
        Any
            The deserialised Python object previously written by :meth:`_write`.

        Raises
        ------
        KeyError
            If no file exists for *key*.
        cryptography.fernet.InvalidToken
            If the file content cannot be decrypted (e.g. key mismatch or
            file corruption).
        """
        path = self._filepath(key)
        if not os.path.exists(path):
            raise KeyError(key)
        with open(path, 'rb') as fh:
            token = fh.read()
        return pickle.loads(self._fernet.decrypt(token))  # noqa: S301

    # ------------------------------------------------------------------ #
    #  Core API (instance methods)                                         #
    # ------------------------------------------------------------------ #

    def get(self, key: str, default: Any = None) -> Any:
        """Read a value from disk.

        Parameters
        ----------
        key : str
            The logical save key to look up.
        default : Any, optional
            Value returned when the key does not exist on disk.
            Defaults to ``None``.

        Returns
        -------
        Any
            The stored value, or *default* if the key was not found or if
            a decryption/deserialisation error occurred.
        """
        try:
            return self._read(key)
        except KeyError:
            return default
        except Exception as exc:
            Console.error(f'[SaveManager] get({key!r}) failed: {exc}')
            return default

    def set(self, key: str, value: Any) -> bool:  # noqa: A003
        """Write a value to disk immediately.

        Parameters
        ----------
        key : str
            The logical save key under which *value* will be stored.
        value : Any
            Any picklable Python object to persist.

        Returns
        -------
        bool
            ``True`` on success, ``False`` if any error occurred during
            serialisation or file I/O.
        """
        try:
            self._write(key, value)
            return True
        except Exception as exc:
            Console.error(f'[SaveManager] set({key!r}) failed: {exc}')
            return False

    def delete(self, key: str) -> None:
        """Remove the file associated with *key* from disk.

        Silently does nothing if the key does not exist.

        Parameters
        ----------
        key : str
            The logical save key whose backing file should be removed.
        """
        path = self._filepath(key)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError as exc:
                Console.error(f'[SaveManager] delete({key!r}) failed: {exc}')

    def has(self, key: str) -> bool:
        """Check whether a key is currently persisted on disk.

        Parameters
        ----------
        key : str
            The logical save key to test.

        Returns
        -------
        bool
            ``True`` if the corresponding file exists on disk, ``False``
            otherwise.
        """
        return os.path.exists(self._filepath(key))

    def reset(self) -> None:
        """Delete all save files from the save directory.

        The master ``.key`` file is preserved so that a fresh save session
        can begin with the same encryption key.  All other entries in the
        save directory are removed.
        """
        if not os.path.isdir(self._save_dir):
            return
        for fname in os.listdir(self._save_dir):
            if fname == '.key':
                continue
            try:
                os.remove(os.path.join(self._save_dir, fname))
            except OSError:
                pass
        Console.log('[SaveManager] All save data has been cleared.')

    # ------------------------------------------------------------------ #
    #  Static shorthand API                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def Get(key: str, default: Any = None) -> Any:
        """Static shorthand for :meth:`SaveManager.instance().get`.

        Parameters
        ----------
        key : str
            The logical save key to look up.
        default : Any, optional
            Fallback value when the key is absent. Defaults to ``None``.

        Returns
        -------
        Any
            The stored value, or *default* if not found.
        """
        return SaveManager.instance().get(key, default)

    @staticmethod
    def Set(key: str, value: Any) -> bool:
        """Static shorthand for :meth:`SaveManager.instance().set`.

        Parameters
        ----------
        key : str
            The logical save key under which *value* will be stored.
        value : Any
            Any picklable Python object to persist.

        Returns
        -------
        bool
            ``True`` on success, ``False`` on failure.
        """
        return SaveManager.instance().set(key, value)

    @staticmethod
    def Has(key: str) -> bool:
        """Static shorthand for :meth:`SaveManager.instance().has`.

        Parameters
        ----------
        key : str
            The logical save key to test.

        Returns
        -------
        bool
            ``True`` if the key exists on disk, ``False`` otherwise.
        """
        return SaveManager.instance().has(key)

    @staticmethod
    def Delete(key: str) -> None:
        """Static shorthand for :meth:`SaveManager.instance().delete`.

        Parameters
        ----------
        key : str
            The logical save key whose backing file should be removed.
        """
        SaveManager.instance().delete(key)