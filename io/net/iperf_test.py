#!/usr/bin/env python

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
# Copyright: 2018 IBM
# Author: Narasimhan V <sim@linux.vnet.ibm.com>

"""
iperf is a tool for active measurements of the maximum achievable
bandwidth on IP networks.
"""

import os
import netifaces
from avocado import main
from avocado import Test
from avocado.utils.software_manager import SoftwareManager
from avocado.utils import build
from avocado.utils import archive
from avocado.utils import process
from avocado.utils.genio import read_file
from avocado.utils.configure_network import PeerInfo
from avocado.utils import configure_network
from avocado.utils.ssh import Session


class Iperf(Test):
    """
    Iperf Test
    """

    def setUp(self):
        """
        To check and install dependencies for the test
        """
        self.peer_user = self.params.get("peer_user_name", default="root")
        self.peer_ip = self.params.get("peer_ip", default="")
        self.peer_password = self.params.get("peer_password", '*',
                                             default=None)
        interfaces = netifaces.interfaces()
        self.iface = self.params.get("interface", default="")
        if self.iface not in interfaces:
            self.cancel("%s interface is not available" % self.iface)
        self.ipaddr = self.params.get("host_ip", default="")
        self.netmask = self.params.get("netmask", default="")
        configure_network.set_ip(self.ipaddr, self.netmask, self.iface)
        self.session = Session(self.peer_ip, user=self.peer_user,
                               password=self.peer_password)
        smm = SoftwareManager()
        for pkg in ["gcc", "autoconf", "perl", "m4", "libtool"]:
            if not smm.check_installed(pkg) and not smm.install(pkg):
                self.cancel("%s package is need to test" % pkg)
            cmd = "%s install %s" % (smm.backend.base_command, pkg)
            output = self.session.cmd(cmd)
            if not output.exit_status == 0:
                self.cancel("unable to install the package %s on peer machine "
                            % pkg)
        if self.peer_ip == "":
            self.cancel("%s peer machine is not available" % self.peer_ip)
        self.mtu = self.params.get("mtu", default=1500)
        self.peerinfo = PeerInfo(self.peer_ip, peer_user=self.peer_user,
                                 peer_password=self.peer_password)
        self.peer_interface = self.peerinfo.get_peer_interface(self.peer_ip)
        if not self.peerinfo.set_mtu_peer(self.peer_interface, self.mtu):
            self.cancel("Failed to set mtu in peer")
        if not configure_network.set_mtu_host(self.iface, self.mtu):
            self.cancel("Failed to set mtu in host")
        self.iperf = os.path.join(self.teststmpdir, 'iperf')
        iperf_download = self.params.get("iperf_download", default="https:"
                                         "//excellmedia.dl.sourceforge.net/"
                                         "project/iperf2/iperf-2.0.13.tar.gz")
        tarball = self.fetch_asset(iperf_download, expire='7d')
        archive.extract(tarball, self.iperf)
        self.version = os.path.basename(tarball.split('.tar')[0])
        self.iperf_dir = os.path.join(self.iperf, self.version)
        cmd = "scp -r %s %s@%s:/tmp" % (self.iperf_dir, self.peer_user,
                                        self.peer_ip)
        if process.system(cmd, shell=True, ignore_status=True) != 0:
            self.cancel("unable to copy the iperf into peer machine")
        cmd = "cd /tmp/%s;./configure ppc64le;make" % self.version
        output = self.session.cmd(cmd)
        if not output.exit_status == 0:
            self.cancel("Unable to compile Iperf into peer machine")
        self.iperf_run = str(self.params.get("IPERF_SERVER_RUN", default=0))
        if self.iperf_run == '1':
            cmd = "/tmp/%s/src/iperf -s" % self.version
            self.session.cmd(cmd)
        os.chdir(self.iperf_dir)
        process.system('./configure', shell=True)
        build.make(self.iperf_dir)
        self.iperf = os.path.join(self.iperf_dir, 'src')
        self.expected_tp = self.params.get("EXPECTED_THROUGHPUT", default="85")

    def test(self):
        """
        Test run is a One way throughput test. In this test, we have one host
        transmitting (or receiving) data from a client. This transmit large
        messages using multiple threads or processes.
        """
        speed = int(read_file("/sys/class/net/%s/speed" % self.iface))
        os.chdir(self.iperf)
        cmd = "./iperf -c %s" % self.peer_ip
        result = process.run(cmd, shell=True, ignore_status=True)
        if result.exit_status:
            self.fail("FAIL: Iperf Run failed")
        for line in result.stdout.decode("utf-8").splitlines():
            if 'sender' in line:
                tput = int(line.split()[6].split('.')[0])
                if tput < (int(self.expected_tp) * speed) / 100:
                    self.fail("FAIL: Throughput Actual - %s%%, Expected - %s%%"
                              ", Throughput Actual value - %s "
                              % ((tput*100)/speed, self.expected_tp,
                                 str(tput)+'Mb/sec'))

    def tearDown(self):
        """
        Killing Iperf process in peer machine
        """
        cmd = "pkill iperf; rm -rf /tmp/%s" % self.version
        output = self.session.cmd(cmd)
        if not output.exit_status == 0:
            self.fail("Either the ssh to peer machine machine\
                       failed or iperf process was not killed")
        if not configure_network.set_mtu_host(self.iface, '1500'):
            self.cancel("Failed to set mtu in host")
        if not self.peerinfo.set_mtu_peer(self.peer_interface, '1500'):
            self.cancel("Failed to set mtu in peer")
        configure_network.unset_ip(self.iface)


if __name__ == "__main__":
    main()
