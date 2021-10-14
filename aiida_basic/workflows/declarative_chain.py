from aiida.orm import Dict, SinglefileData, Str, load_node, load_code, load_group
from aiida.engine import WorkChain, ToContext, while_, calcfunction
from aiida.plugins import CalculationFactory, DataFactory
from jsonschema import validate
import json

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
                }
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
    typ = d['type']
    val = d['value']
    if typ == "dict":
        validate(instance=val, schema=structschema)
        structure = DataFactory('structure')(cell=val['cell'])
        for a in val['atoms']:
            structure.append_atom(**a)
        return structure
    elif typ == "node":
        return load_node(val)


def dict2code(d):
    typ = d['type']
    val = d['value']
    if typ == 'string':
        return load_code(val)
    elif typ == 'node':
        return load_node(val)


def dict2upf(d):
    typ = d['type']
    val = d['value']

    if typ == 'dict':
        validate(instance=val, schema=upfschema)
        group = load_group(val['group'])
        return group.get_pseudo(element=val['element'])
    elif typ == 'node':
        return load_node(val)


def dict2kpoints(d):
    typ = d['type']
    val = d['value']

    kpoints = DataFactory("array.kpoints")()
    if typ == 'array':
        kpoints.set_kpoints_mesh(val)
        return kpoints
    elif typ == 'node':
        return load_node(val)


def dict2datanode(d):
    typ = d['type']
    dat = d['data']

    if typ == 'Code':
        return dict2code(dat)
    elif typ == 'Structure':
        return dict2structure(dat)
    elif typ == 'UpfData':
        return dict2upf(dat)
    elif typ == 'KpointsData':
        return dict2kpoints(dat)
    elif typ == 'Dict':
        return Dict(dict=dat)

    elif typ == 'dict':
        out = dict()
        for k in dat:
            out[k] = dict2datanode(dat[k])

        return out


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
            spec = json.load(f)

        validate(instance=spec, schema=schema)

        self.ctx.steps = spec['steps']

    def not_finished(self):
        return self.ctx.current_id < len(self.ctx.steps)

    def submit_next(self):
        id = self.ctx.current_id
        step = self.ctx.steps[id]
        # This needs to happen because no dict 2 node for now.
        inputs = dict()
        inputs['metadata'] = step['metadata']
        for k in step['inputs']:
            inputs[k] = dict2datanode(step['inputs'][k])

        cjob = CalculationFactory(step['calcjob'])

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
