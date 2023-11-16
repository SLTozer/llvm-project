; RUN: not llvm-as -disable-output < %s 2>&1 | FileCheck -check-prefix VERIFY %s
; RUN: llvm-as -disable-verify < %s | llvm-dis | FileCheck -check-prefix NOVERIFY %s

; NOVERIFY: !named = !{!DIExpression(0, 1, 9, 7, 2)}
!named = !{!DIExpression(0, 1, 9, 7, 2)}

; VERIFY: assembly parsed, but does not verify
