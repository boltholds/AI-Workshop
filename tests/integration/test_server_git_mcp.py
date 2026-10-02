from __future__ import annotations

import asyncio
import inspect

from ai_workshop.gateway.git_tools import register_git_tools
from ai_workshop.gateway.project_tools import register_project_tools
from ai_workshop.gateway.server import build_server
from ai_workshop.git.models import GitCommitResult, GitLogEntry, GitStatus
from ai_workshop.projects.models import GitManagedProject


class FakeServer:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def decorate(fn):
            self.tools[fn.__name__] = fn
            return fn
        return decorate


class FakeProjects:
    def list(self):
        return [
            GitManagedProject(
                project_id="demo",
                path="/srv/ai-workshop/projects/demo",
                remote_url="git@example.test:demo.git",
            )
        ]

    def get(self, project_id):
        return self.list()[0]

    def remove_registration(self, project_id):
        self.removed = project_id


class FakeGit:
    def clone(self, project_id, remote_url, *, credential_id=None):
        self.last = ("clone", project_id, remote_url, credential_id)
        return FakeProjects().get(project_id)

    def status(self, project_id):
        return GitStatus(project_id=project_id, branch="main", porcelain="")

    def diff(self, project_id, *, staged=False):
        return "diff" if not staged else "staged"

    def fetch(self, project_id, *, remote="origin", credential_id=None):
        self.last = ("fetch", project_id, remote, credential_id)

    def pull(self, project_id, *, remote="origin", branch, credential_id=None):
        self.last = ("pull", project_id, remote, branch, credential_id)

    def add(self, project_id, paths):
        self.last = ("add", project_id, paths)

    def commit(self, project_id, message):
        return GitCommitResult(project_id=project_id, commit_id="a" * 40)

    def log(self, project_id, *, limit=20):
        return [GitLogEntry(commit_id="a" * 40, subject="commit")]

    def branch_list(self, project_id):
        return ["main"]

    def branch_create(self, project_id, branch):
        self.last = ("branch_create", project_id, branch)

    def switch(self, project_id, branch):
        self.last = ("switch", project_id, branch)

    def checkout(self, project_id, ref):
        self.last = ("checkout", project_id, ref)

    def remote_list(self, project_id):
        return {"origin": "git@example.test:demo.git"}

    def remote_set(self, project_id, name, url):
        self.last = ("remote_set", project_id, name, url)

    def stash(self, project_id, *, message="AI Workshop stash"):
        self.last = ("stash", project_id, message)

    def tag(self, project_id, tag):
        self.last = ("tag", project_id, tag)

    def push(self, project_id, *, remote="origin", branch, credential_id=None):
        self.last = ("push", project_id, remote, branch, credential_id)

    def merge(self, project_id, ref):
        self.last = ("merge", project_id, ref)

    def rebase(self, project_id, ref):
        self.last = ("rebase", project_id, ref)

    def rebase_continue(self, project_id):
        self.last = ("rebase_continue", project_id)

    def rebase_abort(self, project_id):
        self.last = ("rebase_abort", project_id)

    def cherry_pick(self, project_id, ref):
        self.last = ("cherry_pick", project_id, ref)


class FakeDestructive:
    pass


def test_project_tools_expose_ids_not_checkout_paths():
    server = FakeServer()
    register_project_tools(server, FakeProjects())

    assert {"projects_list", "projects_get", "projects_remove_registration"} <= set(server.tools)
    item = server.tools["projects_get"]("demo")
    assert item["project_id"] == "demo"
    assert "path" not in item


def test_git_tools_register_extended_server_git_surface():
    server = FakeServer()
    register_git_tools(server, FakeGit())

    expected = {
        "git_clone", "git_status", "git_diff", "git_fetch", "git_pull",
        "git_add", "git_commit", "git_log", "git_branch_list",
        "git_branch_create", "git_switch", "git_checkout", "git_remote_list",
        "git_remote_set", "git_stash", "git_tag", "git_push", "git_merge",
        "git_rebase", "git_rebase_continue", "git_rebase_abort", "git_cherry_pick",
    }
    assert expected <= set(server.tools)


def test_git_tools_do_not_expose_raw_git_or_secret_parameters():
    server = FakeServer()
    register_git_tools(server, FakeGit())

    forbidden = {
        "argv", "args", "cwd", "host_path", "private_key", "token",
        "password", "docker_args", "git_args",
    }
    for name, tool in server.tools.items():
        if name.startswith("git_"):
            assert forbidden.isdisjoint(inspect.signature(tool).parameters)


def test_git_add_accepts_only_project_id_and_relative_paths():
    server = FakeServer()
    git = FakeGit()
    register_git_tools(server, git)

    server.tools["git_add"]("demo", ["src/app.py"])

    assert git.last == ("add", "demo", ["src/app.py"])
    assert set(inspect.signature(server.tools["git_add"]).parameters) == {
        "project_id", "relative_paths"
    }


def test_build_server_uses_extended_git_tools_when_git_service_is_configured():
    server = build_server(
        "http://127.0.0.1:8766",
        token="workspace-token",
        project_service=FakeProjects(),
        git_service=FakeGit(),
    )
    names = {tool.name for tool in asyncio.run(server.list_tools())}

    assert "git_status" in names
    assert "git_clone" in names
    assert "projects_list" in names
    assert "filesystem_read" in names
    assert len([name for name in names if name == "git_status"]) == 1


def test_build_server_keeps_desktop_git_proxy_by_default():
    server = build_server("http://127.0.0.1:8766", token="workspace-token")
    names = {tool.name for tool in asyncio.run(server.list_tools())}

    assert "git_status" in names
    assert "git_diff" in names
    assert "git_clone" not in names
