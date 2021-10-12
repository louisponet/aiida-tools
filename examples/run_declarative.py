import aiida
aiida.load_profile()
from aiida import orm
from aiida import engine
from aiida_basic.workflows.declarative_chain import DeclarativeChain
import os

all = {
    'workchain_specification': orm.SinglefileData(os.path.splitdir(os.getcwd() + __file__)[0] +"/workflow.json")
}

engine.run(DeclarativeChain, **all)
