import nacl

from Jumpscale import j
import binascii

JSConfigBase = j.baseclasses.object_config
from nacl.signing import VerifyKey
from nacl.public import PrivateKey, PublicKey, SealedBox


class ThreebotClient(JSConfigBase):
    _SCHEMATEXT = """
    @url = jumpscale.threebot.client
    name** = ""                      #is the bot dns
    tid** =  0 (I)                     #threebot id
    host = "127.0.0.1" (S)          #for caching purposes
    port = 8901 (ipport)            #for caching purposes
    pubkey = ""                     #for caching purposes
    """

    def _init(self, **kwargs):
        self._pubkey_obj = None
        self._verifykey_obj = None
        self._sealedbox_ = None
        self._gedis_connections = {}
        assert self.name != ""

    def actors_get(self, package_name="all"):
        if not package_name in self._gedis_connections:
            name = "" if "all" else package_name
            g = j.clients.gedis.get(name=self.name, host=self.host, port=self.port, package_name=name)
            self._gedis_connections[package_name] = g
        return self._gedis_connections[package_name].actors

    def reload(self):
        for key, g in self._gedis_connections.items():
            g.reload()

    @property
    def _gedis(self):
        a = self.actors_get("all")
        return self._gedis_connections["all"]

    @property
    def actors_all(self):
        return self.actors_get("all")

    def encrypt_for_threebot(self, data, hex=False):
        """
        Encrypt data using the public key of the remote threebot
        :param data: data to be encrypted, should be of type binary

        @return: encrypted data hex or binary

        """
        if isinstance(data, str):
            data = data.encode()
        res = self._sealedbox.encrypt(data)
        if hex:
            res = binascii.hexlify(res)
        return res

    def verify_from_threebot(self, data, signature, data_is_hex=False):
        """
        :param data, if string will unhexlify else binary data to verify against verification key of the threebot who send us the data

        :return:
        """
        if isinstance(data, str) or data_is_hex:
            data = binascii.unhexlify(data)
        if len(signature) == 128:
            signature = binascii.unhexlify(signature)
        return self.verifykey_obj.verify(data, signature=signature)

    @property
    def _sealedbox(self):
        if not self._sealedbox_:
            self._sealedbox_ = SealedBox(self.pubkey_obj)
        return self._sealedbox_

    @property
    def pubkey_obj(self):
        if not self._pubkey_obj:
            self._pubkey_obj = self.verifykey_obj.to_curve25519_public_key()
        return self._pubkey_obj

    @property
    def verifykey_obj(self):
        if not self._verifykey_obj:
            assert self.pubkey
            verifykey = binascii.unhexlify(self.pubkey)
            assert len(verifykey) == 32
            self._verifykey_obj = VerifyKey(verifykey)
        return self._verifykey_obj

    def test_auth(self, bot_id):
        nacl_cl = j.data.nacl.get()
        nacl_cl._load_singing_key()
        epoch = str(j.data.time.epoch)
        signed_message = nacl_cl.sign(epoch.encode()).hex()
        cmd = "auth {} {} {}".format(bot_id, epoch, signed_message)
        return self._gedis._redis.execute_command(cmd)
