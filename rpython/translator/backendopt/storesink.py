
from rpython.rtyper.lltypesystem.lloperation import llop
from rpython.translator.backendopt import removenoops

def has_side_effects(op):
    if op.opname == 'debug_assert':
        return False
    try:
        return getattr(llop, op.opname).sideeffects
    except AttributeError:
        return True


def storesink_graph(graph):
    added_some_same_as = False

    for block in graph.iterblocks():
        newops = []
        cache = {}

        newops, _some_same_as = _storesink_block(block, cache)
        added_some_same_as = _some_same_as or added_some_same_as
        if block.operations:
            block.operations = newops

    if added_some_same_as:
        removenoops.remove_same_as(graph)


def _storesink_block(block, cache):
    def clear_cache_for(cache, concretetype, fieldname):
        for k in cache.keys():
            if k[0].concretetype == concretetype and k[1] == fieldname:
                del cache[k]

    added_some_same_as = False
    newops = []
    for op in block.operations:
        if op.opname == 'getfield':
            tup = (op.args[0], op.args[1].value)
            res = cache.get(tup, None)
            if res is not None:
                op.opname = 'same_as'
                op.args = [res]
                added_some_same_as = True
            else:
                cache[tup] = op.result
        elif op.opname in ['setarrayitem', 'setinteriorfield']:
            pass
        elif op.opname == 'setfield':
            target = op.args[0]
            field = op.args[1].value
            clear_cache_for(cache, target.concretetype, field)
            cache[target, field] = op.args[2]
        elif has_side_effects(op):
            cache = {}
        newops.append(op)
    return newops, added_some_same_as
