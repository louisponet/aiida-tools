# aiida-basic

A collection of basic building blocks to be used with AiiDA.


## Installation
Since this plugin is not yet registered, use the following commands to install:
```
git clone https://github.com/louisponet/aiida-basic
cd aiida-basic
pip install ./
reentry scan
```

## `Script` and `ScriptChain`
The goal of the `Script` `CalcJob` and `ScriptChain` `WorkChain` is to allow users to run a sequence of scripts while capturing the provenance,
and allow for a string of these scripts to be ran inside the AiiDA daemon as seperate execution blocks.

Communication between the scripts, and between the scripts and AiiDA is facilitated through json formatted files.

### Example
In this example we will simply reproduce the input parameters as results,
and create and increment one of the entries in the `context` dictionary.
The assumption is that the `python` code is already set up on the local machine.

The following two `python` scripts will be used as a demonstration:

Submission:
```python
import aiida
from aiida import orm, engine
from aiida.orm import SinglefileData, Dict
from aiida_basic.workflows.script_chain import ScriptChain
aiida.load_profile()
# Setting up inputs
code = orm.load_code('python@localhost')

# First we define the script to run, here twice the same one.
scripts = {
    '0': SinglefileData('test_python.py'),
    '1': SinglefileData('test_python.py')
}

# Then we define the parameters of EACH script.
params = {'0': Dict(dict={'p1': 3}),
          '1': Dict(dict={'p1': 3})}

# Some needed metadata
metadata = {
    'code': code,
    'metadata': {
        'options': {
            'withmpi': False,
            'resources': {
                'num_machines': 1,
                'num_mpiprocs_per_machine': 1}
        }
    }
}
all = {
    'parameters': params,
    'scripts': scripts,
    'script': metadata
}


# Running the calculation & parsing results
output_dict, node = engine.run_get_node(ScriptChain, **all)

print(f"Script 1 results: {node.outputs.results['0'].get_dict()}")
print(f"Script 2 results: {node.outputs.results['1'].get_dict()}")
```

Script:
```python
import json
import sys


def create_out(params, context):
    # If the context dict already has c1 defined we add 1 to it
    if 'c1' in context:
        context['c1'] += 1
    # otherwise we create it
    else:
        context['c1'] = 1

    return {'r1': params['p1'], 'c1': context['c1']}


if __name__ == "__main__":

    param_file = sys.argv[1]
    context_file = sys.argv[2]
    results_file = sys.argv[3]

    # Read the parameters
    with open(param_file, "r") as pfile:
        params = json.load(pfile)

    # Read the context
    with open(context_file, "r") as cfile:
        context = json.load(cfile)

    # Create the results dictionary and mutate the
    # context, then write the results to the results
    # file.
    out = create_out(params, context)
    with open(results_file, "w") as rfile:
        json.dump(out, rfile)

    # Now write the context dict to communicate it to next
    # scripts.
    with open(context_file, "w") as cfile:
        json.dump(context, cfile)

```

Saving the second file as `test_python.py` and the first as `run_python.py` in the same directory, we can run the chain as `python run_python.py`, which should show you the expected outputs.

As follows from the example, what happened here is similar to running the following bash script:
```bash
#!/bin/bash

cat << EOF > params1.json
{p1: 3}
EOF
cat << EOF > context1.json
{}
EOF

python test_python.py params1.json context1.json results1.json

cat << EOF > params2.json
{p1: 3}
EOF

cp context1.json context2.json

python test_python.py params2.json context2.json results2.json

cat results1.json
cat results2.json
```
