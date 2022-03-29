# aiida-tools

A collection of building blocks to extend the functionality of AiiDA.
These are mostly for my own personal use.


## Installation
Since this plugin is not yet registered, use the following commands to install:
```
git clone https://github.com/louisponet/aiida-tools
cd aiida-tools
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
from aiida_tools.workflows.script_chain import ScriptChain
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
{"p1": 3}
EOF
cat << EOF > context1.json
{}
EOF

python test_python.py params1.json context1.json results1.json

cat << EOF > params2.json
{"p1": 3}
EOF

cp context1.json context2.json

python test_python.py params2.json context2.json results2.json

cat results1.json
cat results2.json
```

# Declarative Chain
This is a self assembling workchain that utilizes json or yaml files to specify both the steps in the workchain as well as the data to be used with it.

## Syntax
The overall structure of the input files are as follows:
```yaml
---
steps:
- calcjob: <aiida calcjob or calculation entry point>
  inputs:
    <dict with inputs for the calcjob>
```
The array of steps will be ran sequentially inside the workchain. The structure above is the most basic form of a workflow file.

### Data Referencing
To keep the files clean and readable, it is possible to first specify some data and then reference it in the `steps` part of the workflow file. For example:
```yaml
---
data:
    kpoints:
    - 6
    - 6
    - 6
steps:
- calcjob: quantumespresso.pw
  inputs:
    kpoints:
        "$ref": "#/data/kpoints"
    <other inputs>
```
will paste the definition of `kpoints` in the `data` section into the input where it's referenced. This uses [jsonref](https://pypi.org/project/jsonref/), see its documentation for more possibilities. It is for example also possible to reference data from an external json/yaml file.

### Jinja templates
Often, we want to use the workchain context `self.ctx` to store and retrieve intermediate results throughout the workchain's execution. To facilitate this we can use [jinja](https://jinja.palletsprojects.com/en/3.1.x/) templates such as:
`"{{ ctx.scf_dir }}"` to resolve certain values into the yaml script. The use of will become clear later.

### PostProcessing
By defining a `postprocess` field, common operations can be performed that will run _after_ the execution of the `current` calcjob. For example
```yaml
---
data:
    <data>
steps:
- calcjob: quantumespresso.pw
  inputs:
    <inputs>
  postprocess:
  - "{{ ctx.current.outputs['remote_folder'] | to_ctx('scf_dir') }}"
- calcjob: quantumespresso.pw
  inputs:
    parameters:
        "$ref": "#/data/pw_parameters"
    parameters.CONTROL.calculation: nscf
    parent_folder: "{{ ctx.scf_dir }}"
```
Here we can observe a couple of new constructs. The first is `ctx.current`, signifying the currently executed calcjob (i.e. the `scf` calculation). Secondly, the `|` and `to_ctx` in `"{{ ctx.current.outputs['remote_folder'] | to_ctx('scf_dir') }}"` mean the value is piped through a the `to_ctx` filter, which assigns it to the variable `scf_dir`, stored in the workchain's context `self.ctx` for later referencing. Indeed we see that in the next step we retrieve this value using `"{{ ctx.scf_dir }}"` as the `parent_folder` input. Finally we note the line `parameters.CONTROL.calculation: nscf`, this simply means that we set a particular value in the `parameters` dictionary.

### If
Steps can define an `if` field which contains a statement. If the statement is true, the step will be executed, otherwise it is ignored.
```yaml
---
steps:
- if: "{{ ctx.should_run }}"
  calcjob: quantumespresso.pw
  inputs:
    <inputs>
```
Here, depending on the previously set `ctx` variable, the step will run.
!!!! note
    the corresponding else statement would be `"{{ not ctx.should_run }}"`

### While
It is possible to specify a `while` field, with a sequence of steps that will be run until the while statement is false, e.g.:
```yaml
---
steps:
- while: "{{ ctx.count < 5 }}"
  steps:
    - calcjob: quantumespresso.pw
      inputs:
        <inputs>
      postprocess:
      - "{{ (ctx.count + 1) | to_ctx('count') }}"
```
will run the same calcjob 4 times
!!!! note
    Don't forget to set the ctx.count variable to something in the postprocessing step of the previous calcjob.

### Error
It is possible that one of the steps errors. The error code and message will always be reported by the workchain. It is also possible to explicitely specify an error to return from the workchain if this happens using:
```yaml
---
steps:
- calcjob: quantumespresso.pw
  inputs:
        <inputs>
  error:
    code: 23
    message: "The first pw calculation failed."
```
### Further examples
For a fully featured example, see the `bands.yaml` file in the examples directory which mimics largely the `PwBandsWorkchain` from the [aiida-quantumespresso](https://github.com/aiidateam/aiida-quantumespresso) package.
