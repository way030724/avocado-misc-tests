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
# Copyright: 2016 IBM
# Author: Narasimhan V <sim@linux.vnet.ibm.com>

"""
Tcpdump Test.
"""

import os
import netifaces
from avocado import Test
from avocado import main
from avocado.utils import process
from avocado.utils import distro
from avocado.utils import archive
from avocado.utils import build
from avocado.utils.software_manager import SoftwareManager
from avocado.utils.network.interfaces import NetworkInterface
from avocado.utils.network.hosts import LocalHost, RemoteHost
from avocado.utils import wait


class TcpdumpTest(Test):
    """
    Test the tcpdump for specified interface.
    """

    def setUp(self):
        """
        Set up.
        """
        self.iface = self.params.get("interface", default="")
        self.count = self.params.get("count", default="500")
        self.nping_count = self.params.get("nping_count", default="")
        self.peer_ip = self.params.get("peer_ip", default="")
        self.drop = self.params.get("drop_accepted", default="10")
        self.host_ip = self.params.get("host_ip", default="")
        self.option = self.params.get("option", default='')
        # Check if interface exists in the system
        interfaces = netifaces.interfaces()
        if self.iface not in interfaces:
            self.cancel("%s interface is not available" % self.iface)
        if not self.peer_ip:
            self.cancel("peer ip should specify in input")
        self.ipaddr = self.params.get("host_ip", default="")
        self.netmask = self.params.get("netmask", default="")
        localhost = LocalHost()
        self.networkinterface = NetworkInterface(self.iface, localhost)
        try:
            self.networkinterface.add_ipaddr(self.ipaddr, self.netmask)
            self.networkinterface.save(self.ipaddr, self.netmask)
        except Exception:
            self.networkinterface.save(self.ipaddr, self.netmask)
        self.networkinterface.bring_up()
        if not wait.wait_for(self.networkinterface.is_link_up, timeout=120):
            self.cancel("Link up of interface is taking longer than 120 seconds")
        self.peer_user = self.params.get("peer_user", default="root")
        self.peer_password = self.params.get("peer_password", '*',
                                             default="None")
        self.mtu = self.params.get("mtu", default=1500)
        remotehost = RemoteHost(self.peer_ip, self.peer_user,
                                password=self.peer_password)
        self.peer_interface = remotehost.get_interface_by_ipaddr(self.peer_ip).name
        self.peer_networkinterface = NetworkInterface(self.peer_interface,
                                                      remotehost)
        if self.peer_networkinterface.set_mtu(self.mtu) is not None:
            self.cancel("Failed to set mtu in peer")
        if self.networkinterface.set_mtu(self.mtu) is not None:
            self.cancel("Failed to set mtu in host")

        # Install needed packages
        smm = SoftwareManager()
        detected_distro = distro.detect()
        pkgs = ['tcpdump', 'flex', 'bison', 'gcc', 'gcc-c++', 'nmap']
        for pkg in pkgs:
            if not smm.check_installed(pkg) and not smm.install(pkg):
                self.cancel("%s package Can not install" % pkg)
        if detected_distro.name == "SuSE":
            self.nmap = os.path.join(self.teststmpdir, 'nmap')
            nmap_download = self.params.get("nmap_download", default="https:"
                                            "//nmap.org/dist/"
                                            "nmap-7.80.tar.bz2")
            tarball = self.fetch_asset(nmap_download)
            self.version = os.path.basename(tarball.split('.tar')[0])
            self.n_map = os.path.join(self.nmap, self.version)
            archive.extract(tarball, self.nmap)
            os.chdir(self.n_map)
            process.system('./configure ppc64le', shell=True)
            build.make(self.n_map)
            process.system('./nping/nping -h', shell=True)

    def test(self):
        """
        Performs the tcpdump test.
        """
        cmd = "ping -I %s %s -c %s" % (self.iface, self.peer_ip, self.count)
        output_file = os.path.join(self.outputdir, 'tcpdump')
        if self.option in ('tcp', 'udp', 'icmp'):
            obj = self.nping(self.option)
            obj.start()
        else:
            obj = process.SubProcess(cmd, verbose=False, shell=True)
            obj.start()
        cmd = "tcpdump -i %s -n -c %s" % (self.iface, self.count)
        if self.option in ('host', 'src'):
            cmd = "%s %s %s" % (cmd, self.option, self.host_ip)
        elif self.option == "dst":
            cmd = "%s %s %s" % (cmd, self.option, self.peer_ip)
        else:
            cmd = "%s %s" % (cmd, self.option)
        cmd = "%s -w '%s'" % (cmd, output_file)
        for line in process.run(cmd, shell=True,
                                ignore_status=True).stderr.decode("utf-8") \
                                                   .splitlines():
            if "packets dropped by kernel" in line:
                self.log.info(line)
                if int(line[0]) >= (int(self.drop) * int(self.count) / 100):
                    self.fail("%s, more than %s percent" % (line, self.drop))
        obj.stop()

    def nping(self, param):
        """
        perform nping
        """
        detected_distro = distro.detect()
        if detected_distro.name == "SuSE":
            cmd = "./nping/nping --%s %s -c %s" % (param,
                                                   self.peer_ip, self.nping_count)
            return process.SubProcess(cmd, verbose=False, shell=True)
        else:
            cmd = "nping --%s %s -c %s" % (param, self.peer_ip, self.nping_count)
            return process.SubProcess(cmd, verbose=False, shell=True)

    def tearDown(self):
        '''
        unset ip for host interface
        '''
        if self.networkinterface.set_mtu('1500') is not None:
            self.cancel("Failed to set mtu in host")
        if self.peer_networkinterface.set_mtu('1500') is not None:
            self.cancel("Failed to set mtu in peer")
        self.networkinterface.remove_ipaddr(self.ipaddr, self.netmask)


if __name__ == "__main__":
    main()
