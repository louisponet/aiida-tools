from aiida.common.datastructures import CalcInfo, CodeInfo
from aiida.common.folders import Folder
from aiida.engine import CalcJob, CalcJobProcessSpec, ExitCode
from aiida.orm import Dict, SinglefileData, Code
from os.path import splitext
import json


class Script(CalcJob):
    """
    A simple CalcJob that runs the script using the specified code. The parameters
    and context Dicts will be dumped to json files that are passed as the first and
    second argument to the script. The results are expected to be saved in
    json format in the file passed as the third argument to the script.

    Since the context Dict is passed as both in and output, this can be used
    to communicate variables between scripts.
    """
    @classmethod
    def define(cls, spec: CalcJobProcessSpec):
        super().define(spec)
        spec.input('script',         valid_type=SinglefileData)
        spec.input('parameters',     valid_type=Dict)
        spec.input('context',        valid_type=Dict)
        spec.input('code',           valid_type=Code)
        spec.input('cmdline_params', required=False)
        spec.output('results',       valid_type=Dict)
        spec.output('context',       valid_type=Dict)

    def prepare_for_submission(self, folder: Folder) -> CalcInfo:
     
        codeinfo = CodeInfo()
        codeinfo.code_uuid = self.inputs.code.uuid
        fname = splitext(self.inputs.script.filename)[0]
        pname = fname + '_parameters.json'
        cname = fname + '_context.json'
        rname = fname + '_results.json'

        codeinfo.stdout_name = fname + '.out'

        with folder.open(pname, 'w') as params_file:
            json.dump(self.inputs['parameters'].get_dict(), params_file)

        with folder.open(cname, 'w') as context_file:
            json.dump(self.inputs['context'].get_dict(), context_file)

        with folder.open(self.inputs.script.filename, 'w') as script_file:
            script_file.write(self.inputs.script.get_content())

        if 'cmdline_params' in self.inputs:
            codeinfo.cmdline_params = [self.inputs.script.filename, pname, cname, rname] + self.inputs.cmdline_params
        else:
            codeinfo.cmdline_params = [self.inputs.script.filename, pname, cname, rname]

        calcinfo = CalcInfo()
        calcinfo.codes_info = [codeinfo]
        calcinfo.retrieve_list = [codeinfo.stdout_name, cname, rname]

        return calcinfo

    def parse(self, folder):
        output_folder = self.node.outputs.retrieved

        fname = splitext(self.inputs.script.filename)[0]
        cname = fname + '_context.json'
        rname = fname + '_results.json'
        try:
            with output_folder.open(rname, 'r') as handle:
                result = json.load(handle)
                self.out('results', Dict(dict=result))
        except (OSError, IOError):
            return self.exit_codes.ERROR_READING_OUTPUT_FILE

        if result is None:
            return self.exit_codes.ERROR_INVALID_OUTPUT

        with output_folder.open(cname, 'r') as context_file:
            self.out('context', Dict(dict=json.load(context_file)))
            
        return ExitCode(0)

