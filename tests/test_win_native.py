"""get.py 윈도우 그대로(WSL 없이) — 맥에서는 IS_WIN 을 흉내 내 확인하고, 윈도우(깃허브 러너)에서는 진짜로 돌린다.

  python3 tests/test_win_native.py      (윈도우: py -3 tests\\test_win_native.py)
"""
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
WIN = os.name == "nt"


def load(home):
    os.environ["BUILDERLOG_HOME"] = str(home)
    os.environ["BUILDERLOG_SERVER"] = "https://example.test"
    spec = importlib.util.spec_from_file_location(f"getpy_{time.monotonic_ns()}", REPO / "client/get.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.LANG = "ko"
    return m


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.env = mock.patch.dict(os.environ, {"BUILDERLOG_NO_BROWSER": "", "BUILDERLOG_NO_SYSTEM": "1",
                                                "BUILDERLOG_CRONTAB_FILE": str(self.root / "crontab"),
                                                "BUILDERLOG_TASK_FILE": str(self.root / "task.json"),
                                                "BUILDERLOG_LAUNCHD_DIR": str(self.root / "agents"),
                                                "CLAUDE_CONFIG_DIR": str(self.root / "claude")})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.g = load(self.root / "home")

    def win(self):
        """맥·리눅스에서 윈도우처럼(진짜 윈도우면 그대로)."""
        if WIN:
            return contextlib.nullcontext()
        st = contextlib.ExitStack()
        st.enter_context(mock.patch.object(self.g, "IS_WIN", True))
        st.enter_context(mock.patch.object(self.g.platform, "system", lambda: "Windows"))
        st.enter_context(mock.patch.object(self.g, "PY", "py -3"))
        st.enter_context(mock.patch.object(self.g, "GET", f"py -3 {self.g.HELPER.as_posix()}"))  # 진짜 윈도우에서는 불러올 때 정해짐
        return st

    def run_main(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = self.g.main(list(argv))
        return rc, buf.getvalue()


class Paths(Base):
    def test_show_is_absolute_on_windows(self):
        with self.win():
            s = self.g.show(self.g.HELPER)
        self.assertFalse(s.startswith("~"), s)
        self.assertTrue(s.strip('"').endswith("/get.py"), s)
        self.assertNotIn("\\", s)

    def test_show_quotes_spaces(self):
        d = self.root / "John Doe" / "get.py"
        with self.win():
            self.assertTrue(self.g.show(d).startswith('"'))

    @unittest.skipUnless(WIN, "윈도우에서만")
    def test_get_command_is_runnable_on_windows(self):
        self.assertTrue(self.g.GET.startswith(("py -3 ", "python ")), self.g.GET)
        self.assertNotIn("python3", self.g.GET)

    def test_venv_python(self):
        with self.win():
            self.assertEqual(self.g.venv_py(Path("x")).as_posix(), "x/.venv/Scripts/python.exe")
        if not WIN:
            self.assertEqual(self.g.venv_py(Path("x")).as_posix(), "x/.venv/bin/python")

    def test_install_line_windows(self):
        with self.win():
            self.assertEqual(self.g.install_line(), "irm https://example.test/install.ps1 | iex")

    def test_machine_os(self):
        with self.win():
            self.assertTrue(self.g.machine_info()["os"].startswith("Windows"))


class Lock(Base):
    def test_second_lock_is_refused(self):
        dest = self.root / "home" / "blog"
        dest.mkdir(parents=True)
        with self.g.pack_lock(dest):
            with self.assertRaises(self.g.Stop) as e:
                with self.g.pack_lock(dest):
                    pass
            self.assertEqual(e.exception.code, 5)
        with self.g.pack_lock(dest):  # 풀린 뒤에는 다시 된다
            pass


class Browser(Base):
    def test_open_url_uses_startfile(self):
        seen = []
        with self.win(), mock.patch.object(self.g.os, "startfile", seen.append, create=True):
            used = self.g.open_url("https://example.test/a?b=1&c=2")
        self.assertEqual(used, "start")
        self.assertEqual(seen, ["https://example.test/a?b=1&c=2"])


class Schedule(Base):
    def test_on_off_uses_task_scheduler_not_cron(self):
        with self.win():
            rc, out = self.run_main("schedule", "on", "--client", "none")
            self.assertEqual(rc, 0, out)
            cmd = json.loads((self.root / "task.json").read_text(encoding="utf-8"))
            self.assertEqual(cmd[:4], ["schtasks", "/Create", "/F", "/SC"])
            tr = cmd[cmd.index("/TR") + 1]
            self.assertIn("update --auto", tr)
            self.assertIn(str(self.g.HELPER), tr)
            self.assertIn("schtasks", out)
            self.assertNotIn("python3", out)
            rc, out = self.run_main("schedule", "off")
            self.assertEqual(rc, 0, out)
            cmd = json.loads((self.root / "task.json").read_text(encoding="utf-8"))
            self.assertEqual(cmd, ["schtasks", "/Delete", "/F", "/TN", "Builderlog Update"])
        self.assertFalse((self.root / "crontab").exists())
        self.assertEqual(json.loads((self.g.STATE / "schedule.json").read_text(encoding="utf-8")), {"on": False})

    def test_task_line_fits_schtasks_limit(self):
        tr = self.g.task_cmd(10, 5)
        self.assertIn("10:05", tr)
        self.assertLessEqual(len(tr[-1]), 261)

    @unittest.skipUnless(WIN, "윈도우에서만: 진짜 작업 스케줄러")
    def test_real_task_scheduler(self):
        with mock.patch.dict(os.environ, {"BUILDERLOG_NO_SYSTEM": "", "BUILDERLOG_TASK_FILE": ""}):
            rc, out = self.run_main("schedule", "on", "--client", "none")
            self.assertEqual(rc, 0, out)
            q = subprocess.run(["schtasks", "/Query", "/TN", "Builderlog Update"], capture_output=True)
            self.assertEqual(q.returncode, 0, out)
            rc, out = self.run_main("schedule", "off")
            q = subprocess.run(["schtasks", "/Query", "/TN", "Builderlog Update"], capture_output=True)
            self.assertNotEqual(q.returncode, 0, out)


class Output(Base):
    def test_pythonw_without_stdout_writes_update_log(self):
        old = sys.stdout, sys.stderr
        try:
            sys.stdout = sys.stderr = None
            rc = self.g.main(["status"])
        finally:
            f = sys.stdout
            sys.stdout, sys.stderr = old
            if f:
                f.close()
        self.assertIn(rc, (0, 3, 4))
        self.assertTrue((self.g.STATE / "update.log").read_text(encoding="utf-8").strip())

    def test_piped_output_is_utf8(self):
        env = {**os.environ, "BUILDERLOG_HOME": str(self.root / "pipe"), "BUILDERLOG_LANG": "ko"}
        env.pop("PYTHONIOENCODING", None)
        env.pop("PYTHONUTF8", None)
        r = subprocess.run([sys.executable, str(REPO / "client/get.py"), "status"], capture_output=True, env=env, timeout=60)
        text = (r.stdout + r.stderr).decode("utf-8")  # 깨지면 여기서 UnicodeDecodeError
        self.assertRegex(text, "[가-힣]")


class Commands(Base):
    @unittest.skipUnless(WIN, "윈도우에서만: npm 의 claude.cmd")
    def test_cmd_shim_is_found(self):
        b = self.root / "bin"
        b.mkdir()
        log = self.root / "args.txt"
        (b / "claude.cmd").write_text(f'@echo off\r\necho %* > "{log}"\r\nexit /b 0\r\n', encoding="ascii")
        with mock.patch.dict(os.environ, {"PATH": str(b) + os.pathsep + os.environ.get("PATH", "")}):
            self.assertTrue(self.g.run_quiet(["claude", "mcp", "get", "builderlog"]))
            ok, why = self.g.run_reason(["claude", "mcp", "add", "--transport", "http", "-s", "user", "builderlog", "https://example.test/mcp"])
        self.assertTrue(ok, why)
        self.assertIn("https://example.test/mcp", log.read_text())

    def test_resolve_exe_keeps_paths(self):
        with self.win():
            self.assertEqual(self.g.resolve_exe(["C:/x/claude.cmd", "a"]), ["C:/x/claude.cmd", "a"])
            with mock.patch.object(self.g.shutil, "which", lambda n: "C:/npm/claude.CMD" if n == "claude" else None):
                self.assertEqual(self.g.resolve_exe(["claude", "mcp"]), ["C:/npm/claude.CMD", "mcp"])

    def test_messages_have_no_python3_on_windows(self):
        """안내 속 명령이 GET 하나로 모였는지(윈도우면 py -3 · 절대 경로)."""
        src = (REPO / "client/get.py").read_text(encoding="utf-8")
        body = src.split("\nimport argparse\n", 1)[1]
        self.assertNotIn("python3 ~/builderlog/get.py", body)
        self.assertNotIn("python3 {show(HELPER)}", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
