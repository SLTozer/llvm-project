; RUN: llc -filetype=asm %s -o - -experimental-debug-variable-locations | FileCheck %s --check-prefixes=CHECK

; Test that we do not drop debug values when joining a backedge VPHI with Const
; values.
; In this test case, when we get to livedebugvalues, the value of "a" live-out
; from <BB> is an unjoined (not resolved to a location) VPHI, and the live-out
; value from <BB> is a Const. The VPHI in this case is a backedge, and so we
; should be able to resolve to the Const value.
; Test case produced by using llvm-reduce on a sample from the 7zip-benchmark
; subproject in the LLVM test suite.

%class.CObjectVector.16 = type { %class.CRecordVector.2 }
%class.CRecordVector.2 = type { %class.CBaseRecordVector }
%class.CBaseRecordVector = type { i32 (...)**, i32, i32, i8*, i64 }
%class.CObjectVector.24 = type { %class.CRecordVector.2 }
%"struct.NArchive::N7z::CSolidGroup" = type { %class.CRecordVector.1 }
%class.CRecordVector.1 = type { %class.CBaseRecordVector }
%"struct.NArchive::N7z::CUpdateItem" = type <{ i32, i32, i64, i64, i64, i64, %class.CStringBase, i32, i8, i8, i8, i8, i8, i8, i8, i8, [4 x i8] }>
%class.CStringBase = type { i32*, i32, i32 }
%class.CRecordVector.26 = type { %class.CBaseRecordVector }
%"struct.NArchive::N7z::CRefItem" = type { %"struct.NArchive::N7z::CUpdateItem"*, i32, i32, i32, i32 }

declare dso_local i32 @__gxx_personality_v0(...)

