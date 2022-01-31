from aiida.orm.nodes.data.upf import get_pseudos_from_structure
from aiida.plugins import DataFactory
from aiida_tools.workflows.calcjob_chain import CalcJobChain
from aiida_tools.workflows.script_chain import ScriptChain
from aiida.orm import Str, Dict, SinglefileData
from aiida import orm, engine
import aiida
aiida.load_profile()


StructureData = DataFactory('structure')

alat = 4.  # angstrom
cell = [[alat, 0., 0., ],
        [0., alat, 0., ],
        [0., 0., alat, ],
        ]

# BaTiO3 cubic structure
s = StructureData(cell=cell)
s.append_atom(position=(0., 0., 0.), symbols='Ba')
s.append_atom(position=(alat/2., alat/2., alat/2.), symbols='Ti')
s.append_atom(position=(alat/2., alat/2., 0.), symbols='O')
s.append_atom(position=(alat/2., 0., alat/2.), symbols='O')
s.append_atom(position=(0., alat/2., alat/2.), symbols='O')

parameters = Dict(dict={
    'CONTROL': {
        'calculation': 'scf',
        'restart_mode': 'from_scratch',
        'wf_collect': True,
    },
    'SYSTEM': {
        'ecutwfc': 30.,
        'ecutrho': 240.,
    },
    'ELECTRONS': {
        'conv_thr': 1.e-6,
    }
})

parameters_projwfc = Dict(dict={
    'PROJWFC': {
        'DeltaE': 0.2,
        'ngauss': 1,
        'degauss': 0.02
    }})

KpointsData = DataFactory('array.kpoints')
kpoints = KpointsData()
kpoints.set_kpoints_mesh([4, 4, 4])

family = orm.load_group('SSSP/1.1/PBE/efficiency')
pseudos = family.get_pseudos(structure=s)


# Setup the workchain
code = orm.load_code('pw-6.6@localhost')
code_projwfc = orm.load_code('projwfc-6.6@localhost')

calcjobs = {
    '0': Str('quantumespresso.pw'),
    '1': Str('quantumespresso.projwfc')
}

metadata = {
    'metadata': {
        'options': {
            'withmpi': False,
            'resources': {
                'num_machines': 1,
                'num_mpiprocs_per_machine': 14}
        }
    }
}

preprocess = {
    '1': Str("inputs['parent_folder'] = self.ctx.current.outputs['retrieved']")}

inputs = {
    '0': {'code': code,
          'kpoints': kpoints,
          'structure': s,
          'pseudos': pseudos,
          'parameters': parameters,
          **metadata},
    '1': {'code': code_projwfc,
          'parameters': parameters_projwfc,
          **metadata}
}

all = {
    'inputs': inputs,
    'calcjobs': calcjobs,
    'preprocess': preprocess
}
output_dict, node = engine.run_get_node(CalcJobChain, **all)
