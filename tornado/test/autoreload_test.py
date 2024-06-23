import os
import shutil
import subprocess
from subprocess import Popen
import sys
from tempfile import mkdtemp
import textwrap
import time
import unittest
import tornado.autoreload
import types
import threading
from unittest.mock import patch, MagicMock, PropertyMock
import runpy
from tornado.autoreload import main

class AutoreloadTest(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.test_coverage = {}
        self.maxDiff = 1024
        self.path = mkdtemp()
        self.write_files(
            {
                "run_twice_magic.py": """
                    import os
                    import sys

                    import tornado.autoreload

                    sys.stdout.flush()

                    if "TESTAPP_STARTED" not in os.environ:
                        os.environ["TESTAPP_STARTED"] = "1"
                        tornado.autoreload._reload()
                    else:
                        os._exit(0)
                """
            }
        )

    def tearDown(self):
        super().tearDown()
        try:
            shutil.rmtree(self.path)
        except OSError:
            time.sleep(1)
            shutil.rmtree(self.path)

    def write_files(self, tree, base_path=None):
        if base_path is None:
            base_path = self.path
        for name, contents in tree.items():
            if isinstance(contents, dict):
                os.mkdir(os.path.join(base_path, name))
                self.write_files(contents, os.path.join(base_path, name))
            else:
                with open(os.path.join(base_path, name), "w", encoding="utf-8") as f:
                    f.write(textwrap.dedent(contents))

    def run_subprocess(self, args):
        pythonpath = os.getcwd()
        if "PYTHONPATH" in os.environ:
            pythonpath += os.pathsep + os.environ["PYTHONPATH"]

        p = Popen(
            args,
            stdout=subprocess.PIPE,
            env=dict(os.environ, PYTHONPATH=pythonpath),
            cwd=self.path,
            universal_newlines=True,
            encoding="utf-8",
        )

        for i in range(40):
            if p.poll() is not None:
                break
            time.sleep(0.1)
        else:
            p.kill()
            raise Exception("subprocess failed to terminate")

        out = p.communicate()[0]
        self.assertEqual(p.returncode, 0)
        return out

    def test_reload(self):
        main = """\
import sys

try:
    import testapp
except ImportError:
    print("import testapp failed")
else:
    print("import testapp succeeded")

spec = getattr(sys.modules[__name__], '__spec__', None)
print(f"Starting {__name__=}, __spec__.name={getattr(spec, 'name', None)}")
exec(open("run_twice_magic.py").read())
"""

        self.write_files(
            {
                "testapp": {
                    "__init__.py": "",
                    "__main__.py": main,
                },
            }
        )

        for wrapper in [False, True]:
            with self.subTest(wrapper=wrapper):
                with self.subTest(mode="module"):
                    if wrapper:
                        base_args = [sys.executable, "-m", "tornado.autoreload"]
                    else:
                        base_args = [sys.executable]
                    out = self.run_subprocess(base_args + ["-m", "testapp"])
                    self.assertEqual(
                        out,
                        (
                            "import testapp succeeded\n"
                            + "Starting __name__='__main__', __spec__.name=testapp.__main__\n"
                        )
                        * 2,
                    )

                with self.subTest(mode="file"):
                    out = self.run_subprocess(base_args + ["testapp/__main__.py"])
                    expect_import = (
                        "import testapp succeeded"
                        if wrapper
                        else "import testapp failed"
                    )
                    self.assertEqual(
                        out,
                        f"{expect_import}\nStarting __name__='__main__', __spec__.name=None\n"
                        * 2,
                    )

                with self.subTest(mode="directory"):
                    out = self.run_subprocess(base_args + ["testapp"])
                    expect_import = (
                        "import testapp succeeded"
                        if wrapper
                        else "import testapp failed"
                    )
                    self.assertEqual(
                        out,
                        f"{expect_import}\nStarting __name__='__main__', __spec__.name=__main__\n"
                        * 2,
                    )

    def test_reload_wrapper_preservation(self):
        main = """\
import sys

import testapp

if 'tornado.autoreload' not in sys.modules:
    raise Exception('started without autoreload wrapper')

print('Starting')
exec(open("run_twice_magic.py").read())
"""

        self.write_files(
            {
                "testapp": {
                    "__init__.py": "",
                    "__main__.py": main,
                },
            }
        )

        out = self.run_subprocess(
            [sys.executable, "-m", "tornado.autoreload", "-m", "testapp"]
        )
        self.assertEqual(out, "Starting\n" * 2)

    def test_reload_wrapper_args(self):
        main = """\
import os
import sys

print(os.path.basename(sys.argv[0]))
print(f'argv={sys.argv[1:]}')
exec(open("run_twice_magic.py").read())
"""
        self.write_files({"main.py": main})

        out = self.run_subprocess(
            [
                sys.executable,
                "-m",
                "tornado.autoreload",
                "main.py",
                "arg1",
                "--arg2",
                "-m",
                "arg3",
            ],
        )

        self.assertEqual(out, "main.py\nargv=['arg1', '--arg2', '-m', 'arg3']\n" * 2)

    def test_reload_wrapper_until_success(self):
        main = """\
import os
import sys

if "TESTAPP_STARTED" in os.environ:
    print("exiting cleanly")
    sys.exit(0)
else:
    print("reloading")
    exec(open("run_twice_magic.py").read())
"""

        self.write_files({"main.py": main})

        out = self.run_subprocess(
            [sys.executable, "-m", "tornado.autoreload", "--until-success", "main.py"]
        )

        self.assertEqual(out, "reloading\nexiting cleanly\n")

    def test_watch_file(self):
        with patch('tornado.autoreload.os.path.isfile', return_value=True):
            tornado.autoreload.watch('somefile.txt')
            self.assertIn('somefile.txt', tornado.autoreload._watched_files)
    
    def test_watch_directory(self):
        with patch('tornado.autoreload.os.path.isdir', return_value=True):
            tornado.autoreload.watch('somedir')
            self.assertIn('somedir', tornado.autoreload._watched_files)
    
    def test_start_autoreload(self):
        with patch('tornado.ioloop.IOLoop.instance') as mock_ioloop:
            mock_ioloop.return_value = mock_ioloop
            tornado.autoreload.start()
    
    def test_io_loop_start(self):
        with patch('tornado.ioloop.IOLoop.instance') as mock_ioloop:
            mock_ioloop.return_value = mock_ioloop
            tornado.autoreload.start()

    def test_reload_attempted(self):
        tornado.autoreload._reload_attempted = True
        tornado.autoreload._reload_on_update({})
        self.assertTrue(tornado.autoreload._reload_attempted)

    def test_task_id_not_none(self):
        tornado.autoreload._reload_attempted = False
        with patch('tornado.autoreload.process.task_id', return_value=1):
            tornado.autoreload._reload_on_update({})
            self.assertFalse(tornado.autoreload._reload_attempted)

    def test_non_module_objects_in_sys_modules(self):
        tornado.autoreload._reload_attempted = False
        with patch('tornado.autoreload.process.task_id', return_value=None):
            sys.modules['non_module'] = 'I am not a module'
            tornado.autoreload._reload_on_update({})
            self.assertNotIn('non_module', tornado.autoreload._watched_files)

    def test_module_without_file(self):
        tornado.autoreload._reload_attempted = False
        with patch('tornado.autoreload.process.task_id', return_value=None):
            mod = MagicMock(spec=types.ModuleType)
            del mod.__file__
            sys.modules['test_mod'] = mod
            tornado.autoreload._reload_on_update({})
            self.assertNotIn('test_mod', tornado.autoreload._watched_files)

    def test_module_with_pyc_file(self):
        tornado.autoreload._reload_attempted = False
        with patch('tornado.autoreload.process.task_id', return_value=None):
            mod = types.ModuleType('test_mod')
            mod.__file__ = '/path/to/module.pyc'
            sys.modules['test_mod'] = mod
            with patch('tornado.autoreload._check_file') as mock_check_file:
                tornado.autoreload._reload_on_update({})
                mock_check_file.assert_called_with({}, '/path/to/module.py')

    def test_watched_files(self):
        tornado.autoreload._reload_attempted = False
        tornado.autoreload._watched_files = {'/path/to/file.py'}
        with patch('tornado.autoreload._check_file') as mock_check_file:
            tornado.autoreload._reload_on_update({})
            mock_check_file.assert_called_with({}, '/path/to/file.py')

    @patch('tornado.autoreload.os.execv')
    def test_reload_sets_reload_attempted(self, mock_execv):
        tornado.autoreload._reload_attempted = False
        tornado.autoreload._reload_hooks = []
        tornado.autoreload._reload()
        self.assertTrue(tornado.autoreload._reload_attempted)

    @patch('tornado.autoreload.os.execv')
    def test_reload_calls_hooks(self, mock_execv):
        mock_hook = MagicMock()
        tornado.autoreload._reload_hooks = [mock_hook]
        tornado.autoreload._reload()
        mock_hook.assert_called_once()

    @patch('tornado.autoreload.os.execv')
    def test_reload_execv_called(self, mock_execv):
        tornado.autoreload._reload_hooks = []
        tornado.autoreload._reload()
        mock_execv.assert_called_once_with(sys.executable, [sys.executable] + sys.argv)

    @patch('tornado.autoreload.os.execv')
    @patch('tornado.autoreload.sys.platform', 'win32')
    def test_reload_on_windows(self, mock_execv):
        main_thread = MagicMock()
        main_thread.__class__ = threading._MainThread
        with patch('tornado.autoreload.threading.enumerate', return_value=[main_thread]):
            tornado.autoreload._reload_hooks = []
            tornado.autoreload._reload()
            mock_execv.assert_called_once_with(sys.executable, [sys.executable] + sys.argv)

    @patch('tornado.autoreload._autoreload_is_main', True)
    def test_autoreload_is_main(self):
        tornado.autoreload._original_argv = ['arg1', 'arg2']
        tornado.autoreload._original_spec = 'test_spec'
        tornado.autoreload._reload_hooks = []
        tornado.autoreload._reload_attempted = False

        with patch('tornado.autoreload.os.execv'):
            tornado.autoreload._reload()
            self.assertEqual(tornado.autoreload._original_argv, ['arg1', 'arg2'])
            self.assertEqual(tornado.autoreload._original_spec, 'test_spec')

    @patch('tornado.autoreload._has_execv', False)
    def test_no_execv(self):
        tornado.autoreload._original_argv = ['arg1', 'arg2']
        with patch('tornado.autoreload.subprocess.Popen') as mock_popen, patch('tornado.autoreload.os._exit') as mock_exit:
            tornado.autoreload._reload()
            mock_popen.assert_called_once_with([sys.executable] + ['arg1', 'arg2'])
            mock_exit.assert_called_once_with(0)

    @patch('tornado.autoreload.os.stat')
    def test_file_stat_exception(self, mock_stat):
        mock_stat.side_effect = Exception("File not found")
        modify_times = {}
        tornado.autoreload._check_file(modify_times, 'nonexistent_file.txt')
        self.assertNotIn('nonexistent_file.txt', modify_times)

    @patch('tornado.autoreload.os.stat')
    def test_file_not_in_modify_times(self, mock_stat):
        mock_stat.return_value.st_mtime = 100
        modify_times = {}
        tornado.autoreload._check_file(modify_times, 'new_file.txt')
        self.assertIn('new_file.txt', modify_times)
        self.assertEqual(modify_times['new_file.txt'], 100)

    @patch('tornado.autoreload.os.stat')
    def test_file_in_modify_times_no_change(self, mock_stat):
        mock_stat.return_value.st_mtime = 100
        modify_times = {'existing_file.txt': 100}
        tornado.autoreload._check_file(modify_times, 'existing_file.txt')
        self.assertEqual(modify_times['existing_file.txt'], 100) 

    @patch('tornado.autoreload.os.stat')
    @patch('tornado.autoreload.gen_log')
    @patch('tornado.autoreload._reload')
    def test_file_in_modify_times_with_change(self, mock_reload, mock_log, mock_stat):
        mock_stat.return_value.st_mtime = 200
        modify_times = {'existing_file.txt': 100}
        tornado.autoreload._check_file(modify_times, 'existing_file.txt')
        self.assertEqual(mock_log.info.call_args[0][0], "%s modified; restarting server")
        self.assertEqual(mock_log.info.call_args[0][1], 'existing_file.txt')
        mock_reload.assert_called_once()

    @patch('tornado.autoreload.wait')
    @patch('tornado.autoreload.watch')
    @patch('tornado.autoreload._autoreload_is_main', new_callable=PropertyMock)
    @patch('tornado.autoreload._original_argv', new_callable=PropertyMock)
    @patch('tornado.autoreload._original_spec', new_callable=PropertyMock)
    def test_main_with_module(self, mock_spec, mock_argv, mock_is_main, mock_watch, mock_wait):
        test_module = 'tornado.test.runtests'
        sys.argv = ['python', '-m', test_module]

        with patch('optparse.OptionParser.parse_args', return_value=(MagicMock(module=test_module, until_success=False), [])):
            with patch('runpy.run_module') as mock_run_module:
                main()
                mock_run_module.assert_called_once_with(test_module, run_name="__main__", alter_sys=True)
                self.assertTrue(mock_is_main)
                self.assertEqual(mock_argv, sys.argv)
                self.assertIsNone(mock_spec)
                mock_wait.assert_called_once()

    @patch('tornado.autoreload.wait')
    @patch('tornado.autoreload.watch')
    @patch('tornado.autoreload._autoreload_is_main', new_callable=PropertyMock)
    @patch('tornado.autoreload._original_argv', new_callable=PropertyMock)
    @patch('tornado.autoreload._original_spec', new_callable=PropertyMock)
    def test_main_with_path(self, mock_spec, mock_argv, mock_is_main, mock_watch, mock_wait):
        test_path = 'tornado/test/runtests.py'
        sys.argv = ['python', test_path]

        with patch('optparse.OptionParser.parse_args', return_value=(MagicMock(module=None, until_success=False), [test_path])):
            with patch('runpy.run_path') as mock_run_path:
                main()
                mock_run_path.assert_called_once_with(test_path, run_name="__main__")
                self.assertTrue(mock_is_main)
                self.assertEqual(mock_argv, sys.argv)
                self.assertIsNone(mock_spec)
                mock_wait.assert_called_once()

    @patch('tornado.autoreload.wait')
    @patch('tornado.autoreload.watch')
    @patch('tornado.autoreload._autoreload_is_main', new_callable=PropertyMock)
    @patch('tornado.autoreload._original_argv', new_callable=PropertyMock)
    @patch('tornado.autoreload._original_spec', new_callable=PropertyMock)
    def test_main_syntax_error(self, mock_spec, mock_argv, mock_is_main, mock_watch, mock_wait):
        test_path = 'tornado/test/runtests.py'
        sys.argv = ['python', test_path]

        with patch('optparse.OptionParser.parse_args', return_value=(MagicMock(module=None, until_success=False), [test_path])):
            with patch('runpy.run_path', side_effect=SyntaxError('Test syntax error')):
                with patch('traceback.extract_tb', return_value=[('file.py', 1, 'function', 'line')]):
                    main()
                    mock_watch.assert_called_with('file.py')
                    mock_wait.assert_called_once()

    @patch('tornado.autoreload.wait')
    @patch('tornado.autoreload.watch')
    @patch('tornado.autoreload._autoreload_is_main', new_callable=PropertyMock)
    @patch('tornado.autoreload._original_argv', new_callable=PropertyMock)
    @patch('tornado.autoreload._original_spec', new_callable=PropertyMock)
    def test_main_uncaught_exception(self, mock_spec, mock_argv, mock_is_main, mock_watch, mock_wait):
        test_path = 'tornado/test/runtests.py'
        sys.argv = ['python', test_path]

        with patch('optparse.OptionParser.parse_args', return_value=(MagicMock(module=None, until_success=False), [test_path])):
            with patch('runpy.run_path', side_effect=Exception('Test exception')):
                with patch('traceback.extract_tb', return_value=[('file.py', 1, 'function', 'line')]):
                    main()
                    mock_watch.assert_called_with('file.py')
                    mock_wait.assert_called_once()

    @patch('tornado.autoreload.wait')
    @patch('tornado.autoreload.watch')
    @patch('tornado.autoreload._autoreload_is_main', new_callable=PropertyMock)
    @patch('tornado.autoreload._original_argv', new_callable=PropertyMock)
    @patch('tornado.autoreload._original_spec', new_callable=PropertyMock)
    def test_main_exit_success(self, mock_spec, mock_argv, mock_is_main, mock_watch, mock_wait):
        test_module = 'tornado.test.runtests'
        sys.argv = ['python', '-m', test_module]

        with patch('optparse.OptionParser.parse_args', return_value=(MagicMock(module=test_module, until_success=True), [])):
            with patch('runpy.run_module') as mock_run_module:
                with patch('sys.exit', side_effect=SystemExit(0)) as mock_exit:
                    main()
                    mock_run_module.assert_called_once_with(test_module, run_name="__main__", alter_sys=True)
                    mock_exit.assert_called_once_with(0)

    @patch('tornado.autoreload.wait')
    @patch('tornado.autoreload.watch')
    @patch('tornado.autoreload._autoreload_is_main', new_callable=PropertyMock)
    @patch('tornado.autoreload._original_argv', new_callable=PropertyMock)
    @patch('tornado.autoreload._original_spec', new_callable=PropertyMock)
    def test_main_exit_failure(self, mock_spec, mock_argv, mock_is_main, mock_watch, mock_wait):
        test_module = 'tornado.test.runtests'
        sys.argv = ['python', '-m', test_module]

        with patch('optparse.OptionParser.parse_args', return_value=(MagicMock(module=test_module, until_success=True), [])):
            with patch('runpy.run_module') as mock_run_module:
                with patch('sys.exit', side_effect=SystemExit(1)) as mock_exit:
                    main()
                    mock_run_module.assert_called_once_with(test_module, run_name="__main__", alter_sys=True)
                    mock_exit.assert_called_once_with(1)
                    mock_wait.assert_called_once()

if __name__ == "__main__":
    unittest.main()
