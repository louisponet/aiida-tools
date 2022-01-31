from aiida import orm
from aiida.orm import Dict, SinglefileData, Str, load_node, load_code, load_group, Int, Float, List
from aiida.engine import WorkChain, ToContext, while_, calcfunction, run_get_node
from aiida.plugins import CalculationFactory, DataFactory
from aiida.engine.utils import is_process_function
from jsonschema import validate
import json
import sys
import plumpy
from aiida_pseudo.data.pseudo.upf import UpfData
import jsonref
from os.path import splitext
from ruamel.yaml import YAML
from ..utils import JsonYamlLoader

# from jinja2.nativetypes import NativeEnvironment

# TODO: extend schema to include also the postprocess and preprocess objects
schema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "title": "Chain",
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "$ref": "#/definitions/Step"
            },
            "minItems": 1
        }
    },
    "required": ["steps"],
    "definitions": {
        "Step": {
            "type": "object",
            "properties": {
                "calcjob": {
                    "type": "string"
                },
                "inputs": {
                    "type": "object"
                },
                "postprocess": {
                    "type": "array"
                },
                "metadata": {
                    "type": "object"
                },
                "node": {
                    "type": "integer"
                }
            },
            "additionalProperties": False,
            "title": "Step"
        }
    }
}

structschema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "title": "Structure",
    "required": ["cell", "atoms"],
    "properties": {
        "atoms": {
            "type": "array",
            "items": {
                "$ref": "#/definitions/Atom"
            },
            "minItems": 1
        },
        "cell": {
            "$ref": "#/definitions/Cell"
        }
    },
    "definitions": {
        "Atom": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "string"
                },
                "position": {
                    "$ref": "#/definitions/Vec3"
                }
            },
            "required": ["symbols", "position"]
        },
        "Cell": {
            "type": "array",
            "items": {
                "$ref": "#/definitions/Vec3"
            },
            "required": ["a", "b", "c"],
            "properties": {
                "a": {
                    "$ref": "#/definitions/Vec3"
                },
                "b": {
                     "$ref": "#/definitions/Vec3"
                },
                "c": {
                    "$ref": "#/definitions/Vec3"
                }
            }
        },
        "Vec3": {
            "type": "array",
            "items": {
                "type": "number"
            },
            "minItems": 3,
            "maxItems": 3
        }
    }
}

upfschema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "title": "UpfData",
    "required": ["group", "element"],
    "properties": {
        "group": {
            "type": "string"
        },
        "element": {
            "type": "string"
        }
    }
}


def dict2structure(d):
    validate(instance=d, schema=structschema)
    structure = DataFactory('core.structure')(cell=d['cell'])
    for a in d['atoms']:
        structure.append_atom(**a)
    return structure


def dict2code(d):
    return load_code(d)


def dict2upf(d):
    validate(instance=d, schema=upfschema)
    group = load_group(d['group'])
    return group.get_pseudo(element=d['element'])


#TODO: implement for old upfs?
def dict2upf_deprecated(d):
    return None


def dict2kpoints(d):
    kpoints = DataFactory("core.array.kpoints")()
    if isinstance(d[0], list):
        kpoints.set_kpoints(d)
    else:
        kpoints.set_kpoints_mesh(d)
    return kpoints


def dict2datanode(dat, typ, dynamic=False):
    # Resolve recursively
    if dynamic:
        out = dict()
        for k in dat:
            # Is there only 1 level of dynamisism?
            out[k] = dict2datanode(dat[k], typ, False)
        return out

    # If node is specified, just load node
    if dat is dict and "node" in dat:
        return load_node(dat["node"])

    # More than one typ possible
    if isinstance(typ, tuple):
        for t in typ:
            try:
                return dict2datanode(dat, t, dynamic)
            except:
                None

    # Else resolve DataNode from value
    if typ is orm.Code:
        return dict2code(dat)
    elif typ is orm.StructureData:
        return dict2structure(dat)
    elif typ is UpfData:
        return dict2upf(dat)
    elif typ is orm.KpointsData:
        return dict2kpoints(dat)
    elif typ is Dict:
        return Dict(dict=dat)
    elif typ is List:
        return List(list=dat)
    else:
        return typ(dat)


