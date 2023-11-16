; RUN: llvm-as < %s | llvm-dis | llvm-as | llvm-dis | FileCheck %s
; RUN: verify-uselistorder %s

; CHECK: !named = !{
; CHECK-SAME: !DIExpression(),
; CHECK-SAME: !DIExpression(DW_OP_deref),
; CHECK-SAME: !DIExpression(DW_OP_constu, 3, DW_OP_plus),
; CHECK-SAME: !DIExpression(DW_OP_LLVM_fragment, 3, 7),
; CHECK-SAME: !DIExpression(DW_OP_deref, DW_OP_plus_uconst, 3, DW_OP_LLVM_fragment, 3, 7),
; CHECK-SAME: !DIExpression(DW_OP_constu, 2, DW_OP_swap, DW_OP_xderef),
; CHECK-SAME: !DIExpression(DW_OP_plus_uconst, 3)
; CHECK-SAME: !DIExpression(DW_OP_LLVM_convert, 16, DW_ATE_unsigned, DW_OP_LLVM_convert, 32, DW_ATE_signed)
; CHECK-SAME: !DIExpression(DW_OP_LLVM_tag_offset, 1)}

!named = !{!DIExpression(), !DIExpression(DW_OP_deref), !DIExpression(DW_OP_constu, 3, DW_OP_plus), !DIExpression(DW_OP_LLVM_fragment, 3, 7), !DIExpression(DW_OP_deref, DW_OP_plus_uconst, 3, DW_OP_LLVM_fragment, 3, 7), !DIExpression(DW_OP_constu, 2, DW_OP_swap, DW_OP_xderef), !DIExpression(DW_OP_plus_uconst, 3), !DIExpression(DW_OP_LLVM_convert, 16, DW_ATE_unsigned, DW_OP_LLVM_convert, 32, DW_ATE_signed), !DIExpression(DW_OP_LLVM_tag_offset, 1)}

