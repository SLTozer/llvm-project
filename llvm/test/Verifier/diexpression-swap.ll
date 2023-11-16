; RUN: not opt -S < %s 2>&1 | FileCheck %s

!named = !{!DIExpression(DW_OP_swap)}
; CHECK: invalid expression
