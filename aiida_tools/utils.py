from pathlib import Path
from urllib.parse import urlsplit
import cachecontrol
import requests
from ruamel.yaml import YAML
import jsonref

# Copied from https://github.com/aiidalab/aiidalab/blob/90b334e6a473393ba22b915fdaf85d917fd947f4/aiidalab/registry/yaml.py
# licensed under the MIT license
REQUESTS = cachecontrol.CacheControl(requests.Session())

class JsonYamlLoader(jsonref.JsonLoader):

    safe_yaml = YAML(typ="safe")

    def __call__(self, uri, **kwargs):
        uri_split = urlsplit(uri)
        if Path(uri_split.path).suffix in (".yml", ".yaml"):
            if uri_split.scheme == "file":
                content = Path(uri_split.path).read_bytes()
            else:
                response = REQUESTS.get(uri)
                response.raise_for_status()
                content = response.content
            return self.safe_yaml.load(content)
        else:
            return super().__call__(uri, **kwargs)

