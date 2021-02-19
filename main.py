import os
import subprocess
import yaml
import requests
import asyncio, aiohttp
import packaging.version

class MatrixGenerator:
    owner = "conan-io"
    repo = "conan-center-index"

    package_denylist = ["android-ndk"]

    dry_run = True

    def __init__(self, token=None, user=None, pw=None):
        self.session = requests.session()
        self.session.headers = {}
        if token:
            self.session.headers["Authorization"] = "token %s" % token

        self.session.headers["Accept"] = "application/vnd.github.v3+json"
        self.session.headers["User-Agent"] = "request"

        self.session.auth = None
        if user and pw:
            self.session.auth = requests.auth.HTTPBasicAuth(user, pw)


    def _make_request(self, method, url, **kwargs):
        if self.dry_run and method in ["PATCH", "POST"]:
            return

        r = self.session.request(method, "https://api.github.com" + url, **kwargs)
        r.raise_for_status()
        return r

    async def generate_matrix(self):

        r = self._make_request("GET", f"/repos/{self.owner}/{self.repo}/contents/recipes")

        res = []

        async with aiohttp.ClientSession() as session:

            async def _add_package(package, repo, ref):
                verStr = "0.0.0"
                version = packaging.version.Version(verStr)
                async with session.get("https://raw.githubusercontent.com/%s/%s/recipes/%s/config.yml" % (repo, ref, package)) as r:
                    if r.status  == 404:
                        return
                    r.raise_for_status()
                    config = yaml.safe_load(await r.text())
                    for v in config["versions"]:
                        try:
                            tmpVer = packaging.version.Version(v)
                            if tmpVer > version:
                                version = tmpVer
                                verStr = v
                        except packaging.version.InvalidVersion:
                            print("Error parsing version %s for package %s" % (v, package))
                    if verStr != "0.0.0":
                        res.append({
                                'package': package,
                                'version': verStr,
                            })
            tasks = []
            for package in  r.json():
                if not package["name"] in self.package_denylist:
                    tasks.append(asyncio.create_task(_add_package(package['name'], '%s/%s' % (self.owner, self.repo), 'master')))

            await asyncio.gather(*tasks)

        for p in res:
            ref = "%s/%s@" % (p["package"], p["version"])
            def _package_exists(ref):
                try:
                    subprocess.run(["conan", "search", ref], check=True)
                    return True
                except subprocess.CalledProcessError:
                    return False

            if True:
                try:
                    subprocess.run(["conan", "install", ref], check=False)
                except subprocess.CalledProcessError as ex:
                    if ex.returncode != 6:
                        raise
                try:
                    res = subprocess.run(["conan", "inspect", ref, "--raw=default_options"], check=False, capture_output=True, text=True)
                    if "shared=True" in res.stdout:
                        shared_value="False"
                    elif "shared=False" in res.stdout:
                        shared_value="True"
                    else:
                        shared_value=None
                    if shared_value:
                        subprocess.run(["conan", "install", ref, "-o", "%s:shared=%s" % (ref, shared_value)], check=False)

                except subprocess.CalledProcessError as ex:
                    if ex.returncode != 6:
                        raise





def main():
    d = MatrixGenerator(token=os.getenv("GH_TOKEN"))
    loop = asyncio.get_event_loop()
    loop.run_until_complete(d.generate_matrix())


if __name__ == "__main__":
    # execute only if run as a script
    main()