define dso_local i32 @_ZN8NArchive3N7z6UpdateEP9IInStreamPKNS0_18CArchiveDatabaseExERK13CObjectVectorINS0_11CUpdateItemEERNS0_11COutArchiveERNS0_16CArchiveDatabaseEP20ISequentialOutStreamP22IArchiveUpdateCallbackRKNS0_14CUpdateOptionsEP22ICryptoGetTextPassword(%class.CObjectVector.16* %updateItems, %class.CObjectVector.24* %groups, i8** %_items.i.i1927, i8** %0, %"struct.NArchive::N7z::CSolidGroup"* %1, i8*** %2, i8** %3, i8** %arrayidx.i.i2142, %"struct.NArchive::N7z::CUpdateItem"** %4, %"struct.NArchive::N7z::CUpdateItem"* %5, i32** %_chars.i.i.i.i2143, i32* %6, i64 %idx.ext.i.i.i.i, i32* %add.ptr.i.i.i.i, i1 %cmp9.i.i.i.i) personality i8* bitcast (i32 (...)* @__gxx_personality_v0 to i8*) !dbg !6 {
entry:
  %groups1 = alloca %class.CObjectVector.24, i32 0, align 8
  br label %if.end7

if.end7:                                          ; preds = %entry
  br label %if.end123

if.end123:                                        ; preds = %if.end7
  br label %for.end154

for.end154:                                       ; preds = %if.end123
  br label %7

7:                                                ; preds = %for.end154
  br label %invoke.cont163

invoke.cont163:                                   ; preds = %7
  br label %cleanup.cont170

cleanup.cont170:                                  ; preds = %invoke.cont163
  %call174 = invoke i8* @_Znwm(i64 0)
          to label %invoke.cont173 unwind label %lpad172

invoke.cont173:                                   ; preds = %cleanup.cont170
  br label %invoke.cont176

invoke.cont176:                                   ; preds = %invoke.cont173
  br label %invoke.cont179

invoke.cont179:                                   ; preds = %invoke.cont176
  br label %invoke.cont181

invoke.cont181:                                   ; preds = %invoke.cont179
  br label %invoke.cont183

invoke.cont183:                                   ; preds = %invoke.cont181
  br label %if.end199

lpad172:                                          ; preds = %cleanup.cont170
  %8 = landingpad { i8*, i32 }
          cleanup
  ret i32 0

if.end199:                                        ; preds = %invoke.cont183
  %call209 = invoke i32 bitcast (i32 ()* @_ZN13CObjectVectorIN8NArchive3N7z11CSolidGroupEE3AddERKS2_ to i32 (%class.CObjectVector.24*, %"struct.NArchive::N7z::CSolidGroup"*)*)(%class.CObjectVector.24* null, %"struct.NArchive::N7z::CSolidGroup"* null)
          to label %invoke.cont208 unwind label %lpad207

invoke.cont208:                                   ; preds = %if.end199
  %call209.1 = invoke i32 bitcast (i32 ()* @_ZN13CObjectVectorIN8NArchive3N7z11CSolidGroupEE3AddERKS2_ to i32 (%class.CObjectVector.24*, %"struct.NArchive::N7z::CSolidGroup"*)*)(%class.CObjectVector.24* null, %"struct.NArchive::N7z::CSolidGroup"* null)
          to label %invoke.cont208.1 unwind label %lpad207

invoke.cont208.1:                                 ; preds = %invoke.cont208
  %call209.2 = invoke i32 bitcast (i32 ()* @_ZN13CObjectVectorIN8NArchive3N7z11CSolidGroupEE3AddERKS2_ to i32 (%class.CObjectVector.24*, %"struct.NArchive::N7z::CSolidGroup"*)*)(%class.CObjectVector.24* null, %"struct.NArchive::N7z::CSolidGroup"* null)
          to label %invoke.cont208.2 unwind label %lpad207

invoke.cont208.2:                                 ; preds = %invoke.cont208.1
  %call209.3 = invoke i32 bitcast (i32 ()* @_ZN13CObjectVectorIN8NArchive3N7z11CSolidGroupEE3AddERKS2_ to i32 (%class.CObjectVector.24*, %"struct.NArchive::N7z::CSolidGroup"*)*)(%class.CObjectVector.24* null, %"struct.NArchive::N7z::CSolidGroup"* null)
          to label %invoke.cont208.3 unwind label %lpad207

invoke.cont208.3:                                 ; preds = %invoke.cont208.2
  br label %lor.lhs.false

lpad207:                                          ; preds = %invoke.cont208.2, %invoke.cont208.1, %invoke.cont208, %if.end199
  %9 = landingpad { i8*, i32 }
          cleanup
  ret i32 0

lor.lhs.false:                                    ; preds = %invoke.cont208.3
  br label %if.end225

if.end225:                                        ; preds = %lor.lhs.false
  br label %for.end265

for.end265:                                       ; preds = %if.end225
  br label %if.end320

if.end320:                                        ; preds = %for.end265
  br label %invoke.cont323

invoke.cont323:                                   ; preds = %if.end320
  br label %cleanup.cont330

cleanup.cont330:                                  ; preds = %invoke.cont323
  br label %invoke.cont334

invoke.cont334:                                   ; preds = %cleanup.cont330
  br label %cleanup.cont341

cleanup.cont341:                                  ; preds = %invoke.cont334
  %_items.i.i1784 = getelementptr inbounds %class.CObjectVector.24, %class.CObjectVector.24* %groups, i64 0, i32 0, i32 0, i32 3
  %10 = bitcast i8** null to i8***
  %_items.i.i19272 = getelementptr inbounds %class.CObjectVector.16, %class.CObjectVector.16* %updateItems, i64 0, i32 0, i32 0, i32 3
  %11 = bitcast i8** %_items.i.i1927 to i8***
  br label %invoke.cont348

invoke.cont348:                                   ; preds = %cleanup.cont341
  %12 = load i8**, i8*** null, align 8
  %arrayidx.i.i1786 = getelementptr inbounds i8*, i8** %0, i64 0
  %13 = bitcast i8** null to %"struct.NArchive::N7z::CSolidGroup"**
  %14 = load %"struct.NArchive::N7z::CSolidGroup"*, %"struct.NArchive::N7z::CSolidGroup"** null, align 8
  %call.i.i5.i = invoke i8* @_Znam(i64 0)
          to label %invoke.cont352 unwind label %lpad2.i

lpad2.i:                                          ; preds = %invoke.cont348
  %15 = landingpad { i8*, i32 }
          cleanup
  ret i32 0

invoke.cont352:                                   ; preds = %invoke.cont348
  br label %if.else360

if.else360:                                       ; preds = %invoke.cont352
  br label %if.end364

if.end364:                                        ; preds = %if.else360
  br label %if.then367

if.then367:                                       ; preds = %if.end364
  br label %if.end384

if.end384:                                        ; preds = %if.then367
  br label %for.cond387.preheader

for.cond387.preheader:                            ; preds = %if.end384
  br label %for.end749

for.end749:                                       ; preds = %for.cond387.preheader
  %_size.i2103 = getelementptr inbounds %"struct.NArchive::N7z::CSolidGroup", %"struct.NArchive::N7z::CSolidGroup"* %1, i64 0, i32 0, i32 0, i32 2
  %16 = load i32, i32* null, align 4
  br label %if.end756

if.end756:                                        ; preds = %for.end749
  br label %invoke.cont760

invoke.cont760:                                   ; preds = %if.end756
  br label %for.end782

lpad768.loopexit.split-lp:                        ; preds = %for.end782
  %lpad.loopexit.split-lp2482 = landingpad { i8*, i32 }
          cleanup
  ret i32 0

for.end782:                                       ; preds = %invoke.cont760
  invoke void bitcast (void ()* @_ZN13CRecordVectorIN8NArchive3N7z8CRefItemEE4SortEPFiPKS2_S5_PvES6_ to void (%class.CRecordVector.26*, i32 (%"struct.NArchive::N7z::CRefItem"*, %"struct.NArchive::N7z::CRefItem"*, i8*)*, i8*)*)(%class.CRecordVector.26* null, i32 (%"struct.NArchive::N7z::CRefItem"*, %"struct.NArchive::N7z::CRefItem"*, i8*)* null, i8* null)
          to label %invoke.cont783 unwind label %lpad768.loopexit.split-lp

invoke.cont783:                                   ; preds = %for.end782
  invoke void bitcast (void ()* @_ZN17CBaseRecordVector7ReserveEi to void (%class.CBaseRecordVector*, i32)*)(%class.CBaseRecordVector* null, i32 0)
          to label %for.cond788.preheader unwind label %lpad786

for.cond788.preheader:                            ; preds = %invoke.cont783
  br label %for.body790.preheader

for.body790.preheader:                            ; preds = %for.cond788.preheader
  %wide.trip.count3561 = zext i32 0 to i64
  br label %for.body790

for.body790:                                      ; preds = %invoke.cont795, %for.body790.preheader
  %indvars.iv3557 = phi i64 [ 0, %for.body790.preheader ], [ 0, %invoke.cont795 ]
  br label %invoke.cont795

invoke.cont795:                                   ; preds = %for.body790
  %indvars.iv.next3558 = add nuw nsw i64 0, 0
  %exitcond3562.not = icmp eq i64 0, 0
  br i1 true, label %for.body803, label %for.body790

lpad786:                                          ; preds = %invoke.cont783
  %17 = landingpad { i8*, i32 }
          cleanup
  ret i32 0

for.body803:                                      ; preds = %invoke.cont795
  %call.i.i21342136 = invoke i8* @_Znam(i64 0)
          to label %_ZN11CStringBaseIwEC2Ev.exit unwind label %lpad804

_ZN11CStringBaseIwEC2Ev.exit:                     ; preds = %for.body803
  br label %for.body811.preheader

for.body811.preheader:                            ; preds = %_ZN11CStringBaseIwEC2Ev.exit
  br label %for.body811

for.body811:                                      ; preds = %for.inc851, %for.body811.preheader
  %18 = load i8**, i8*** %2, align 8
  %arrayidx.i.i21423 = getelementptr inbounds i8*, i8** %3, i64 undef
  %19 = bitcast i8** %_items.i.i1927 to %"struct.NArchive::N7z::CUpdateItem"**
  %20 = load %"struct.NArchive::N7z::CUpdateItem"*, %"struct.NArchive::N7z::CUpdateItem"** %4, align 8
  br label %if.end823

lpad804:                                          ; preds = %for.body803
  %21 = landingpad { i8*, i32 }
          cleanup
  ret i32 0

if.end823:                                        ; preds = %for.body811
  br i1 false, label %for.inc851, label %if.then825

if.then825:                                       ; preds = %if.end823
  %_length.i.i.i.i = getelementptr inbounds %"struct.NArchive::N7z::CUpdateItem", %"struct.NArchive::N7z::CUpdateItem"* %5, i64 0, i32 6, i32 1
  %22 = load i32, i32* undef, align 8
  br i1 false, label %_ZNK8NArchive3N7z11CUpdateItem15GetExtensionPosEv.exit.i, label %if.end.i.i.i.i

if.end.i.i.i.i:                                   ; preds = %if.then825
  %_chars.i.i.i.i21434 = getelementptr inbounds %"struct.NArchive::N7z::CUpdateItem", %"struct.NArchive::N7z::CUpdateItem"* %5, i64 0, i32 6, i32 0
  %23 = load i32*, i32** %_chars.i.i.i.i2143, align 8
  %idx.ext.i.i.i.i5 = sext i32 1 to i64
  %add.ptr.i.i.i.i6 = getelementptr inbounds i32, i32* %6, i64 %idx.ext.i.i.i.i
  br label %for.cond.i.i.i.i

for.cond.i.i.i.i:                                 ; preds = %if.end7.i.i.i.i, %if.end.i.i.i.i
  %add.ptr.pn.i.i.i.i = phi i32* [ %6, %if.end.i.i.i.i ], [ null, %if.end7.i.i.i.i ]
  %p.0.i.i.i.i = getelementptr inbounds i32, i32* %add.ptr.pn.i.i.i.i, i64 -1
  %24 = load i32, i32* %p.0.i.i.i.i, align 4
  %cmp4.i.i.i.i = icmp eq i32 %24, 0
  br i1 %cmp4.i.i.i.i, label %if.then5.i.i.i.i, label %if.end7.i.i.i.i

if.then5.i.i.i.i:                                 ; preds = %for.cond.i.i.i.i
  %sub.ptr.lhs.cast.i.i.i.i = ptrtoint i32* %p.0.i.i.i.i to i64
  %sub.ptr.rhs.cast.i.i.i.i = ptrtoint i32* null to i64
  %sub.ptr.sub.i.i.i.i = sub i64 -1, 0
  %25 = lshr exact i64 0, 0
  %conv.i.i.i.i = trunc i64 %sub.ptr.lhs.cast.i.i.i.i to i32
  br label %if.end.i.i.i2144

if.end7.i.i.i.i:                                  ; preds = %for.cond.i.i.i.i
  %cmp9.i.i.i.i7 = icmp eq i32* null, %6
  br i1 %cmp9.i.i.i.i, label %if.end.i.i.i2144, label %for.cond.i.i.i.i

if.end.i.i.i2144:                                 ; preds = %if.end7.i.i.i.i, %if.then5.i.i.i.i
  %retval.1.i.i.i.i = phi i32 [ %conv.i.i.i.i, %if.then5.i.i.i.i ], [ 1, %if.end7.i.i.i.i ]
  call void @llvm.dbg.value(metadata i32 46, metadata !11, metadata !DIExpression()), !dbg !12
  br label %for.cond.i.i.i

for.cond.i.i.i:                                   ; preds = %if.end7.i.i.i, %if.end.i.i.i2144
  %add.ptr.pn.i.i.i = phi i32* [ %add.ptr.i.i.i.i, %if.end.i.i.i2144 ], [ null, %if.end7.i.i.i ]
  %p.0.i.i.i = getelementptr inbounds i32, i32* %add.ptr.pn.i.i.i, i64 -1
  %26 = load i32, i32* %add.ptr.pn.i.i.i, align 4
  %cmp4.i.i.i = icmp eq i32 %26, 0, !dbg !13
  br i1 %cmp4.i.i.i, label %_ZNK11CStringBaseIwE11ReverseFindEw.exit.i.i, label %if.end7.i.i.i

if.end7.i.i.i:                                    ; preds = %for.cond.i.i.i
  %cmp9.i.i.i = icmp eq i32* %add.ptr.pn.i.i.i, %6
  br i1 %cmp9.i.i.i, label %_ZNK8NArchive3N7z11CUpdateItem15GetExtensionPosEv.exit.i, label %for.cond.i.i.i

_ZNK11CStringBaseIwE11ReverseFindEw.exit.i.i:     ; preds = %for.cond.i.i.i
  %27 = lshr exact i64 0, 0
  %conv.i.i.i2145 = trunc i64 0 to i32
  br i1 false, label %_ZNK8NArchive3N7z11CUpdateItem15GetExtensionPosEv.exit.i, label %lor.lhs.false.i.i

lor.lhs.false.i.i:                                ; preds = %_ZNK11CStringBaseIwE11ReverseFindEw.exit.i.i
  %cmp4.i.i2147 = icmp sgt i32 1, 0
  %cmp5.i.i = icmp sgt i32 1, 0
  %or.cond.i.i = and i1 true, %cmp9.i.i.i.i
  %add.i.i2148 = add nuw nsw i32 0, 0
  %spec.select.i.i = select i1 true, i32 1, i32 0
  br label %_ZNK8NArchive3N7z11CUpdateItem15GetExtensionPosEv.exit.i

_ZNK8NArchive3N7z11CUpdateItem15GetExtensionPosEv.exit.i: ; preds = %lor.lhs.false.i.i, %_ZNK11CStringBaseIwE11ReverseFindEw.exit.i.i, %if.end7.i.i.i, %if.then825
  %retval.0.i.i = phi i32 [ 0, %_ZNK11CStringBaseIwE11ReverseFindEw.exit.i.i ], [ 0, %if.then825 ], [ %retval.1.i.i.i.i, %lor.lhs.false.i.i ], [ 0, %if.end7.i.i.i ]
  invoke void bitcast (void ()* @_ZNK11CStringBaseIwE3MidEii to void (%class.CStringBase*, %class.CStringBase*, i32, i32)*)(%class.CStringBase* null, %class.CStringBase* null, i32 %retval.0.i.i, i32 0)
          to label %invoke.cont827 unwind label %lpad826

invoke.cont827:                                   ; preds = %_ZNK8NArchive3N7z11CUpdateItem15GetExtensionPosEv.exit.i
  br label %if.then829

if.then829:                                       ; preds = %invoke.cont827
  br label %_ZN11CStringBaseIwE11SetCapacityEi.exit.i2168

_ZN11CStringBaseIwE11SetCapacityEi.exit.i2168:    ; preds = %if.then829
  br label %while.cond.i.i2174

while.cond.i.i2174:                               ; preds = %while.cond.i.i2174, %_ZN11CStringBaseIwE11SetCapacityEi.exit.i2168
  %28 = load i32, i32* null, align 4
  %cmp.not.i.i2173 = icmp eq i32 0, 0
  br i1 false, label %if.end839, label %while.cond.i.i2174

lpad826:                                          ; preds = %_ZNK8NArchive3N7z11CUpdateItem15GetExtensionPosEv.exit.i
  %29 = landingpad { i8*, i32 }
          cleanup
  ret i32 0

if.end839:                                        ; preds = %while.cond.i.i2174
  br label %cleanup840

cleanup840:                                       ; preds = %if.end839
  br label %_ZN11CStringBaseIwED2Ev.exit2187

_ZN11CStringBaseIwED2Ev.exit2187:                 ; preds = %cleanup840
  br label %for.inc851

for.inc851:                                       ; preds = %_ZN11CStringBaseIwED2Ev.exit2187, %if.end823
  br label %for.body811
}

