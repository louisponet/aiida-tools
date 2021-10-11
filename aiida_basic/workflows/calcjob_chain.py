
from aiida.orm import Dict, SinglefileData, Str
from aiida.engine import WorkChain, ToContext, while_, calcfunction
from aiida.plugins import CalculationFactory

import ast

class CalcJobChain(WorkChain):

    @classmethod
    def define(cls, spec):
        super().define(spec)
        spec.input_namespace('calcjobs', dynamic=True, valid_type=Str)
        spec.input_namespace('inputs', dynamic=True)
        spec.input_namespace('preprocess', dynamic=True, required=False,valid_type=Str)
        spec.input_namespace('postprocess', dynamic=True, required=False, valid_type=Str)
        spec.inputs.validator = cls.check_inputs

        spec.outline(
            cls.setup,
            while_(cls.not_finished)(
                cls.submit_next,
                cls.process_current
            ),
            cls.finalize
        )
        spec.output_namespace('results', dynamic=True)

    @classmethod
    def check_inputs(self, inputs, _):
        cjobs = inputs['calcjobs']
        inputs = inputs['inputs']
        if len(cjobs) != len(inputs):
            return 'ERROR: amount of calcjobs and inputs are not equal.'

        for k in cjobs.keys():
            if k not in inputs:
                return f'ERROR: key {k} not found in inputs.'

    def setup(self):
        self.ctx.current_id = 0
        self.ctx.results    = dict()


    def not_finished(self):
        return self.ctx.current_id < len(self.inputs['calcjobs']) 

    def submit_next(self):
        id     = self.ctx.current_id
        k      = f'{id}'
        inputs = self.inputs['inputs'][k]
        cjob   = CalculationFactory(self.inputs['calcjobs'][k].value)

        if 'preprocess' in self.inputs:
            if k in self.inputs['preprocess']:
                exec(self.inputs['preprocess'][k].value)

        return ToContext(current = self.submit(cjob, **inputs))
        

    def process_current(self):
        results = dict()
        outputs = self.ctx.current.outputs
        for k in outputs:
            results[k] = self.ctx.current.outputs[k]

        k = f'{self.ctx.current_id}'
        if 'postprocess' in self.inputs:
            if k in self.inputs['postprocess']:
                exec(self.inputs['postprocess'][k].value)

        self.ctx.results[k] = results
        self.ctx.current_id += 1

    def finalize(self):
        self.out('results', self.ctx.results)
    
