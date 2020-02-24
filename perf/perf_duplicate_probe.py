#!/usr/bin/env python
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: 2019 IBM
# Author: Shirisha G <shiganta@in.ibm.com>

import platform
from avocado import Test
from avocado import main
from avocado.utils import distro, genio, process
from avocado.utils.software_manager import SoftwareManager


class PerfProbe(Test):

    def setUp(self):
        '''
        Install the basic packages to support perf and systemtap-sdt-devel
        '''
        # Check for basic utilities
        smm = SoftwareManager()
        distro_name = distro.detect().name
        deps = []
        if 'Ubuntu' in distro_name:
            deps.extend(['linux-tools-common', 'linux-tools-%s' %
                         platform.uname()[2]])
        elif 'rhel' in distro_name:
            deps.extend(['perf', 'kernel-debuginfo'])
        elif 'SuSE' in distro_name:
            deps.extend(['perf', 'kernel-default-base-debuginfo'])
        else:
            self.cancel("Install the package for perf supported\
                      by %s" % distro_name)
        for package in deps:
            if not smm.check_installed(package) and not smm.install(package):
                self.cancel('%s is needed for the test to be run' % package)

    def test_probe(self):
        output = process.run("perf probe select_task_rq_fair:15", sudo=True)
        if 'select_task_rq_fair' in output.stderr.decode("utf-8") and 'select_task_rq_fair_' in output.stderr.decode("utf-8"):
            fail_flag = 1
        output = genio.read_all_lines("/sys/kernel/debug/tracing/kprobe_events")
        for line in output:
            if 'select_task_rq_fair' in line or 'select_task_rq_fair_' in line:
                fail_flag += 1
        if(fail_flag >= 2):
            self.fail("perf probe is placing multiple probe at the same location ")

    def tearDown(self):
        # Deleting all the probed events
        process.run('perf probe -d \\*')


if __name__ == "__main__":
    main()
