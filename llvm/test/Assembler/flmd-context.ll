;; Basic test that we can parse and print the contents of an
;; MDFunctionLocalContext.
; RUN: opt < %s -S | FileCheck %s
; RUN: opt < %s -S | opt -S | FileCheck %s

; CHECK: define i32 @foo
; CHECK-SAME: !dbg ![[FOO_SP:[0-9]+]] !flmd ![[FOO_CTX:[0-9]+]]
; CHECK: define i32 @baz
; CHECK-SAME: !flmd ![[BAZ_CTX:[0-9]+]]

; CHECK: ![[FOO_SP]] = distinct !DISubprogram(name: "foo",
; CHECK: ![[FOO_CTX]] = distinct !MDFunctionLocalContext(scopes: [
; CHECK-NEXT:   !!scope(scope: ![[FOO_SP]])
; CHECK-NEXT: ], srcLocs: [
; CHECK-NEXT:   !!srcLoc(line: 0, scope: 0),
; CHECK-NEXT:   !!srcLoc(line: 2, scope: 0),
; CHECK-NEXT:   !!srcLoc(line: 3, scope: 0)
; CHECK-NEXT: ], inlinedCalls: [
; CHECK-NEXT:   !!inlinedCall(srcLoc: 2, inlineeContext: ![[BAR_CTX:[0-9]+]]),
; CHECK-NEXT:   !!inlinedCall(srcLoc: 4, inlinedAt: 0, uniquable: true, inlineeContext: ![[BAR_CTX]])
; CHECK-NEXT: ])
; CHECK: ![[BAR_CTX]] = distinct !MDFunctionLocalContext(scopes: [
; CHECK-NEXT:   !!scope(scope: ![[BAR_SP:[0-9]+]]),
; CHECK-NEXT:   !!scope(scope: ![[BAR_LB:[0-9]+]])
; CHECK-NEXT: ], srcLocs: [
; CHECK-NEXT:   !!srcLoc(line: 0, scope: 0),
; CHECK-NEXT:   !!srcLoc(line: 12, scope: 0),
; CHECK-NEXT:   !!srcLoc(line: 13, scope: 0),
; CHECK-NEXT:   !!srcLoc(line: 14, column: 7, scope: 1),
; CHECK-NEXT:   !!srcLoc(line: 15, scope: 1),
; CHECK-NEXT:   !!srcLoc(line: 16, column: 12, scope: 0)
; CHECK-NEXT: ])
; CHECK: ![[BAR_SP]] = distinct !DISubprogram(name: "bar",
; CHECK: ![[BAR_LB]] = distinct !DILexicalBlock(scope: ![[BAR_SP]]
; CHECK: ![[BAZ_CTX]] = distinct !MDFunctionLocalContext(nonDebug: true, inlinedCalls: [
; CHECK-NEXT:   !!inlinedCall(inlineeContext: ![[FOO_CTX]]),
; CHECK-NEXT:   !!inlinedCall(srcLoc: 2, inlinedAt: 0, inlineeContext: ![[BAR_CTX]])
; CHECK-NEXT: ])

define i32 @foo(i32 %i) !dbg !9 !flmd !11 {
entry:
  ret i32 %i
}

define i32 @baz(i32 %i) !flmd !16 {
entry:
  ret i32 %i
}

!llvm.dbg.cu = !{!0}
!llvm.module.flags = !{!2, !3, !4, !5, !6, !7}
!llvm.ident = !{!8}

!0 = distinct !DICompileUnit(language: DW_LANG_C11, file: !1, producer: "clang version 24.0.0", isOptimized: false, runtimeVersion: 0, emissionKind: LineTablesOnly, splitDebugInlining: false, nameTableKind: None)
!1 = !DIFile(filename: "test.c", directory: "/")
!2 = !{i32 7, !"Dwarf Version", i32 5}
!3 = !{i32 2, !"Debug Info Version", i32 3}
!4 = !{i32 8, !"PIC Level", i32 2}
!5 = !{i32 7, !"PIE Level", i32 2}
!6 = !{i32 7, !"uwtable", i32 2}
!7 = !{i32 7, !"frame-pointer", i32 2}
!8 = !{!"clang version 24.0.0git"}
!9 = distinct !DISubprogram(name: "foo", scope: !1, file: !1, line: 2, type: !10, scopeLine: 2, flags: DIFlagPrototyped, spFlags: DISPFlagDefinition, unit: !0)
!10 = !DISubroutineType(types: !15)
!11 = distinct !MDFunctionLocalContext(scopes: [
  !!scope(scope: !9)
], srcLocs: [
  !!srcLoc(line: 0, scope: 0),
  !!srcLoc(line: 2, scope: 0),
  !!srcLoc(line: 3, scope: 0)
], inlinedCalls: [
    !!inlinedCall(srcLoc: 2, inlineeContext: !13),
    !!inlinedCall(srcLoc: 4, inlinedAt: 0, uniquable: true, inlineeContext: !13),
])
!12 = distinct !DISubprogram(name: "bar", scope: !1, file: !1, line: 12, type: !10, scopeLine: 2, flags: DIFlagPrototyped, spFlags: DISPFlagDefinition, unit: !0)
!13 = distinct !MDFunctionLocalContext(scopes: [
  !!scope(scope: !12),
  !!scope(scope: !14)
], srcLocs: [
  !!srcLoc(line: 0, scope: 0),
  !!srcLoc(line: 12, scope: 0),
  !!srcLoc(line: 13, scope: 0),
  !!srcLoc(line: 14, column: 7, scope: 1),
  !!srcLoc(line: 15, scope: 1),
  !!srcLoc(line: 16, column: 12, scope: 0),
])
!14 = distinct !DILexicalBlock(scope: !12, file: !1, line: 13)
!15 = !{}
!16 = distinct !MDFunctionLocalContext(nonDebug: true, inlinedCalls: [
    !!inlinedCall(inlineeContext: !11),
    !!inlinedCall(srcLoc: 2, inlinedAt: 0, inlineeContext: !13),
])