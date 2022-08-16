; RUN: llc -filetype=asm %s -o - -experimental-debug-variable-locations | FileCheck %s --check-prefixes=CHECK

; Test that we do not drop debug values when joining a VPHI and a Def that use
; the same value.
; In this test case, when we get to livedebugvalues, the value of "a" live-out
; from if.then.i.i.i626 is a VPHI, and the live-out value from if.then3.i.i.i644
; is a Def that refers to the same value. When these two values are joined at
; MBB lpad13, we should recognize that they refer to the same value and select
; either one of them as the live-in value to propagate that value through
; lpad13.
; Test case produced by using llvm-reduce on a sample from the 7zip-benchmark
; subproject in the LLVM test suite.

; CHECK: .LBB0_9:
; CHECK-NEXT: #DEBUG_VALUE: foo:a <- $rsi

; ModuleID = 'reduced.ll'
source_filename = "reduced.ll"

declare dso_local i32 @__gxx_personality_v0(...)

define dso_local i32 @foo() personality i8* bitcast (i32 (...)* @__gxx_personality_v0 to i8*) !dbg !6 {
if.end:
  %call.i.i.i561 = call i8* undef(i64 0, i32 0)
  call void @llvm.dbg.value(metadata i8* %call.i.i.i561, metadata !11, metadata !DIExpression()), !dbg !12
  %0 = bitcast i8* %call.i.i.i561 to i32*
  br label %allocate.exit.i577

allocate.exit.i577: ; preds = %if.end
  br label %copy.exit.i590

copy.exit.i590: ; preds = %allocate.exit.i577
  br label %deallocate.exit.i599.thread

deallocate.exit.i599.thread: ; preds = %copy.exit.i590
  br label %for.body.lr.ph

for.body.lr.ph:                                   ; preds = %deallocate.exit.i599.thread
  br label %for.body

for.body:                                         ; preds = %invoke.cont14.for.body_crit_edge, %for.body.lr.ph
  %isextreme.sroa.191125.0 = phi i32* [ %0, %for.body.lr.ph ], [ %isextreme.sroa.191125.1, %invoke.cont14.for.body_crit_edge ]
  br label %invoke.cont11

invoke.cont11:                                    ; preds = %for.body
  br i1 undef, label %if.then.i620, label %invoke.cont14

if.then.i620:                                     ; preds = %invoke.cont11
  br i1 undef, label %if.then.i.i.i626, label %invoke.cont14, !dbg !13

if.then.i.i.i626:                                 ; preds = %if.then.i620
  %call.i.i.i.i655 = invoke i8* undef(i64 0, i32 0)
          to label %allocate.exit.i.i630 unwind label %lpad13

allocate.exit.i.i630: ; preds = %if.then.i.i.i626
  %1 = bitcast i8* %call.i.i.i.i655 to i32*
  call void @llvm.dbg.value(metadata i32* %isextreme.sroa.191125.0, metadata !11, metadata !DIExpression()), !dbg !13
  br label %copy.exit.i.i640

copy.exit.i.i640: ; preds = %allocate.exit.i.i630
  br i1 undef, label %invoke.cont14, label %if.then3.i.i.i644

if.then3.i.i.i644:                                ; preds = %copy.exit.i.i640
  invoke void undef(i8* null)
          to label %invoke.cont14 unwind label %lpad13

invoke.cont14:                                    ; preds = %if.then3.i.i.i644, %copy.exit.i.i640, %if.then.i620, %invoke.cont11
  %isextreme.sroa.191125.1 = phi i32* [ null, %if.then.i620 ], [ null, %invoke.cont11 ], [ %1, %if.then3.i.i.i644 ], [ %1, %copy.exit.i.i640 ]
  call void @llvm.dbg.value(metadata i32* %isextreme.sroa.191125.1, metadata !11, metadata !DIExpression()), !dbg !13
  br label %invoke.cont14.for.body_crit_edge

invoke.cont14.for.body_crit_edge:                 ; preds = %invoke.cont14
  br label %for.body

lpad13:                                           ; preds = %if.then3.i.i.i644, %if.then.i.i.i626
  %2 = landingpad { i8*, i32 }
          cleanup
  br label %ehcleanup400

ehcleanup400:                                     ; preds = %lpad13
  br label %ehcleanup405

ehcleanup405:                                     ; preds = %ehcleanup400
  %tobool.not.i.i.i1000 = icmp eq i32* %isextreme.sroa.191125.0, null
  br i1 %tobool.not.i.i.i1000, label %invoke.cont406, label %if.then3.i.i.i1004

if.then3.i.i.i1004:                               ; preds = %ehcleanup405
  %3 = bitcast i32* null to i8*
  br label %invoke.cont406

invoke.cont406:                                   ; preds = %if.then3.i.i.i1004, %ehcleanup405
  resume { i8*, i32 } zeroinitializer
}

; Function Attrs: nofree nosync nounwind readnone speculatable willreturn
declare dso_local void @llvm.dbg.value(metadata, metadata, metadata)

!llvm.dbg.cu = !{!0}
!llvm.module.flags = !{!2, !3, !4, !5}

!0 = distinct !DICompileUnit(language: DW_LANG_C_plus_plus_14, file: !1, producer: "clang version 15.0.0", isOptimized: true, runtimeVersion: 0, emissionKind: FullDebug, splitDebugInlining: false, nameTableKind: None)
!1 = !DIFile(filename: "test.cpp", directory: "/")
!2 = !{i32 7, !"Dwarf Version", i32 5}
!3 = !{i32 2, !"Debug Info Version", i32 3}
!4 = !{i32 1, !"wchar_size", i32 4}
!5 = !{i32 7, !"uwtable", i32 2}
!6 = distinct !DISubprogram(name: "foo", linkageName: "_Z3fooii", scope: !1, file: !1, line: 1, type: !7, scopeLine: 1, flags: DIFlagPrototyped | DIFlagAllCallsDescribed, spFlags: DISPFlagDefinition | DISPFlagOptimized, unit: !0, retainedNodes: !10)
!7 = !DISubroutineType(types: !8)
!8 = !{!9, !9, !9}
!9 = !DIBasicType(name: "int", size: 32, encoding: DW_ATE_signed)
!10 = !{!11}
!11 = !DILocalVariable(name: "a", arg: 1, scope: !6, file: !1, line: 1, type: !9)
!12 = !DILocation(line: 0, scope: !6)
!13 = !DILocation(line: 4, column: 10, scope: !6)
