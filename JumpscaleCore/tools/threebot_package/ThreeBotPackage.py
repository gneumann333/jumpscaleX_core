import sys

from Jumpscale import j

JSConfigBase = j.baseclasses.object_config


class ThreeBotPackage(JSConfigBase):

    _SCHEMATEXT = """
        @url = jumpscale.threebot.package.1
        name** = "main"
        giturl = "" (S)  #if empty then local
        path = ""
        status = "init,config,installed,running,halted,disabled,error" (E)
        source = (O) !jumpscale.threebot.package.source.1
        actor = (O) !jumpscale.threebot.package.actor.1
        bcdb = (LO) !jumpscale.threebot.package.bcdb.1

        @url = jumpscale.threebot.package.source.1
        name = ""
        threebot = ""
        description = ""
        version = "" (S)

        @url = jumpscale.threebot.package.actor.1
        namespace = ""

        @url = jumpscale.threebot.package.bcdb.1
        namespace = ""
        type = "zdb,sqlite" (E)
        instance = "default"

        """

    @property
    def threebot_server(self):
        return j.servers.threebot.get(name=self.threebot_server_name)

    @property
    def gedis_server(self):
        return self.threebot_server.gedis_server

    @property
    def openresty(self):
        return self.threebot_server.openresty_server

    def _init(self, **kwargs):
        self._init_ = False
        if self.status == "init":
            self.config_load()

    def config_load(self):
        self._log_info("load package.toml config", data=self)
        tomlfile = f"{self.path}/package.toml"
        if not j.sal.fs.exists(tomlfile):
            raise j.exceptions.Input("cannot find config file on:%s" % tomlfile)
        config = j.data.serializers.toml.loads(j.sal.fs.readFile(tomlfile))
        self._data._data_update(config)
        if self.status == "init":
            self.status = "config"

    def load(self):

        if not "bcdb" in j.threebot.__dict__:
            # means we are not in a threebot server, should not allow the following to happen
            raise j.exceptions.Base("cannot use threebot package data model from process out of threebot")

        if self._init_ == False:

            # Parent root directory for packages needed to be in sys.path
            # in order to be able to import file properly inside packages
            packages_root = j.sal.fs.getParent(self.path)
            if not packages_root in sys.path:
                sys.path.append(packages_root)

            self._path_package = "%s/package.py" % (self.path)

            j.shell()

            if not j.sal.fs.exists(self._path_package):
                raise j.exceptions.Input(
                    "cannot find package.py in the package directory", data={"path": self._path_package}
                )

            klass = j.tools.codeloader.load(obj_key="Package", path=self._path_package, reload=False)
            self._package_author = klass(package=self)

            path = self.path + "/models"
            if j.sal.fs.exists(path):
                self.bcdb.models_add(path)

            path = self.path + "/actors"
            if j.sal.fs.exists(path):
                self.gedis_server.actors_add(path, namespace=self._package_author.actors_namespace)

            path = self.path + "/chatflows"
            if j.sal.fs.exists(path):
                self.gedis_server.chatbot.chatflows_load(path)

            def load_wiki(wiki_name=None, wiki_path=None):
                """we cannot use name parameter with myjobs.schedule, it has a name parameter itself"""
                wiki = j.tools.markdowndocs.load(name=wiki_name, path=wiki_path, pull=False)
                wiki.write()

            path = self.path + "/wiki"
            if j.sal.fs.exists(path):
                name = self.name
                j.servers.myjobs.schedule(load_wiki, wiki_name=name, wiki_path=path)

            if j.sal.fs.exists(self.path + "/html"):
                self._web_load("html")
            elif j.sal.fs.exists(self.path + "/frontend"):
                self._web_load("frontend")

        self._init_ = True

    def _web_load(self, app_type="frontend"):
        for port in (443, 80):
            website = self.openresty.get_from_port(port)
            locations = website.locations.get(f"{self.name}_locations")
            if app_type == "frontend":
                website_location = locations.locations_spa.new()
            elif app_type == "html":
                website_location = locations.locations_static.new()

            website_location.name = self.name
            website_location.path_url = f"/{self.name}"
            website_location.use_jumpscale_weblibs = False
            fullpath = j.sal.fs.joinPaths(self.path, f"{app_type}/")
            website_location.path_location = fullpath

            locations.configure()
            website.configure()

    @property
    def bcdb(self):
        """
        will only return bcdb if only 1
        :return:
        """
        j.shell()
        return self._package_author.bcdb

    def install(self):
        self.load()
        if self.giturl:
            self.path = j.clients.git.getContentPathFromURLorPath(self.giturl, branch=self.branch)
        self._package_author.prepare()

    def start(self):
        self.load()
        self._package_author.start()
        self.status = "running"
        self.save()

    def stop(self):
        self.load()
        self._package_author.stop()
        self.status = "halted"
        self.save()

    def uninstall(self):
        self.load()
        self._package_author.uninstall()

    def disable(self):
        self.status = "disabled"
        self.save()

    def enable(self):
        self.status = "installed"
        self.save()
