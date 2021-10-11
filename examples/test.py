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
