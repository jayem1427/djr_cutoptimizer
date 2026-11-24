from __future__ import annotations
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))


def _forget_modules():
    """Drop this add-in's other modules from Python's cache.

    Fusion keeps one Python process for the whole session, so after an update a
    Stop/Run would otherwise keep running the old submodules with the new panel.
    Matches by file location, so it works however Fusion names the package.
    """
    me = os.path.abspath(__file__)
    for name, mod in list(sys.modules.items()):
        f = getattr(mod, '__file__', None)
        if not f:
            continue
        f = os.path.abspath(f)
        if f != me and f.startswith(_HERE + os.sep):
            sys.modules.pop(name, None)


_forget_modules()

from .lib.fusionAddInUtils import Events  # noqa: E402
from .lib.fusionAddInUtils import Utils  # noqa: E402
from .commands.commands import Commands  # noqa: E402


def run(context):
    try:
        Utils.log("djr_cutoptimizer run")
        Commands.start()
    except:
        Utils.handleError('run')


def stop(context):
    try:
        Events.clear()
        Commands.stop()
    except:
        Utils.handleError('stop')
    _forget_modules()
