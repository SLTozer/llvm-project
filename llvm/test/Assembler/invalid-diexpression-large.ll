; RUN: not llvm-as < %s -disable-output 2>&1 | FileCheck %s

; CHECK-NOT: error:
!named1 = !{ !DIExpression(18446744073709551615) }

; CHECK: <stdin>:[[@LINE+1]]:28: error: element too large, limit is 18446744073709551615
!named2 = !{ !DIExpression(18446744073709551616) }
