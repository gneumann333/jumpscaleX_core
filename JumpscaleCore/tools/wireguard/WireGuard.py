from Jumpscale import j
from configparser import ConfigParser
from io import StringIO
import netaddr


def to_section(section, data):
    config = ConfigParser()
    config.optionxform = str
    config.add_section(section)
    for key, value in data.items():
        config.set(section, key, str(value))
    buffer = StringIO()
    config.write(buffer)
    return buffer.getvalue()


class WireGuard(j.baseclasses.object_config):
    _SCHEMATEXT = """
    @url = jumpscale.wireguard.peer.1
    name** = "main"
    sshclient_name = "" (S)
    key_private_ = "" (S)
    key_public = "" (S) 
    network_private = "" (S)
    network_public = "" (S)
    interface_name = "wg0" (S)
    port = 7777 (I)
    peers = (LI)
    """

    def _init(self, **kwargs):
        self._executor = None

    @property
    def islocal(self):
        return self.sshclient_name == ""

    def key_pair_get(self):
        if not self.key_private_:
            rc, privatekey, err = self.executor.execute("wg genkey", showout=False)
            self.key_private_ = privatekey.strip()
        if not self.key_public:
            rc, publickey, err = self.executor.execute("echo {} | wg pubkey".format(privatekey.strip()), showout=False)
            self.key_public = publickey.strip()
        return self.key_private_, self.key_public

    def save(self):
        if not self.key_private_ or not self.key_public:
            self.key_pair_get()
        super().save()

    @property
    def executor(self):
        if self._executor is None:
            if self.islocal:
                self._executor = j.tools.executorLocal
            else:
                self._executor = j.tools.executor.ssh_get(self.sshclient_name)
        return self._executor

    def install(self):
        """
        get wireguard to work
        :return:
        """
        if self.executor.platformtype.platform_is_osx:
            self.executor.execute("brew install wireguard-tools")
        else:
            # need to check on ubuntu
            rc, out, err = self.executor.execute("wg", die=False)
            if rc != 0:
                C = """
                export DEBIAN_FRONTEND=noninteractive
                add-apt-repository -y ppa:wireguard/wireguard
                apt-get update
                apt-get upgrade -y --force-yes
                apt-get install wireguard -y
                """
                self.executor.execute(C)

    @property
    def peers_objects(self):
        for peer in self.peers:
            yield j.tools.wireguard.get_by_id(peer)

    @property
    def wid(self):
        return self._id

    def peer_add(self, wireguard):
        if wireguard.wid not in self.peers:
            self.peers.append(wireguard.wid)
            self.save()

    def peer_remove(self, wireguard):
        if wireguard.wid in self.peers:
            self.peers.remove(wireguard.wid)
            self.save()

    def configure(self):
        config = ConfigParser()
        config.add_section("Interface")
        private, _ = self.key_pair_get()
        interface = {
            "Address": self.network_private,
            "SaveConfig": "true",
            "PrivateKey": private,
            "ListenPort": str(self.port),
        }

        config = ""
        config += to_section("Interface", interface)
        for peerobject in self.peers_objects:
            _, publickey = peerobject.key_pair_get()
            peer = {"PublicKey": publickey}
            subnet = netaddr.IPNetwork(peerobject.network_private)
            if peerobject.network_public:
                peer["EndPoint"] = f"{peerobject.network_public}:{peerobject.port}"
                peer["PersistentKeepalive"] = "25"
                peer["AllowedIPs"] = f"{subnet.network}/{subnet.prefixlen}"
            else:
                peer["AllowedIPs"] = f"{subnet.ip}"
            config += to_section("Peer", peer)

        configpath = f"/tmp/{self.interface_name}.conf"
        self.executor.file_write(configpath, config)
        rc, _, _ = self.executor.execute(f"wg show {self.interface_name}", die=False)
        if rc != 0:
            # interface is not up let's bring it up
            self.executor.execute(f"wg-quick up {configpath}")
        else:
            # let's update config path
            self.executor.execute(f"wg-quick strip {configpath} | wg setconf {self.interface_name} /dev/stdin")

    def start(self):
        if self.executor.platformtype.platform_is_osx:
            command = "sudo wireguard-go utun9"
        else:
            command = f"wg-quick up {self.interface_name}"
        self.executor.execute(command)
