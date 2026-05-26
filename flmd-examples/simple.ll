; ModuleID = 'simple.c'
source_filename = "simple.c"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128"
target triple = "x86_64-unknown-linux-gnu"

; Function Attrs: nounwind uwtable
define dso_local i32 @bar(i32 noundef %a, i32 noundef %b) local_unnamed_addr #0 !dbg !12 {
entry:
  %call = tail call i32 (...) @baz() #2, !dbg !15
  %mul = mul nsw i32 %call, %a, !dbg !16
  %add = add nsw i32 %mul, %b, !dbg !17
  ret i32 %add, !dbg !18
}

declare !dbg !19 i32 @baz(...) local_unnamed_addr #1

; Function Attrs: nounwind uwtable
define dso_local i32 @foo(i32 noundef %x, i32 noundef %y, i32 noundef %i) local_unnamed_addr #0 !dbg !20 {
entry:
  %cmp11 = icmp sgt i32 %i, 0, !dbg !21
  br i1 %cmp11, label %for.body, label %cleanup2, !dbg !22

for.cond:                                         ; preds = %for.body
  %inc = add nuw nsw i32 %l.014, 1, !dbg !23
  %exitcond.not = icmp eq i32 %inc, %i, !dbg !24
  br i1 %exitcond.not, label %cleanup2, label %for.body, !dbg !25, !llvm.loop !26

for.body:                                         ; preds = %entry, %for.cond
  %l.014 = phi i32 [ %inc, %for.cond ], [ 0, %entry ]
  %x.addr.013 = phi i32 [ %y.addr.012, %for.cond ], [ %x, %entry ]
  %y.addr.012 = phi i32 [ %add.i, %for.cond ], [ %y, %entry ]
  %call.i = tail call i32 (...) @baz() #2, !dbg !30
  %mul.i = mul nsw i32 %call.i, %x.addr.013, !dbg !32
  %add.i = add nsw i32 %mul.i, %y.addr.012, !dbg !33
  %rem = srem i32 %add.i, 5, !dbg !34
  %cmp1.not = icmp eq i32 %rem, 0, !dbg !35
  br i1 %cmp1.not, label %cleanup2, label %for.cond

cleanup2:                                         ; preds = %for.body, %for.cond, %entry
  %0 = phi i32 [ 0, %entry ], [ 0, %for.cond ], [ %add.i, %for.body ]
  ret i32 %0, !dbg !36
}

attributes #0 = { nounwind uwtable "min-legal-vector-width"="0" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
attributes #1 = { "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
attributes #2 = { nounwind }

!llvm.dbg.cu = !{!0}
!llvm.module.flags = !{!2, !3, !4, !5, !6}
!llvm.ident = !{!7}
!llvm.errno.tbaa = !{!8}

!0 = distinct !DICompileUnit(language: DW_LANG_C11, file: !1, producer: "clang version 23.0.0git (https://github.com/llvm/llvm-project.git 6900ebe0ff52507e63bfa9a225c6b4da015fac0b)", isOptimized: true, runtimeVersion: 0, emissionKind: LineTablesOnly, splitDebugInlining: false, nameTableKind: None)
!1 = !DIFile(filename: "simple.c", directory: "/home/gbtozers/dev/upstream-llvm", checksumkind: CSK_MD5, checksum: "dc4888d01459003cbb693fba25989fe9")
!2 = !{i32 7, !"Dwarf Version", i32 5}
!3 = !{i32 2, !"Debug Info Version", i32 3}
!4 = !{i32 8, !"PIC Level", i32 2}
!5 = !{i32 7, !"PIE Level", i32 2}
!6 = !{i32 7, !"uwtable", i32 2}
!7 = !{!"clang version 23.0.0git (https://github.com/llvm/llvm-project.git 6900ebe0ff52507e63bfa9a225c6b4da015fac0b)"}
!8 = !{!9, !9, i64 0}
!9 = !{!"int", !10, i64 0}
!10 = !{!"omnipotent char", !11, i64 0}
!11 = !{!"Simple C/C++ TBAA"}
!12 = distinct !DISubprogram(name: "bar", scope: !1, file: !1, line: 4, type: !13, scopeLine: 4, flags: DIFlagPrototyped | DIFlagAllCallsDescribed, spFlags: DISPFlagDefinition | DISPFlagOptimized, unit: !0, keyInstructions: true)
!13 = !DISubroutineType(types: !14)
!14 = !{}
!15 = !DILocation(line: 5, column: 11, scope: !12, atomGroup: 1, atomRank: 2)
!16 = !DILocation(line: 6, column: 12, scope: !12)
!17 = !DILocation(line: 6, column: 16, scope: !12, atomGroup: 3, atomRank: 2)
!18 = !DILocation(line: 6, column: 3, scope: !12, atomGroup: 3, atomRank: 1)
!19 = !DISubprogram(name: "baz", scope: !1, file: !1, line: 2, type: !13, spFlags: DISPFlagOptimized)
!20 = distinct !DISubprogram(name: "foo", scope: !1, file: !1, line: 9, type: !13, scopeLine: 9, flags: DIFlagPrototyped | DIFlagAllCallsDescribed, spFlags: DISPFlagDefinition | DISPFlagOptimized, unit: !0, keyInstructions: true)
!21 = !DILocation(line: 10, column: 21, scope: !20, atomGroup: 13, atomRank: 1)
!22 = !DILocation(line: 10, column: 3, scope: !20, atomGroup: 14, atomRank: 1)
!23 = !DILocation(line: 10, column: 26, scope: !20, atomGroup: 9, atomRank: 2)
!24 = !DILocation(line: 10, column: 21, scope: !20, atomGroup: 2, atomRank: 1)
!25 = !DILocation(line: 10, column: 3, scope: !20, atomGroup: 3, atomRank: 1)
!26 = distinct !{!26, !27, !28, !29}
!27 = !DILocation(line: 10, column: 3, scope: !20)
!28 = !DILocation(line: 16, column: 3, scope: !20)
!29 = !{!"llvm.loop.mustprogress"}
!30 = !DILocation(line: 5, column: 11, scope: !12, inlinedAt: !31, atomGroup: 1, atomRank: 2)
!31 = distinct !DILocation(line: 11, column: 16, scope: !20)
!32 = !DILocation(line: 6, column: 12, scope: !12, inlinedAt: !31)
!33 = !DILocation(line: 6, column: 16, scope: !12, inlinedAt: !31, atomGroup: 3, atomRank: 2)
!34 = !DILocation(line: 12, column: 14, scope: !20)
!35 = !DILocation(line: 12, column: 18, scope: !20, atomGroup: 5, atomRank: 2)
!36 = !DILocation(line: 18, column: 1, scope: !20, atomGroup: 12, atomRank: 1)
