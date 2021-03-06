from rpython.jit.backend.arm.helper.assembler import count_reg_args
from rpython.jit.metainterp.history import (BoxInt, BoxPtr, BoxFloat,
                                        INT, REF, FLOAT)


def test_count_reg_args():
    assert count_reg_args([BoxPtr()]) == 1
    assert count_reg_args([BoxPtr()] * 2) == 2
    assert count_reg_args([BoxPtr()] * 3) == 3
    assert count_reg_args([BoxPtr()] * 4) == 4
    assert count_reg_args([BoxPtr()] * 5) == 4
    assert count_reg_args([BoxFloat()] * 1) == 1
    assert count_reg_args([BoxFloat()] * 2) == 2
    assert count_reg_args([BoxFloat()] * 3) == 2

    assert count_reg_args([BoxInt(), BoxInt(), BoxFloat()]) == 3
    assert count_reg_args([BoxInt(), BoxFloat(), BoxInt()]) == 2

    assert count_reg_args([BoxInt(), BoxFloat(), BoxInt()]) == 2
    assert count_reg_args([BoxInt(), BoxInt(), BoxInt(), BoxFloat()]) == 3
