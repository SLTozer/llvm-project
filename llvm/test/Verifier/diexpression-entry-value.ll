; RUN: not opt -S < %s 2>&1 | FileCheck %s

!named = !{!DIExpression(DW_OP_LLVM_entry_value, 4, DW_OP_constu, 0, DW_OP_stack_value), !DIExpression(DW_OP_constu, 0, DW_OP_LLVM_entry_value, 1, DW_OP_constu, 0), !DIExpression(DW_OP_LLVM_entry_value, 100, DW_OP_constu, 0)}
; CHECK: invalid expression
; CHECK-NEXT: !DIExpression
; CHECK: invalid expression
; CHECK-NEXT: !DIExpression
; CHECK: invalid expression
; CHECK-NEXT: !DIExpression
