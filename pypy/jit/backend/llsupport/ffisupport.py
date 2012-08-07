from pypy.rlib.rarithmetic import intmask
from pypy.rlib.objectmodel import specialize
from pypy.rpython.lltypesystem import lltype, rffi
from pypy.jit.backend.llsupport.descr import CallDescr

class UnsupportedKind(Exception):
    pass

def get_call_descr_dynamic(cpu, cif_description, extrainfo):
    """Get a call descr from the given CIF_DESCRIPTION"""
    ffi_result = cif_description.rtype
    try:
        reskind = get_ffi_type_kind(cpu, ffi_result)
        argkinds = [get_ffi_type_kind(cpu, cif_description.atypes[i])
                    for i in range(cif_description.nargs)]
    except UnsupportedKind:
        return None
    if reskind == 'v':
        result_size = 0
    else:
        result_size = intmask(ffi_result.c_size)
    argkinds = ''.join(argkinds)
    return CallDescr(argkinds, reskind, is_ffi_type_signed(ffi_result),
                     result_size, extrainfo, ffi_flags=cif_description.abi)

def get_ffi_type_kind(cpu, ffi_type):
    from pypy.rlib.jit_libffi import types
    kind = types.getkind(ffi_type)
    if ((not cpu.supports_floats and kind == 'f') or
        (not cpu.supports_longlong and kind == 'L') or
        (not cpu.supports_singlefloats and kind == 'S') or
        kind == '*'):
        raise UnsupportedKind("Unsupported kind '%s'" % kind)
    if kind == 'u':
        kind = 'i'
    return kind

def is_ffi_type_signed(ffi_type):
    from pypy.rlib.jit_libffi import types
    kind = types.getkind(ffi_type)
    return kind != 'u'

@specialize.memo()
def _get_ffi2descr_dict(cpu):
    d = {('v', 0): ('v', None)}
    if cpu.supports_floats:
        d[('f', 0)] = ('f', cpu.arraydescrof(rffi.CArray(lltype.Float)))
    if cpu.supports_singlefloats:
        d[('S', 0)] = ('i', cpu.arraydescrof(rffi.CArray(lltype.SingleFloat)))
    for SIGNED_TYPE in [rffi.SIGNEDCHAR,
                        rffi.SHORT,
                        rffi.INT,
                        rffi.LONG,
                        rffi.LONGLONG]:
        key = ('i', rffi.sizeof(SIGNED_TYPE))
        kind = 'i'
        if key[1] > rffi.sizeof(lltype.Signed):
            if not cpu.supports_longlong:
                continue
            key = ('L', 0)
            kind = 'f'
        d[key] = (kind, cpu.arraydescrof(rffi.CArray(SIGNED_TYPE)))
    for UNSIGNED_TYPE in [rffi.UCHAR,
                          rffi.USHORT,
                          rffi.UINT,
                          rffi.ULONG,
                          rffi.ULONGLONG]:
        key = ('u', rffi.sizeof(UNSIGNED_TYPE))
        if key[1] > rffi.sizeof(lltype.Signed):
            continue
        d[key] = ('i', cpu.arraydescrof(rffi.CArray(UNSIGNED_TYPE)))
    return d

def get_arg_descr(cpu, ffi_type):
    from pypy.rlib.jit_libffi import types
    kind = types.getkind(ffi_type)
    if kind == 'i' or kind == 'u':
        size = rffi.getintfield(ffi_type, 'c_size')
    else:
        size = 0
    return _get_ffi2descr_dict(cpu)[kind, size]

def calldescr_dynamic_for_tests(cpu, atypes, rtype, abiname='FFI_DEFAULT_ABI'):
    from pypy.rlib import clibffi
    from pypy.rlib.jit_libffi import CIF_DESCRIPTION, FFI_TYPE_PP
    from pypy.jit.codewriter.effectinfo import EffectInfo
    #
    p = lltype.malloc(CIF_DESCRIPTION, len(atypes),
                      flavor='raw', immortal=True)
    rffi.setintfield(p, 'abi', getattr(clibffi, abiname))
    p.nargs = len(atypes)
    p.rtype = rtype
    p.atypes = lltype.malloc(FFI_TYPE_PP.TO, len(atypes),
                             flavor='raw', immortal=True)
    for i in range(len(atypes)):
        p.atypes[i] = atypes[i]
    return cpu.calldescrof_dynamic(p, EffectInfo.MOST_GENERAL)
