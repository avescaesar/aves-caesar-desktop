from __future__ import annotations

import sys

from bird_desktop import __version__


class AppVersion:
    DEVELOPMENT_VERSION = "0.0.0"


    @staticmethod
    def current() -> str:
        if getattr(sys, "frozen", False):
            return __version__

        return AppVersion.DEVELOPMENT_VERSION
