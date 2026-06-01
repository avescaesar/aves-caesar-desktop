from __future__ import annotations

from pathlib import Path

import webview
from PIL import Image

from .api import BirdDesktopApi
from .runtime.paths import AppPaths


def main() -> None:
    AppRunner().run()


class AppRunner:
    def run(self) -> None:
        index = AppPaths.frontend_index()
        if not index.exists():
            raise RuntimeError(f"Frontend build not found: {index}. Run npm run build first.")

        api = BirdDesktopApi()
        webview.create_window("Aves Caesar", index.as_uri(), js_api=api, width=1120, height=760, min_size=(920, 640))
        icon = self._window_icon()
        webview.start(debug=False, icon=str(icon) if icon.exists() else None)


    def _window_icon(self) -> Path:
        source = AppPaths.app_icon()
        target = AppPaths.app_window_icon()
        if not source.exists():
            return source

        if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
            return target

        target.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as image:
            image.save(target, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

        return target
