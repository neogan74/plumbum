from __future__ import with_statement
import os
import socket
import unittest
import six
from plumbum import RemotePath, SshMachine, ProcessExecutionError


#TEST_HOST = "192.168.1.143"
TEST_HOST = "127.0.0.1"
if TEST_HOST not in ("::1", "127.0.0.1", "localhost"):
    import plumbum
    plumbum.local.env.path.append("c:\\Program Files\\Git\\bin")

if not hasattr(unittest, "skipIf"):
    import logging
    import functools
    def skipIf(cond, msg = None):
        def deco(func):
            if cond:
                return func
            else:
                @functools.wraps(func)
                def wrapper(*args, **kwargs):
                    logging.warn("skipping test")
                return wrapper
        return deco
    unittest.skipIf = skipIf

class RemotePathTest(unittest.TestCase):
    def _connect(self):
        return SshMachine(TEST_HOST)

    def test_basename(self):
        name = RemotePath(self._connect(), "/some/long/path/to/file.txt").basename
        self.assertTrue(isinstance(name, six.string_types))
        self.assertEqual("file.txt", str(name))

    def test_dirname(self):
        name = RemotePath(self._connect(), "/some/long/path/to/file.txt").dirname
        self.assertTrue(isinstance(name, RemotePath))
        self.assertEqual("/some/long/path/to", str(name))

    @unittest.skipIf(not hasattr(os, "chown"), "os.chown not supported")
    def test_chown(self):
        with self._connect() as rem:
            with rem.tempdir() as dir:
                p = dir / "foo.txt"
                p.write("hello")
                # because we're connected to localhost, we expect UID and GID to be the same
                self.assertEqual(p.uid, os.getuid())
                self.assertEqual(p.gid, os.getgid())
                p.chown(p.uid.name)
                self.assertEqual(p.uid, os.getuid())


class BaseRemoteMachineTest(object):
    TUNNEL_PROG = r"""import sys, socket
s = socket.socket()
if sys.version_info[0] < 3:
    b = lambda x: x
else:
    b = lambda x: bytes(x, "utf8")
s.bind(("", 0))
s.listen(1)
sys.stdout.write(b("%s\n" % (s.getsockname()[1],)))
sys.stdout.flush()
s2, _ = s.accept()
data = s2.recv(100)
s2.send(b("hello ") + data)
s2.close()
s.close()
"""

    def test_basic(self):
        with self._connect() as rem:
            r_ssh = rem["ssh"]
            r_ls = rem["ls"]
            r_grep = rem["grep"]

            self.assertTrue(".bashrc" in r_ls("-a").splitlines())

            with rem.cwd(os.path.dirname(__file__)):
                cmd = r_ssh["localhost", "cd", rem.cwd, "&&", r_ls | r_grep["\\.py"]]
                self.assertTrue("'|'" in str(cmd))
                self.assertTrue("test_remote.py" in cmd())
                self.assertTrue("test_remote.py" in [f.basename for f in rem.cwd // "*.py"])

    def test_download_upload(self):
        with self._connect() as rem:
            rem.upload("test_remote.py", "/tmp")
            r_ls = rem["ls"]
            r_rm = rem["rm"]
            self.assertTrue("test_remote.py" in r_ls("/tmp").splitlines())
            rem.download("/tmp/test_remote.py", "/tmp/test_download.txt")
            r_rm("/tmp/test_remote.py")
            r_rm("/tmp/test_download.txt")

    def test_session(self):
        with self._connect() as rem:
            sh = rem.session()
            for _ in range(4):
                _, out, _ = sh.run("ls -a")
                self.assertTrue(".bashrc" in out)

    def test_env(self):
        with self._connect() as rem:
            self.assertRaises(ProcessExecutionError, rem.python, "-c",
                "import os;os.environ['FOOBAR72']")
            with rem.env(FOOBAR72 = "lala"):
                with rem.env(FOOBAR72 = "baba"):
                    out = rem.python("-c", "import os;print(os.environ['FOOBAR72'])")
                    self.assertEqual(out.strip(), "baba")
                out = rem.python("-c", "import os;print(os.environ['FOOBAR72'])")
                self.assertEqual(out.strip(), "lala")

    def test_read_write(self):
        with self._connect() as rem:
            with rem.tempdir() as dir:
                self.assertTrue(dir.isdir())
                data = "hello world"
                (dir / "foo.txt").write(data)
                self.assertEqual((dir / "foo.txt").read(), data)

            self.assertFalse(dir.exists())


class RemoteMachineTest(unittest.TestCase, BaseRemoteMachineTest):
    def _connect(self):
        return SshMachine(TEST_HOST)

    def test_tunnel(self):
        with self._connect() as rem:
            p = (rem.python["-u"] << self.TUNNEL_PROG).popen()
            try:
                port = int(p.stdout.readline().strip())
            except ValueError:
                print(p.communicate())
                raise

            with rem.tunnel(12222, port) as tun:
                s = socket.socket()
                s.connect(("localhost", 12222))
                s.send(six.b("world"))
                data = s.recv(100)
                s.close()
                self.assertEqual(data, six.b("hello world"))

            p.communicate()


if not six.PY3:
    import paramiko
    from plumbum.paramiko_machine import ParamikoMachine

    class TestParamikoMachine(unittest.TestCase, BaseRemoteMachineTest):
        def _connect(self):
            return ParamikoMachine(TEST_HOST, missing_host_policy = paramiko.AutoAddPolicy())
        
        def test_tunnel(self):
            with self._connect() as rem:
                p = rem.python["-c", self.TUNNEL_PROG].popen()
                try:
                    port = int(p.stdout.readline().strip())
                except ValueError:
                    print(p.communicate())
                    raise
                
                s = rem.connect_sock(port)
                s.send(six.b("world"))
                data = s.recv(100)
                s.close()
                self.assertEqual(data, six.b("hello world"))
    





if __name__ == "__main__":
    unittest.main()




