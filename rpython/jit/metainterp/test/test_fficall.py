import py
from _pytest.monkeypatch import monkeypatch
import ctypes, math
from rpython.rtyper.lltypesystem import lltype, rffi
from rpython.rtyper.annlowlevel import llhelper
from rpython.jit.metainterp.test.support import LLJitMixin
from rpython.rlib import jit
from rpython.rlib import jit_libffi
from rpython.rlib.jit_libffi import (types, CIF_DESCRIPTION, FFI_TYPE_PP,
                                     jit_ffi_call, jit_ffi_save_result)
from rpython.rlib.unroll import unrolling_iterable
from rpython.rlib.rarithmetic import intmask

def get_description(atypes, rtype):
    p = lltype.malloc(CIF_DESCRIPTION, len(atypes),
                      flavor='raw', immortal=True)
    p.abi = 42
    p.nargs = len(atypes)
    p.rtype = rtype
    p.atypes = lltype.malloc(FFI_TYPE_PP.TO, len(atypes),
                             flavor='raw', immortal=True)
    for i in range(len(atypes)):
        p.atypes[i] = atypes[i]
    return p

class FakeFFI(object):
    """
    Context manager to monkey patch jit_libffi with our custom "libffi-like"
    function
    """
    
    def __init__(self, fake_call_impl_any):
        self.fake_call_impl_any = fake_call_impl_any
        self.monkey = monkeypatch()
        
    def __enter__(self, *args):
        self.monkey.setattr(jit_libffi, 'jit_ffi_call_impl_any', self.fake_call_impl_any)

    def __exit__(self, *args):
        self.monkey.undo()


class FfiCallTests(object):

    def _run(self, atypes, rtype, avalues, rvalue):
        cif_description = get_description(atypes, rtype)

        def verify(*args):
            assert args == tuple(avalues)
            return rvalue
        FUNC = lltype.FuncType([lltype.typeOf(avalue) for avalue in avalues],
                               lltype.typeOf(rvalue))
        func = lltype.functionptr(FUNC, 'verify', _callable=verify)
        func_addr = rffi.cast(rffi.VOIDP, func)

        for i in range(len(avalues)):
            cif_description.exchange_args[i] = (i+1) * 16
        cif_description.exchange_result = (len(avalues)+1) * 16

        unroll_avalues = unrolling_iterable(avalues)

        def fake_call_impl_any(cif_description, func_addr, exchange_buffer):
            ofs = 16
            for avalue in unroll_avalues:
                TYPE = rffi.CArray(lltype.typeOf(avalue))
                data = rffi.ptradd(exchange_buffer, ofs)
                assert rffi.cast(lltype.Ptr(TYPE), data)[0] == avalue
                ofs += 16
            if rvalue is not None:
                write_rvalue = rvalue
            else:
                write_rvalue = 12923  # ignored
            TYPE = rffi.CArray(lltype.typeOf(write_rvalue))
            data = rffi.ptradd(exchange_buffer, ofs)
            rffi.cast(lltype.Ptr(TYPE), data)[0] = write_rvalue

        def f():
            exbuf = lltype.malloc(rffi.CCHARP.TO, (len(avalues)+2) * 16,
                                  flavor='raw', zero=True)
            ofs = 16
            for avalue in unroll_avalues:
                TYPE = rffi.CArray(lltype.typeOf(avalue))
                data = rffi.ptradd(exbuf, ofs)
                rffi.cast(lltype.Ptr(TYPE), data)[0] = avalue
                ofs += 16

            jit_ffi_call(cif_description, func_addr, exbuf)

            if rvalue is None:
                res = 654321
            else:
                TYPE = rffi.CArray(lltype.typeOf(rvalue))
                data = rffi.ptradd(exbuf, ofs)
                res = rffi.cast(lltype.Ptr(TYPE), data)[0]
            lltype.free(exbuf, flavor='raw')
            return res

        with FakeFFI(fake_call_impl_any):
            res = f()
            assert res == rvalue or (res, rvalue) == (654321, None)
            res = self.interp_operations(f, [])
            assert res == rvalue or (res, rvalue) == (654321, None)
            self.check_operations_history(call_may_force=0,
                                          call_release_gil=1)

    def test_simple_call_int(self):
        self._run([types.signed] * 2, types.signed, [456, 789], -42)

    def test_many_arguments(self):
        for i in [0, 6, 20]:
            self._run([types.signed] * i, types.signed,
                      [-123456*j for j in range(i)],
                      -42434445)

    def test_simple_call_float(self):
        self._run([types.double] * 2, types.double, [45.6, 78.9], -4.2)

    def test_returns_none(self):
        self._run([types.signed] * 2, types.void, [456, 789], None)

    def test_returns_signedchar(self):
        self._run([types.signed], types.sint8, [456],
                  rffi.cast(rffi.SIGNEDCHAR, -42))


    def test_guard_not_forced_fails(self):
        FUNC = lltype.FuncType([lltype.Signed], lltype.Signed)

        cif_description = get_description([types.slong], types.slong)
        cif_description.exchange_args[0] = 16
        cif_description.exchange_result = 32

        ARRAY = lltype.Ptr(rffi.CArray(lltype.Signed))

        @jit.dont_look_inside
        def fn(n):
            if n >= 50:
                exctx.m = exctx.topframeref().n # forces the frame
            return n*2

        # this function simulates what a real libffi_call does: reading from
        # the buffer, calling a function (which can potentially call callbacks
        # and force frames) and write back to the buffer
        def fake_call_impl_any(cif_description, func_addr, exchange_buffer):
            # read the args from the buffer
            data_in = rffi.ptradd(exchange_buffer, 16)
            n = rffi.cast(ARRAY, data_in)[0]
            #
            # logic of the function
            func_ptr = rffi.cast(lltype.Ptr(FUNC), func_addr)
            n = func_ptr(n)
            #
            # write the result to the buffer
            data_out = rffi.ptradd(exchange_buffer, 32)
            rffi.cast(ARRAY, data_out)[0] = n

        def do_call(n):
            func_ptr = llhelper(lltype.Ptr(FUNC), fn)
            exbuf = lltype.malloc(rffi.CCHARP.TO, 48, flavor='raw', zero=True)
            data_in = rffi.ptradd(exbuf, 16)
            rffi.cast(ARRAY, data_in)[0] = n
            jit_ffi_call(cif_description, func_ptr, exbuf)
            data_out = rffi.ptradd(exbuf, 32)
            res = rffi.cast(ARRAY, data_out)[0]
            lltype.free(exbuf, flavor='raw')
            return res

        #
        #
        class XY:
            pass
        class ExCtx:
            pass
        exctx = ExCtx()
        myjitdriver = jit.JitDriver(greens = [], reds = ['n'])
        def f():
            n = 0
            while n < 100:
                myjitdriver.jit_merge_point(n=n)
                xy = XY()
                xy.n = n
                exctx.topframeref = vref = jit.virtual_ref(xy)
                res = do_call(n) # this is equivalent of a cffi call which
                                 # sometimes forces a frame

                # when n==50, fn() will force the frame, so guard_not_forced
                # fails and we enter blackholing: this test makes sure that
                # the result of call_release_gil is kept alive before the
                # libffi_save_result, and that the corresponding box is passed
                # in the fail_args. Before the fix, the result of
                # call_release_gil was simply lost and when guard_not_forced
                # failed, and the value of "res" was unpredictable.
                # See commit b84ff38f34bd and subsequents.
                assert res == n*2
                jit.virtual_ref_finish(vref, xy)
                exctx.topframeref = jit.vref_None
                n += 1
            return n

        with FakeFFI(fake_call_impl_any):
            assert f() == 100
            res = self.meta_interp(f, [])
            assert res == 100
        

