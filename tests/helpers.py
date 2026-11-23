import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

BIN = os.path.join(ROOT, "bin", "harness")


def fake(*parts):
    return "".join(parts)


FAKE_GITHUB = fake("gh", "p_", "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8")
FAKE_ANTHROPIC = fake("sk-", "ant-", "api03-", "Zx9" * 30)
FAKE_AWS_ID = fake("AK", "IA", "QWERTYUIOPASDFGH")
FAKE_STRIPE = fake("sk", "_live_", "4eC39HqLyjWDarjtT1zdp7dc")
FAKE_PRIVATE_KEY = fake("-----BEGIN ", "RSA PRIVATE", " KEY-----\nMIIEpAIBAAKCAQEA\n-----END RSA ", "PRIVATE KEY-----")


class ProjectTestCase(unittest.TestCase):
    git = True

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="harness-test-")
        self.project = os.path.realpath(os.path.join(self.tmp, "project"))
        os.makedirs(self.project)
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.home)
        self._env = dict(os.environ)
        os.environ["CLAUDE_PROJECT_DIR"] = self.project
        os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(self.home, ".claude")
        os.environ.pop("HARNESS_POLICY", None)
        os.environ.pop("HARNESS_AUDIT_DISABLED", None)
        os.environ["NO_COLOR"] = "1"
        if self.git:
            self.run_git("init", "-q", "-b", "main")
            self.run_git("config", "user.email", "test@example.com")
            self.run_git("config", "user.name", "Test")
            self.run_git("config", "commit.gpgsign", "false")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_git(self, *args):
        return subprocess.run(["git", *args], cwd=self.project, check=True, capture_output=True, text=True)

    def path(self, *parts):
        return os.path.join(self.project, *parts)

    def write(self, rel, content):
        p = self.path(rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(content)
        return p

    def read(self, *parts):
        with open(self.path(*parts), encoding="utf-8") as fh:
            return fh.read()

    def read_json(self, *parts):
        return json.loads(self.read(*parts))

    def write_policy(self, data, name="policy.json"):
        return self.write(os.path.join(".claude", "harness", name), json.dumps(data))

    def payload(self, event, **fields):
        base = {
            "session_id": "test-session-0001",
            "transcript_path": os.path.join(self.tmp, "t.jsonl"),
            "cwd": self.project,
            "permission_mode": "default",
            "hook_event_name": event,
        }
        base.update(fields)
        return base

    def hook(self, event, **fields):
        from harnesspro.hooks import dispatch

        result = dispatch(event, json.dumps(self.payload(event, **fields)))
        out = json.loads(result.stdout) if result.stdout.strip().startswith("{") else result.stdout
        return result, out

    def cli(self, *args, stdin=""):
        env = dict(os.environ)
        return subprocess.run([sys.executable, BIN, *args], input=stdin, capture_output=True, text=True, cwd=self.project, env=env)
