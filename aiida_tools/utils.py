from pathlib import Path
from urllib.parse import urlsplit
import cachecontrol
import requests
from ruamel.yaml import YAML
import jsonref

# Copied from https://github.com/aiidalab/aiidalab/blob/90b334e6a473393ba22b915fdaf85d917fd947f4/aiidalab/registry/yaml.py
# licensed under the MIT license
REQUESTS = cachecontrol.CacheControl(requests.Session())

def my_fancy_loader(uri):
    uri_split = urlsplit(uri)
    if Path(uri_split.path).suffix in (".yml", ".yaml"):
        if uri_split.scheme == "file":
            content = Path(uri_split.path).read_bytes()
        else:
            response = REQUESTS.get(uri)
            response.raise_for_status()
            content = response.content
        return YAML(typ="safe").load(content)
    else:
        return jsonref.load_uri(uri, **kwargs)