class TestFfiCall(FfiCallTests, LLJitMixin):
    def test_jit_ffi_vref(self):
        py.test.skip("unsupported so far")
        from rpython.rlib import clibffi
        from rpython.rlib.jit_libffi import jit_ffi_prep_cif, jit_ffi_call

        math_sin = intmask(ctypes.cast(ctypes.CDLL(None).sin,
                                       ctypes.c_void_p).value)
        math_sin = rffi.cast(rffi.VOIDP, math_sin)

        cd = lltype.malloc(CIF_DESCRIPTION, 1, flavor='raw')
        cd.abi = clibffi.FFI_DEFAULT_ABI
        cd.nargs = 1
        cd.rtype = clibffi.cast_type_to_ffitype(rffi.DOUBLE)
        atypes = lltype.malloc(clibffi.FFI_TYPE_PP.TO, 1, flavor='raw')
        atypes[0] = clibffi.cast_type_to_ffitype(rffi.DOUBLE)
        cd.atypes = atypes
        cd.exchange_size = 64    # 64 bytes of exchange data
        cd.exchange_result = 24
        cd.exchange_result_libffi = 24
        cd.exchange_args[0] = 16

        def f():
            #
            jit_ffi_prep_cif(cd)
            #
            assert rffi.sizeof(rffi.DOUBLE) == 8
            exb = lltype.malloc(rffi.DOUBLEP.TO, 8, flavor='raw')
            exb[2] = 1.23
            jit_ffi_call(cd, math_sin, rffi.cast(rffi.CCHARP, exb))
            res = exb[3]
            lltype.free(exb, flavor='raw')
            #
            return res
            #
        res = self.interp_operations(f, [])
        lltype.free(cd, flavor='raw')
        assert res == math.sin(1.23)

        lltype.free(atypes, flavor='raw')
