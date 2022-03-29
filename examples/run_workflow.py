import aiida
aiida.load_profile()
from aiida import orm
from aiida import engine
from aiida_tools.workflows.declarative_chain import DeclarativeChain
import sys
import os

if __name__ == "__main__":
    workflow = sys.argv[1]
    all = {
        'workchain_specification': orm.SinglefileData(os.path.abspath(workflow))
    }

    engine.run(DeclarativeChain, **all)

