from aiida.orm import Dict, SinglefileData, Str, load_node
from aiida.engine import WorkChain, ToContext, while_, calcfunction
from aiida.plugins import CalculationFactory
from jsonschema import validate
import json

schema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "WorkChain spec",
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
                }
            },
            "additionalProperties": False,
            "required": ["calcjob", "inputs"],
            "title": "Step"
        }
    }
}

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
        self.ctx.results    = dict()

        with self.inputs['workchain_specification'].open(mode="r") as f:
            spec = json.load(f)

        validate(instance=spec, schema=schema)

        self.ctx.steps = spec['steps']

    def not_finished(self):
        return self.ctx.current_id < len(self.ctx.steps)

    def submit_next(self):
        id     = self.ctx.current_id
        step   = self.ctx.steps[id]
        # This needs to happen because no dict 2 node for now.
        inputs = dict()
        for k in step['inputs']:
            t = step['inputs'][k]
            if isinstance(t, list):
                inputs[k] = map(load_node, step['inputs'])
            elif isinstance(t, int):
                inputs[k] = load_node(step['inputs'][k])

            # For things like pseudos etc
            elif isinstance(t, dict) and k != "metadata":
                inputs[k] = dict()
                for v in t:
                    inputs[k][v] = load_node(t[v])
                    
            else:
                inputs[k] = step['inputs'][k]

        cjob   = CalculationFactory(step['calcjob'])

        if 'preprocess' in step:
            exec(step['preprocess'])

        return ToContext(current = self.submit(cjob, **inputs))

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
    
