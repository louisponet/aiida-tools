import aiida
from aiida import orm, engine
from aiida.orm import Str, Dict, SinglefileData
from aiida_basic.workflows.script_chain import ScriptChain
from aiida_basic.workflows.calcjob_chain import CalcJobChain
aiida.load_profile()
# Setting up inputs
code = orm.load_code('python@localhost')

# First we define the script to run, here twice the same one.
calcjobs = {
    '0': Str('basic.script'),
    '1': Str('basic.script')
}

# Some needed metadata
metadata = {
    'metadata': {
        'options': {
            'withmpi': False,
            'resources': {
                'num_machines': 1,
                'num_mpiprocs_per_machine': 1}
        }
    }
}

inputs = {
    '0': {'script': SinglefileData('/home/lponet/Software/pythondev/test.py'), 'parameters': Dict(dict={'p1': 3}), 'context': Dict(), 'code': code, **metadata},
    '1': {'script': SinglefileData('/home/lponet/Software/pythondev/test.py'), 'parameters': Dict(dict={'p1': 3}),  'code': code, **metadata}
}

prep1 = """
inputs['context'] = self.ctx.context
"""

preprocess = {
    '1': Str(prep1)
}

postp0 = """
self.ctx.context = outputs['context']
"""

postprocess = {
    '0': Str(postp0)
}

all = {
    'calcjobs': calcjobs,
    'inputs': inputs,
    'preprocess': preprocess,
    'postprocess': postprocess
}


# Running the calculation & parsing results
output_dict, node = engine.run_get_node(CalcJobChain, **all)

print(f"Script 1 results: {node.outputs.results['0']['context'].get_dict()}")
print(f"Script 2 results: {node.outputs.results['1']['context'].get_dict()}")
