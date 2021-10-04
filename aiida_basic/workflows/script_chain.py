from aiida.orm import Dict, SinglefileData 
from aiida.engine import WorkChain, ToContext, while_
from ..calculations.script import Script


class ScriptChain(WorkChain):
    """
    A basic modular WorkChain that runs a series of scripts using the specified code.
    Each script has an associated set of input parameters.
    Communcation between the scripts is facilitated through files in json format,
    which are passed as commandline arguments. See the Script calculation for more
    information. Each script is expected to write a results file in json format,
    which is read back into the results output.
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)
        spec.input_namespace('scripts', dynamic=True, valid_type=SinglefileData)
        spec.input_namespace('parameters', dynamic=True, valid_type=Dict)
        spec.inputs.validator = cls.check_inputs
        spec.expose_inputs(Script, exclude=['script', 'parameters', 'context'], namespace='script')
        spec.outline(
            cls.setup,
            while_(cls.finished)(
                cls.submit_next,
                cls.process_current
            ),
            cls.finalize
        )
        spec.output_namespace('results', dynamic = True)

    @classmethod
    def check_inputs(self, inputs, _):
        scripts = inputs['scripts']
        parameters = inputs['scripts']
        if len(scripts) != len(parameters):
            return 'ERROR: length of scripts and parameters inputs are not equal.'

        for k in scripts.keys():
            if k not in parameters:
                return f'ERROR: key {k} not found in parameters.'

    def setup(self):
        self.ctx.n = 0
        self.ctx.results = dict()
        self.ctx.context = Dict()

    def finished(self):
        return self.ctx.n < len(self.inputs['scripts']) 

    def submit_next(self):
        n = self.ctx.n
        param = self.inputs['parameters'][f'{n}']
        script = self.inputs['scripts'][f'{n}']

        inputs = {'context': self.ctx.context, 'parameters': param, 'script': script, **self.exposed_inputs(Script, 'script')}

        return ToContext(current_script = self.submit(Script, **inputs))

    def process_current(self):
        self.ctx.results[f'{self.ctx.n}'] = self.ctx.current_script.outputs['results']
        self.ctx.context = self.ctx.current_script.outputs['context']
        self.ctx.n += 1

    def finalize(self):
        self.out('results', self.ctx.results)
