from aiida import orm
from aiida.orm import Dict, SinglefileData, Str, load_node, load_code, load_group, Int, Float
from aiida.engine import WorkChain, ToContext, while_, calcfunction
from aiida.plugins import CalculationFactory, DataFactory
from jsonschema import validate
import json
import sys
import plumpy
import aiida_pseudo
import jsonref


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
    "additionalProperties": False,
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
                "preprocess": {
                    "type": "string"
                },
                "postprocess": {
                    "type": "string"
                },
                "metadata": {
                    "type": "object"
                },
            },
            "additionalProperties": False,
            "required": ["calcjob", "inputs", "metadata"],
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
    structure = DataFactory('structure')(cell=d['cell'])
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
    kpoints = DataFactory("array.kpoints")()
    kpoints.set_kpoints_mesh(d)
    return kpoints


def dict2datanode(dat, typ, dynamic):
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
    elif typ is aiida_pseudo.data.pseudo.upf.UpfData:
        return dict2upf(dat)
    elif typ is orm.KpointsData:
        return dict2kpoints(dat)
    elif typ is Dict or typ is None:
        return Dict(dict=dat)
    else:
        return typ(dat)


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

        with self.inputs['workchain_specification'].open(mode="r") as f:
            spec = jsonref.load(f, jsonschema=schema)

        self.ctx.steps = spec['steps']

    def not_finished(self):
        return self.ctx.current_id < len(self.ctx.steps)

    def submit_next(self):
        id = self.ctx.current_id
        step = self.ctx.steps[id]
        # This needs to happen because no dict 2 node for now.
        inputs = dict()

        cjob = CalculationFactory(step['calcjob'])
        spec_inputs = cjob.spec().inputs
        inputs['metadata'] = step['metadata'] 
        for k in step['inputs']:
            if k not in spec_inputs:
                return f"ERROR: In: {step['calcjob']}\n\t{k} is not a valid input."

            i = spec_inputs.get(k)
            inputs[k] = dict2datanode(step['inputs'][k], i.valid_type, isinstance(i, plumpy.PortNamespace))

        if 'preprocess' in step:
            exec(step['preprocess'])

        return ToContext(current=self.submit(cjob, **inputs))

    def process_current(self):
        results = dict()
        outputs = self.ctx.current.outputs
        for k in outputs:
            results[k] = self.ctx.current.outputs[k]

        step = self.ctx.steps[self.ctx.current_id]
        if 'postprocess' in step:
            exec(step['preprocess'])

        self.ctx.results[f'{self.ctx.current_id}'] = results
        self.ctx.current_id += 1

    def finalize(self):
        self.out('results', self.ctx.results)
