import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import PosixPath
from typing import Optional

from flask import Flask, Response, send_file, render_template_string, request

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RenderablePath:
    name: str
    url: str
    last_modified: datetime
    size: int
    type: str


class FileApi:
    def __init__(self, base_dir: Optional[PosixPath] = None):
        if base_dir:
            self._base_dir = base_dir.absolute()
        else:
            self._base_dir = (PosixPath(os.environ.get("TOOL_DATA_DIR", "HOME")) / "public_html").absolute()

        self._api_key = os.environ.get("CBNG_TRAINER_FILE_API_KEY", "")

        if not self._base_dir.is_dir():
            raise RuntimeError("invalid base directory")

    def _have_valid_token(self) -> bool:
        if authorization_header := request.headers.get("Authorization"):
            if " " in authorization_header:
                token = authorization_header.split(" ")[1]
                if self._api_key and self._api_key == token:
                    return True
        return False

    def _handle_store(self, target_path: PosixPath):
        if not self._have_valid_token():
            return Response(status=401)

        if not target_path.parent.is_dir():
            target_path.parent.mkdir(parents=True)

        if target_path.is_file():
            # File already exists, don't overwrite it
            # Return 200 to make the client not treat this as a failure, assume the content is the same
            return Response(status=200)

        with target_path.open("wb") as fh:
            fh.write(request.get_data())

        return Response(status=201)

    def _render_listing(self, target_path: PosixPath):
        paths = set()
        for path in target_path.iterdir():
            if path.is_dir():
                stat = path.lstat()
                paths.add(
                    RenderablePath(
                        name=path.name,
                        url=f"/{path.relative_to(self._base_dir).as_posix()}/",
                        last_modified=datetime.fromtimestamp(stat.st_mtime),
                        size=stat.st_size,
                        type="Directory",
                    )
                )
            if path.is_file():
                stat = path.lstat()
                paths.add(
                    RenderablePath(
                        name=path.name,
                        url=f"/{path.relative_to(self._base_dir).as_posix()}",
                        last_modified=datetime.fromtimestamp(stat.st_mtime),
                        size=stat.st_size,
                        type="File",
                    )
                )

        current_path_name = target_path.relative_to(self._base_dir).name
        return render_template_string(
            """
<!DOCTYPE html>
<html>
    <head>
        <meta charset="utf-8">
        <title>Index of {{ current_path }}</title>
    </head>
    <body>
        <h2>Index of {{ current_path }}</h2>
        <table width="100%" style="text-align: center">
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Last Modified</th>
                    <th>Size</th>
                    <th>Type</th>
                </tr>
            </thead>
            <tbody>
            {% if parent_url %}
            <tr>
                <td><a href="{{ parent_url }}">../</a></td>
                <td></td>
                <td></td>
                <td>Directory</td>
            </tr>
            {% endif %}
            {% for path in paths %}
            <tr>
                <td><a href="{{ path.url }}">{{ path.name }}</a></td>
                <td>{{ path.last_modified }}</td>
                <td>{{ path.size }}</td>
                <td>{{ path.type }}</td>
            </tr>
            {% endfor %}
            </tbody>
        </table>
    </body>
            """,
            parent_url=(
                None
                if current_path_name in {".", ""}
                else f"/{target_path.parent.relative_to(self._base_dir).as_posix()}/"
            ),
            current_path=(
                "/" if current_path_name in {".", ""} else f"/{target_path.relative_to(self._base_dir).as_posix()}/"
            ),
            paths=sorted(paths, key=lambda x: (x.type, x.name)),
        )

    def _handle_browser(self, target_path: PosixPath):
        if target_path.is_dir():
            return self._render_listing(target_path)

        if target_path.is_file():
            return send_file(
                target_path.as_posix(),
                "text/plain" if target_path.as_posix().endswith("*.log") else None,
            )

        return Response(status=404)

    def _handle(self, path=None):
        target_path = self._base_dir / path if path else self._base_dir
        if not target_path.absolute().as_posix().startswith(self._base_dir.as_posix()):
            return Response(status=403)

        if request.method == "POST":
            return self._handle_store(target_path)
        return self._handle_browser(target_path)

    def create_app(self) -> Flask:
        app = Flask(__name__)
        app.add_url_rule("/", "/", self._handle)
        app.add_url_rule("/<path:path>", "/", self._handle, methods=["GET", "POST"])
        return app

    def run(self) -> None:
        return self.create_app().run()


# Gunicorn entrypoint
def create_app():
    return FileApi().create_app()
