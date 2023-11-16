; RUN: opt -S < %s 2>&1 | FileCheck %s

!named = !{!DIExpression(DW_OP_LLVM_entry_value, 1), !DIExpression(DW_OP_LLVM_entry_value, 1, DW_OP_lit0, DW_OP_plus)}
; CHECK-NOT: invalid expression
