import aiida
aiida.load_profile()
from aiida import orm
from aiida import engine
from aiida_tools.workflows.declarative_chain import DeclarativeChain
import os

all = {
    'workchain_specification': orm.SinglefileData(os.path.abspath(getcwd() +"/workflow.json"))
}

engine.run(DeclarativeChain, **all)
