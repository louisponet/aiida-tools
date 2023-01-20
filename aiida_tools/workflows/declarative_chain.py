from aiida import orm
from jinja2.nativetypes import NativeEnvironment
from jinja2 import Environment
from aiida.orm import Dict, SinglefileData, Str, load_node, load_code, load_group, Int, Float, List
from aiida.engine import WorkChain, ToContext, while_, calcfunction, run_get_node, ExitCode
from aiida.plugins import CalculationFactory, DataFactory, WorkflowFactory
from aiida.engine.utils import is_process_function
from jsonschema import validate
import json
import sys
import plumpy
from aiida_pseudo.data.pseudo.upf import UpfData
import jsonref
from os.path import splitext
from ruamel.yaml import YAML
from ..utils import my_fancy_loader

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
                "if": {
                    "type": "string"
                },
                "while": {
                    "type": "string"
                },
                "calcjob": {
                    "type": "string"
                },
                "calculation": {
                    "type": "string"
                },
                "workflow": {
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
                "steps": {
                    "type": "array"
                },
                "node": {
                    "type": "integer"
                },
                "error": {
                    "type": "object"
                }
            },
            "additionalProperties": False,
            "title": "Step"
        }
    }
}

ExitCode_schema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "title": "ExitCode",
    "required": ["code"],
    "properties": {
        "code": {
            "type": "integer"
        },
        "message": {
            "type": "string"
        }
    },
    "additionalProperties": False
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
    if typ is orm.AbstractCode:
        return dict2code(dat)
    elif typ is orm.StructureData:
        return dict2structure(dat)
    elif typ is UpfData or typ is orm.nodes.data.upf.UpfData:
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
        spec.exit_code(2, 'ERROR_SUBPROCESS', message='A subprocess has failed.') 

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

        spec = jsonref.JsonRef.replace_refs(tspec, loader = my_fancy_loader)
        validate(instance=spec, schema=schema)
        self.ctx.steps = spec['steps']
        self.env = NativeEnvironment()
        self.env.filters['to_ctx'] = self.to_ctx
        self.env.filters['to_results'] = self.to_results

        self.ctx.in_while = False

        if 'setup' in spec:
            for k in spec['setup']:
                self.eval_template(k)

    def not_finished(self):
        return self.ctx.current_id < len(self.ctx.steps)

    def submit_next(self):

        id = self.ctx.current_id
        step = self.ctx.steps[id]
        if 'if' in step and not self.eval_template(step['if']):
            self.ctx.current_id += 1
            return self.submit_next()

        elif "while" in step:
            if self.eval_template(step['while']):
                if not self.ctx.in_while:
                    # Enter the while loop
                    self.ctx.in_while = True
                    self.ctx.while_first_id = len(self.ctx.steps)
                    self.ctx.while_entry_id = id
                    self.ctx.steps += step['steps']
                    self.ctx.current_id = self.ctx.while_first_id
                else:
                    # Reroll the while loop
                    self.ctx.current_id = self.ctx.while_first_id

            elif self.ctx.in_while:
                # Cleanup while loop
                self.ctx.in_while = False
                self.ctx.steps = self.ctx.steps[0:-len(step['steps'])]
                self.ctx.current_id += 1

            return self.submit_next()

        else:
            if "node" in step:
                self.ctx.current = load_node(step['node'])

            elif "calcjob" in step or "workflow" in step or "calculation" in step:
                # This needs to happen because no dict 2 node for now.
                inputs = dict()
                if "calcjob" in step:
                    cjob = CalculationFactory(step['calcjob'])
                elif "calculation" in step:
                    cjob = WorkflowFactory(step['calculation'])
                elif "workflow" in step:
                    cjob = WorkflowFactory(step['workflow'])
                else:
                    ValueError(f"Unrecognized step {step}")

                spec_inputs = cjob.spec().inputs
                for k in step['inputs']:
                    valid_type = None
                    if k in spec_inputs:
                        i = spec_inputs.get(k)
                        valid_type = i.valid_type

                    d = step['inputs'][k]
                    if isinstance(d, dict):
                        if 'type' in d:
                            valid_type = DataFactory(d.pop('type'))

                        if 'value' in d:
                            val = d['value']
                        else:
                            val = d
                    else:
                        val = d

                    if isinstance(val, str):
                        val = self.eval_template(val)

                    if valid_type is not None and not isinstance(val, valid_type):
                        valid_type = valid_type[0] if isinstance(valid_type, tuple) else valid_type
                        if k in spec_inputs:
                            val = dict2datanode(val, valid_type, isinstance(i, plumpy.PortNamespace))
                        else:
                            val = dict2datanode(val, valid_type)
                    elif k != 'metadata' and not isinstance(val, orm.Data):
                        val = orm.to_aiida_type(val)

                    set_dot2index(inputs, k, val)
                # print(cjob)
                if is_process_function(cjob):
                    return ToContext(current = run_get_node(cjob, **inputs)[1])
                else:
                    return ToContext(current=self.submit(cjob, **inputs))
                    

    def process_current(self):
        step = self.ctx.steps[self.ctx.current_id]
        if not self.ctx.current.is_finished_ok:
            self.report(f'A subprocess failed with exit status {self.ctx.current.exit_status}: {self.ctx.current.exit_message}')
            if 'error' in step:
                validate(step['error'], schema=ExitCode_schema)
                return ExitCode(step['error']['code']) if 'message' not in step['error'] else ExitCode(step['error']['code'], message=step['error']['message'])

        if "postprocess" in step:
            for k in step["postprocess"]:
                self.eval_template(k)

        self.ctx.current_id += 1

        if self.ctx.in_while and self.ctx.current_id == len(self.ctx.steps):
            self.ctx.current_id = self.ctx.while_entry_id

    # Jinja evaluation
    def eval_template(self, s):
        return self.env.from_string(s).render(ctx=self.ctx)

    # Jinja Filters
    def to_ctx(self, value, key):
        self.ctx[key] = value
        return value

    def to_results(self, value, key):
        self.ctx.results[key] = value
        return value

    def finalize(self):
        self.out('results', self.ctx.results)
