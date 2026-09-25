"""Second-instance hint, keyed by the work directory.

Multiple instances are allowed on purpose: per-project settings live beside
each dataset (``.jllabel/project.json``), so two windows on two datasets no
longer clobber each other. What *is* still shared is the global
``.xanylabelingrc`` and the QSettings recent lists, where the instance that
closes last wins - so a second instance says so in the log instead of failing
silently. This is a hint, not a lock: nothing is blocked.
"""

import hashlib

from PyQt6.QtNetwork import QLocalServer, QLocalSocket

# QLocalServer objects must outlive this call, or the name vanishes and the
# next instance reads "first". Held like app.py's _KEEP_OPEN_LOGS.
_KEEP_SERVERS = []


def _server_name(work_dir):
    digest = hashlib.sha1(str(work_dir).encode("utf-8")).hexdigest()[:10]
    return f"jllabel-instance-{digest}"


def hint_second_instance(work_dir, logger):
    """Report when another instance shares this work directory.

    Always returns quietly; a failure to probe (no local server support,
    sandboxed IPC) must never block startup.
    """
    name = _server_name(work_dir)
    try:
        probe = QLocalSocket()
        probe.connectToServer(name)
        already_running = probe.waitForConnected(150)
        probe.disconnectFromServer()

        if already_running:
            logger.warning(
                "Another instance is already running on this work "
                "directory. Project settings (.jllabel) are isolated per "
                "dataset, but the global config and recent-file lists are "
                "shared: the instance that closes last wins."
            )

        # Leave a server behind so later instances can detect this one.
        # Remove a stale server first: after a crash the name may linger.
        QLocalServer.removeServer(name)
        server = QLocalServer()
        server.listen(name)
        _KEEP_SERVERS.append(server)
        return server
    except Exception as e:  # noqa: BLE001 - hint only, never fatal
        logger.warning(f"Instance probe failed (ignored): {e}")
        return None
