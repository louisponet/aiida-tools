from aiida.orm import Dict, SinglefileData, Str
from aiida.engine import WorkChain, ToContext, while_, calcfunction, CalcJob
from aiida.plugins import CalculationFactory
import aiida_dynamic_workflows as flows

class CalcJobChain(WorkChain):

    @classmethod
    def define(cls, spec):
        super().define(spec)
        spec.input_namespace('calcjobs', dynamic=True)
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

        calcjobs = list(map(lambda x: CalculationFactory(cjobs[f'{x}'].value) if isinstance(cjobs[f'{x}'], Str) else cjobs[f'{x}'], range(0, len(cjobs))))
        inputs   = list(map(lambda x: inputs[f'{x}'], range(0, len(cjobs))))

        for i in range(0, len(calcjobs)):
            if i == 0:
                provided_ins = inputs[i].keys()
            else:
                if isinstance(calcjobs[i-1], CalcJob):
                    provided_ins = calcjobs[i-1].spec().outputs
                elif isinstance(calcjobs[i-1], flows.data.PyFunction):
                    provided_ins = calcjobs[i-1].returns

                if isinstance(calcjobs[i], CalcJob):
                    provided_ins += inputs[i].keys() 
                elif isinstance(calcjobs[i], flows.data.PyFunction):
                    provided_ins += inputs[i]['parameters'].keys()

    def setup(self):
        self.ctx.current_id = 0
        self.ctx.results    = dict()
        n = len(self.inputs['calcjobs'])
        self.ctx.calcjobs = list(map(lambda x: CalculationFactory(self.inputs['calcjobs'][f'{x}'].value) if isinstance(self.inputs['calcjobs'][f'{x}'], Str) else self.inputs['calcjobs'][f'{x}'], range(0, n)))
        self.ctx.inputs = list(map(lambda x: self.inputs['inputs'][f'{x}'], range(0, n)))
        
    def not_finished(self):
        return self.ctx.current_id < len(self.ctx.calcjobs) 

    def submit_next(self):
        id     = self.ctx.current_id
        inputs = self.ctx.inputs[id]
        cjob   = self.ctx.calcjobs[id]

        if isinstance(cjob, flows.data.PyFunction):
            return ToContext(current = self.submit(flows.engine.apply(cjob, **inputs['parameters']).on(inputs['environment'])))
        else:
            return ToContext(current = self.submit(cjob, **inputs))
        

    def process_current(self):
        results = dict()
        outputs = self.ctx.current.outputs.return_values if isinstance(self.ctx.calcjobs[self.ctx.current_id], flows.data.PyFunction) else self.ctx.current.outputs
        for k in outputs:
            results[k] = outputs[k]

        self.ctx.results[k] = results
        self.ctx.current_id += 1
        if self.not_finished():
            next = self.ctx.calcjobs[self.ctx.current_id]

            if isinstance(next, flows.data.PyFunction):
                inputs = self.ctx.inputs[self.ctx.current_id]['parameters']
                req_inputs = self.ctx.calcjobs[self.ctx.current_id].parameters
            else:
                inputs = self.ctx.inputs[self.ctx.current_id]
                tins = self.ctx.calcjobs[self.ctx.current_id].spec().inputs
                req_inputs = list(filter(lambda x: tins[x].required, tins))
            print("##########################################################")
            print(list(req_inputs))
            print("##########################################################")
            print("##########################################################")
            print(list(outputs))
            print("##########################################################")
            print("##########################################################")
            print(list(inputs))
            print("##########################################################")
            for k in outputs:
                if k not in inputs and k in req_inputs:
                    print("##########################################################")
                    print(outputs[k])
                    print("##########################################################")
                    t = outputs[k]
                    if isinstance(t, flows.data.PyRemoteData):
                        inputs[k] = outputs.return_values[k].fetch_value()
                    else:
                        inputs[k] = t

    def finalize(self):
        self.out('results', self.ctx.results)
    