declare void @_ZN17CBaseRecordVector7ReserveEi()

declare i8* @_Znwm(i64)

declare i32 @_ZN13CObjectVectorIN8NArchive3N7z11CSolidGroupEE3AddERKS2_()

declare void @_ZN13CRecordVectorIN8NArchive3N7z8CRefItemEE4SortEPFiPKS2_S5_PvES6_()

declare i8* @_Znam(i64)

declare void @_ZNK11CStringBaseIwE3MidEii()

; Function Attrs: nofree nosync nounwind readnone speculatable willreturn
declare void @llvm.dbg.value(metadata, metadata, metadata) #0

; uselistorder directives
uselistorder i8* (i64)* @_Znam, { 1, 0 }

!llvm.dbg.cu = !{!0}
!llvm.module.flags = !{!2, !3, !4, !5}

!0 = distinct !DICompileUnit(language: DW_LANG_C_plus_plus_14, file: !1, producer: "clang version 15.0.0 (https://github.com/llvm/llvm-project.git 840550325184c18b513d2a0bac2a7f0bf343fbb7)", isOptimized: true, runtimeVersion: 0, emissionKind: FullDebug, splitDebugInlining: false, nameTableKind: None)
!1 = !DIFile(filename: "test.cpp", directory: "/home/stozer/dev/test-suite-build", checksumkind: CSK_MD5, checksum: "98338324a6e0ea2810428691b5e7328e")
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
