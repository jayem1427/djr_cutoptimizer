from __future__ import annotations
from .optimizer.palette_command import OptimizerCommand


class Commands():

    # Fusion calls start() and stop() on each of these.
    _commands = [
        OptimizerCommand,
    ]

    @classmethod
    def start(cls):
        for command in Commands._commands:
            command.start()

    @classmethod
    def stop(cls):
        for command in Commands._commands:
            command.stop()