def get_dot2index(d, key):
    if isinstance(key, str):
        return get_dot2index(d, key.split('.'))
    elif len(key) == 1:
        return d[key[0]]
    else:
        return get_dot2index(d[key[0]], key[1:])


def set_dot2index(d, key, val):
    if isinstance(key, str):
        return set_dot2index(d, key.split('.'), val)
    elif len(key) == 1:
        d[key[0]] = val
    else:
        t = key[0]
        if t not in d.keys():
            d[t] = dict()

        return set_dot2index(d[t], key[1:], val)


class DeclarativeChain(WorkChain):

    @classmethod
    def define(cls, spec):
        super().define(spec)
        spec.input('workchain_specification', valid_type=SinglefileData)

        spec.outline(
            cls.setup,
            while_(cls.not_finished)(
                cls.submit_next,
                cls.process_current
            ),
            cls.finalize
        )
        spec.output_namespace('results', dynamic=True)

    def setup(self):
        self.ctx.current_id = 0
        self.ctx.results = dict()

        ext = splitext(self.inputs['workchain_specification'].filename)[1]
        with self.inputs['workchain_specification'].open(mode="r") as f:
            if ext == ".yaml":
                tspec = YAML(typ="safe").load(f)
            else:
                spec = jsonref.load(f)

        spec = jsonref.JsonRef.replace_refs(tspec, loader = JsonYamlLoader())
        validate(instance=spec, schema=schema)
        self.ctx.steps = spec['steps']

    def not_finished(self):
        return self.ctx.current_id < len(self.ctx.steps)

    def submit_next(self):
        id = self.ctx.current_id
        step = self.ctx.steps[id]
        if "node" in step:
            self.ctx.current = load_node(step['node'])

        elif "calcjob" in step:
            # This needs to happen because no dict 2 node for now.
            inputs = dict()

            cjob = CalculationFactory(step['calcjob'])
            spec_inputs = cjob.spec().inputs
            for k in step['inputs']:
                valid_type = None
                if k in spec_inputs:
                    i = spec_inputs.get(k)
                    valid_type = i.valid_type

                d = step['inputs'][k]
                if 'type' in d:
                    valid_type = DataFactory(d.pop('type'))
                if 'value' in d:
                    val = d['value']
                elif 'from_context' in d:
                    val = get_dot2index(self.ctx, d['from_context'])
                elif 'link' in d:
                    link = d['link']
                    if 'step' in link:
                        val = get_dot2index(self.ctx.results[f"{link['step']}"], link['output'])
                    else:
                        val = get_dot2index(self.ctx.current.outputs, link)
                # elif 'jinja' in d:
                #     env = NativeEnvironment()
                #     t = env.from_string(d['jinja'])

                else:
                    val = d

                if valid_type is not None and not isinstance(val, valid_type):
                    if k in spec_inputs:
                        val = dict2datanode(val, valid_type, isinstance(i, plumpy.PortNamespace))
                    else:
                        val = dict2datanode(val, valid_type)

                set_dot2index(inputs, k, val)

            if is_process_function(cjob):
                return ToContext(current = run_get_node(cjob, **inputs)[1])
            else:
                return ToContext(current=self.submit(cjob, **inputs))
            
    def process_current(self):
        results = dict()
        outputs = self.ctx.current.outputs
        for k in outputs:
            results[k] = self.ctx.current.outputs[k]

        step = self.ctx.steps[self.ctx.current_id]
        if "postprocess" in step:
            for work in step["postprocess"]:
                if "to_context" in work:
                    to_context = work["to_context"]
                    if "value" in to_context:
                        val = to_context["value"]
                    elif "output" in to_context:
                        val = get_dot2index(self.ctx.current.outputs, to_context["output"])
                    elif "attribute" in to_context:
                        val = get_dot2index(self.ctx.current.attributes, to_context["attribute"])

                    set_dot2index(self.ctx, to_context["name"], val)

        self.ctx.results[f'{self.ctx.current_id}'] = results
        self.ctx.current_id += 1

    def finalize(self):
        self.out('results', self.ctx.results)