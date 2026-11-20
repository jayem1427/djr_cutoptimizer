from __future__ import annotations
from .lib.fusionAddInUtils import Events
from .lib.fusionAddInUtils import Utils
from .commands.commands import Commands


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
