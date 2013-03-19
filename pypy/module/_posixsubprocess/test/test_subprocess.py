import sys
import os
from os.path import dirname
from pypy.tool.pytest.objspace import gettestobjspace

def setup_module(mod):
    usemodules = ['_posixsubprocess', 'signal']
    # py3k os.open uses subprocess, requiring the following per platform
    if os.name != 'nt':
        usemodules += ['fcntl', 'select']
    else:
        usemodules += ['_rawffi', 'thread']
    mod.space = gettestobjspace(usemodules=usemodules)

class AppTestSubprocess:
    # XXX write more tests

    def setup_class(cls):
        cls.space = space
        cls.w_dir = space.wrap(dirname(__file__))

    def test_cloexec_pipe(self):
        import _posixsubprocess, os
        fd1, fd2 = _posixsubprocess.cloexec_pipe()
        # Sanity checks
        assert 0 <= fd1 < 4096
        assert 0 <= fd2 < 4096
        os.close(fd1)
        os.close(fd2)

    def test_close_fds_true(self):
        import subprocess
        import os.path
        import os

        fds = os.pipe()
        #self.addCleanup(os.close, fds[0])
        #self.addCleanup(os.close, fds[1])

        open_fds = set(fds)
        # add a bunch more fds
        for _ in range(9):
            fd = os.open("/dev/null", os.O_RDONLY)
            #self.addCleanup(os.close, fd)
            open_fds.add(fd)

        p = subprocess.Popen(['/usr/bin/env', 'python', os.path.join(self.dir, 'fd_status.py')], stdout=subprocess.PIPE, close_fds=True)
        output, ignored = p.communicate()
        remaining_fds = set(map(int, output.split(b',')))

        assert not (remaining_fds & open_fds), "Some fds were left open"
        assert 1 in remaining_fds, "Subprocess failed"
