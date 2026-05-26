; ModuleID = 'test.cpp'
source_filename = "test.cpp"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128"
target triple = "x86_64-unknown-linux-gnu"

@Sink = dso_local global i32 0, align 4

; Function Attrs: mustprogress nofree noinline norecurse nosync nounwind willreturn memory(none) uwtable
define dso_local noundef i32 @_Z4coldi(i32 noundef %x) local_unnamed_addr #0 !dbg !12 {
entry:
  %add.i = add nsw i32 %x, 1, !!dbgLoc(srcLoc: 0)
  %mul.i18 = mul nsw i32 %add.i, 5, !!dbgLoc(srcLoc: 0, inlinedAt: 1, atom: [1, 2])
  %0 = and i32 %x, 1, !!dbgLoc(srcLoc: 1, inlinedAt: 1, atom: [2, 2])
  %tobool.not.i20.not = icmp eq i32 %0, 0, !!dbgLoc(srcLoc: 1, inlinedAt: 1, atom: [2, 2])
  %shl.i21 = shl i32 %add.i, 2, !!dbgLoc(srcLoc: 1, inlinedAt: 1, atom: [2, 1])
  %xor.i22 = xor i32 %mul.i18, %shl.i21, !!dbgLoc(srcLoc: 1, inlinedAt: 1, atom: [2, 1])
  %shr.i23 = ashr i32 %add.i, 3, !!dbgLoc(srcLoc: 1, inlinedAt: 1, atom: [2, 1])
  %add.i24 = add nsw i32 %mul.i18, %shr.i23, !!dbgLoc(srcLoc: 1, inlinedAt: 1, atom: [2, 1])
  %a.0.i25 = select i1 %tobool.not.i20.not, i32 %xor.i22, i32 %add.i24, !!dbgLoc(srcLoc: 1, inlinedAt: 1, atom: [2, 1])
  %xor.i54 = xor i32 %a.0.i25, 7, !!dbgLoc(srcLoc: 0, inlinedAt: 2, atom: [1, 2])
  %shr.i56 = ashr i32 %xor.i54, 1, !!dbgLoc(srcLoc: 1, inlinedAt: 2)
  %xor.i66 = xor i32 %add.i, 13, !!dbgLoc(srcLoc: 0, inlinedAt: 3, atom: [1, 2])
  %shr.i68 = ashr i32 %xor.i66, 1, !!dbgLoc(srcLoc: 1, inlinedAt: 3)
  %reass.add = add i32 %xor.i54, %xor.i66, !!dbgLoc(srcLoc: 3, inlinedAt: 0, atom: [3, 2])
  %reass.mul = mul i32 %reass.add, 3, !!dbgLoc(srcLoc: 3, inlinedAt: 0, atom: [3, 2])
  %add.i69 = add nsw i32 %shr.i56, %shr.i68, !!dbgLoc(srcLoc: 2, inlinedAt: 3, atom: [2, 2])
  %add.i11 = add i32 %add.i69, %reass.mul, !!dbgLoc(srcLoc: 3, inlinedAt: 0, atom: [3, 2])
  %mul.i34 = mul nsw i32 %add.i11, 5, !!dbgLoc(srcLoc: 0, inlinedAt: 4, atom: [1, 2])
  %and.i35 = and i32 %add.i11, 1, !!dbgLoc(srcLoc: 2, inlinedAt: 4)
  %tobool.not.i36 = icmp eq i32 %and.i35, 0, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [2, 2])
  %shl.i37 = shl i32 %add.i11, 2, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [2, 1])
  %xor.i38 = xor i32 %mul.i34, %shl.i37, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [2, 1])
  %shr.i39 = ashr i32 %add.i11, 3, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [2, 1])
  %add.i40 = add nsw i32 %mul.i34, %shr.i39, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [2, 1])
  %a.0.i41 = select i1 %tobool.not.i36, i32 %add.i40, i32 %xor.i38, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [2, 1])
  %add1.i.1 = add nsw i32 %a.0.i41, 1, !!dbgLoc(srcLoc: 0)
  %mul.i34.1 = mul nsw i32 %add1.i.1, 5, !!dbgLoc(srcLoc: 0, inlinedAt: 4, atom: [11, 2])
  %1 = and i32 %a.0.i41, 1, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [12, 2])
  %tobool.not.i36.1.not = icmp eq i32 %1, 0, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [12, 2])
  %shl.i37.1 = shl i32 %add1.i.1, 2, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [12, 1])
  %xor.i38.1 = xor i32 %mul.i34.1, %shl.i37.1, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [12, 1])
  %shr.i39.1 = ashr i32 %add1.i.1, 3, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [12, 1])
  %add.i40.1 = add nsw i32 %mul.i34.1, %shr.i39.1, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [12, 1])
  %a.0.i41.1 = select i1 %tobool.not.i36.1.not, i32 %xor.i38.1, i32 %add.i40.1, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [12, 1])
  %add1.i.2 = add nsw i32 %a.0.i41.1, 2, !!dbgLoc(srcLoc: 0)
  %mul.i34.2 = mul nsw i32 %add1.i.2, 5, !!dbgLoc(srcLoc: 0, inlinedAt: 4, atom: [13, 2])
  %and.i35.2 = and i32 %a.0.i41.1, 1, !!dbgLoc(srcLoc: 2, inlinedAt: 4)
  %tobool.not.i36.2 = icmp eq i32 %and.i35.2, 0, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [14, 2])
  %shl.i37.2 = shl i32 %add1.i.2, 2, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [14, 1])
  %xor.i38.2 = xor i32 %mul.i34.2, %shl.i37.2, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [14, 1])
  %shr.i39.2 = ashr i32 %add1.i.2, 3, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [14, 1])
  %add.i40.2 = add nsw i32 %mul.i34.2, %shr.i39.2, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [14, 1])
  %a.0.i41.2 = select i1 %tobool.not.i36.2, i32 %add.i40.2, i32 %xor.i38.2, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [14, 1])
  %add1.i.3 = add nsw i32 %a.0.i41.2, 3, !!dbgLoc(srcLoc: 0)
  %mul.i34.3 = mul nsw i32 %add1.i.3, 5, !!dbgLoc(srcLoc: 0, inlinedAt: 4, atom: [15, 2])
  %and.i35.3 = and i32 %add1.i.3, 1, !!dbgLoc(srcLoc: 2, inlinedAt: 4)
  %tobool.not.i36.3 = icmp eq i32 %and.i35.3, 0, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [16, 2])
  %shl.i37.3 = shl i32 %add1.i.3, 2, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [16, 1])
  %xor.i38.3 = xor i32 %mul.i34.3, %shl.i37.3, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [16, 1])
  %shr.i39.3 = ashr i32 %add1.i.3, 3, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [16, 1])
  %add.i40.3 = add nsw i32 %mul.i34.3, %shr.i39.3, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [16, 1])
  %a.0.i41.3 = select i1 %tobool.not.i36.3, i32 %add.i40.3, i32 %xor.i38.3, !!dbgLoc(srcLoc: 1, inlinedAt: 4, atom: [16, 1])
  %mul.i = mul nsw i32 %x, 5, !!dbgLoc(srcLoc: 0, inlinedAt: 7, atom: [1, 2])
  %shr.i = ashr i32 %x, 3, !!dbgLoc(srcLoc: 1, inlinedAt: 7, atom: [2, 1])
  %add.i17 = add nsw i32 %mul.i, %shr.i, !!dbgLoc(srcLoc: 1, inlinedAt: 7, atom: [2, 1])
  %shl.i = shl i32 %x, 2, !!dbgLoc(srcLoc: 1, inlinedAt: 7, atom: [2, 1])
  %xor.i16 = xor i32 %mul.i, %shl.i, !!dbgLoc(srcLoc: 1, inlinedAt: 7, atom: [2, 1])
  %a.0.i = select i1 %tobool.not.i20.not, i32 %add.i17, i32 %xor.i16, !!dbgLoc(srcLoc: 1, inlinedAt: 7, atom: [2, 1])
  %xor.i50 = xor i32 %a.0.i, 7, !!dbgLoc(srcLoc: 0, inlinedAt: 8, atom: [1, 2])
  %shr.i52 = ashr i32 %xor.i50, 1, !!dbgLoc(srcLoc: 1, inlinedAt: 8)
  %xor.i62 = xor i32 %x, 13, !!dbgLoc(srcLoc: 0, inlinedAt: 9, atom: [1, 2])
  %shr.i64 = ashr i32 %xor.i62, 1, !!dbgLoc(srcLoc: 1, inlinedAt: 9)
  %mul.i26 = mul nsw i32 %a.0.i41.3, 5, !!dbgLoc(srcLoc: 0, inlinedAt: 11, atom: [1, 2])
  %and.i27 = and i32 %a.0.i41.3, 1, !!dbgLoc(srcLoc: 2, inlinedAt: 11)
  %tobool.not.i28 = icmp eq i32 %and.i27, 0, !!dbgLoc(srcLoc: 1, inlinedAt: 11, atom: [2, 2])
  %shl.i29 = shl i32 %a.0.i41.3, 2, !!dbgLoc(srcLoc: 1, inlinedAt: 11, atom: [2, 1])
  %xor.i30 = xor i32 %mul.i26, %shl.i29, !!dbgLoc(srcLoc: 1, inlinedAt: 11, atom: [2, 1])
  %shr.i31 = ashr i32 %a.0.i41.3, 3, !!dbgLoc(srcLoc: 1, inlinedAt: 11, atom: [2, 1])
  %add.i32 = add nsw i32 %mul.i26, %shr.i31, !!dbgLoc(srcLoc: 1, inlinedAt: 11, atom: [2, 1])
  %a.0.i33 = select i1 %tobool.not.i28, i32 %add.i32, i32 %xor.i30, !!dbgLoc(srcLoc: 1, inlinedAt: 11, atom: [2, 1])
  %xor.i58 = xor i32 %a.0.i33, 7, !!dbgLoc(srcLoc: 0, inlinedAt: 12, atom: [1, 2])
  %shr.i60 = ashr i32 %xor.i58, 1, !!dbgLoc(srcLoc: 1, inlinedAt: 12)
  %xor.i70 = xor i32 %a.0.i41.3, 13, !!dbgLoc(srcLoc: 0, inlinedAt: 13, atom: [1, 2])
  %shr.i72 = ashr i32 %xor.i70, 1, !!dbgLoc(srcLoc: 1, inlinedAt: 13)
  %reass.add74 = add i32 %xor.i58, %xor.i70, !!dbgLoc(srcLoc: 3, inlinedAt: 10, atom: [3, 2])
  %reass.mul75 = mul i32 %reass.add74, 3, !!dbgLoc(srcLoc: 3, inlinedAt: 10, atom: [3, 2])
  %add.i73 = add nsw i32 %shr.i60, %shr.i72, !!dbgLoc(srcLoc: 2, inlinedAt: 13, atom: [2, 2])
  %add.i7 = add i32 %add.i73, %reass.mul75, !!dbgLoc(srcLoc: 3, inlinedAt: 10, atom: [3, 2])
  %xor.i = xor i32 %add.i7, %a.0.i41.3, !!dbgLoc(srcLoc: 0)
  %reass.add76 = add i32 %xor.i50, %xor.i62, !!dbgLoc(srcLoc: 2, atom: [2, 2])
  %reass.mul77 = mul i32 %reass.add76, 3, !!dbgLoc(srcLoc: 2, atom: [2, 2])
  %add.i65 = sub i32 %shr.i64, %a.0.i, !!dbgLoc(srcLoc: 2, inlinedAt: 9, atom: [2, 2])
  %add.i15 = add i32 %add.i65, %shr.i52, !!dbgLoc(srcLoc: 3, inlinedAt: 6, atom: [3, 2])
  %sub.i = add i32 %add.i15, %reass.mul77, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [1, 2])
  %add = add i32 %sub.i, %xor.i, !!dbgLoc(srcLoc: 2, atom: [2, 2])
  ret i32 %add, !!dbgLoc(srcLoc: 3, atom: [2, 1])
}

; Function Attrs: mustprogress nofree norecurse nounwind memory(readwrite, argmem: none, target_mem: none) uwtable
define dso_local noundef range(i32 0, 256) i32 @main() local_unnamed_addr #1 !dbg !78 {
entry:
  br label %for.body, !!dbgLoc(srcLoc: 3, atom: [18, 1])

for.cond.cleanup:                                 ; preds = %for.body
  store volatile i32 %add2, ptr @Sink, align 4, !!dbgLoc(srcLoc: 4, atom: [8, 1]), !tbaa !8
  %and = and i32 %add2, 255, !!dbgLoc(srcLoc: 5, atom: [10, 2])
  ret i32 %and, !!dbgLoc(srcLoc: 6, atom: [10, 1])

for.body:                                         ; preds = %entry, %for.body
  %i.050 = phi i32 [ 0, %entry ], [ %add.i.i, %for.body ]
  %v.049 = phi i32 [ 0, %entry ], [ %add2, %for.body ]
  %add.i.i = add nuw nsw i32 %i.050, 1, !!dbgLoc(srcLoc: 0, inlinedAt: 0)
  %mul.i = mul nuw nsw i32 %add.i.i, 5, !!dbgLoc(srcLoc: 0, inlinedAt: 2, atom: [1, 2])
  %0 = and i32 %i.050, 1, !!dbgLoc(srcLoc: 1, inlinedAt: 2, atom: [2, 2])
  %tobool.not.i.not = icmp eq i32 %0, 0, !!dbgLoc(srcLoc: 1, inlinedAt: 2, atom: [2, 2])
  %shl.i = shl nuw nsw i32 %add.i.i, 2, !!dbgLoc(srcLoc: 1, inlinedAt: 2, atom: [2, 1])
  %xor.i = xor i32 %mul.i, %shl.i, !!dbgLoc(srcLoc: 1, inlinedAt: 2, atom: [2, 1])
  %shr.i = lshr i32 %add.i.i, 3, !!dbgLoc(srcLoc: 1, inlinedAt: 2, atom: [2, 1])
  %add.i12 = add nuw nsw i32 %mul.i, %shr.i, !!dbgLoc(srcLoc: 1, inlinedAt: 2, atom: [2, 1])
  %a.0.i = select i1 %tobool.not.i.not, i32 %xor.i, i32 %add.i12, !!dbgLoc(srcLoc: 1, inlinedAt: 2, atom: [2, 1])
  %xor.i29 = xor i32 %a.0.i, 7, !!dbgLoc(srcLoc: 0, inlinedAt: 3, atom: [1, 2])
  %shr.i31 = lshr i32 %xor.i29, 1, !!dbgLoc(srcLoc: 1, inlinedAt: 3)
  %xor.i37 = xor i32 %add.i.i, 13, !!dbgLoc(srcLoc: 0, inlinedAt: 4, atom: [1, 2])
  %shr.i39 = lshr i32 %xor.i37, 1, !!dbgLoc(srcLoc: 1, inlinedAt: 4)
  %reass.add = add nuw i32 %xor.i29, %xor.i37, !!dbgLoc(srcLoc: 3, inlinedAt: 1, atom: [3, 2])
  %reass.mul = mul i32 %reass.add, 3, !!dbgLoc(srcLoc: 3, inlinedAt: 1, atom: [3, 2])
  %add.i40 = add nuw nsw i32 %shr.i31, %shr.i39, !!dbgLoc(srcLoc: 2, inlinedAt: 4, atom: [2, 2])
  %add.i11 = add nuw nsw i32 %add.i40, %reass.mul, !!dbgLoc(srcLoc: 3, inlinedAt: 1, atom: [3, 2])
  %mul.i21 = mul nsw i32 %add.i11, 5, !!dbgLoc(srcLoc: 0, inlinedAt: 5, atom: [1, 2])
  %and.i22 = and i32 %add.i11, 1, !!dbgLoc(srcLoc: 2, inlinedAt: 5)
  %tobool.not.i23 = icmp eq i32 %and.i22, 0, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [2, 2])
  %shl.i24 = shl i32 %add.i11, 2, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [2, 1])
  %xor.i25 = xor i32 %mul.i21, %shl.i24, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [2, 1])
  %shr.i26 = ashr i32 %add.i11, 3, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [2, 1])
  %add.i27 = add nsw i32 %mul.i21, %shr.i26, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [2, 1])
  %a.0.i28 = select i1 %tobool.not.i23, i32 %add.i27, i32 %xor.i25, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [2, 1])
  %add1.i.i.1 = add nsw i32 %a.0.i28, 1, !!dbgLoc(srcLoc: 0, inlinedAt: 0)
  %mul.i21.1 = mul nsw i32 %add1.i.i.1, 5, !!dbgLoc(srcLoc: 0, inlinedAt: 5, atom: [19, 2])
  %1 = and i32 %a.0.i28, 1, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [20, 2])
  %tobool.not.i23.1.not = icmp eq i32 %1, 0, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [20, 2])
  %shl.i24.1 = shl i32 %add1.i.i.1, 2, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [20, 1])
  %xor.i25.1 = xor i32 %mul.i21.1, %shl.i24.1, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [20, 1])
  %shr.i26.1 = ashr i32 %add1.i.i.1, 3, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [20, 1])
  %add.i27.1 = add nsw i32 %mul.i21.1, %shr.i26.1, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [20, 1])
  %a.0.i28.1 = select i1 %tobool.not.i23.1.not, i32 %xor.i25.1, i32 %add.i27.1, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [20, 1])
  %add1.i.i.2 = add nsw i32 %a.0.i28.1, 2, !!dbgLoc(srcLoc: 0, inlinedAt: 0)
  %mul.i21.2 = mul nsw i32 %add1.i.i.2, 5, !!dbgLoc(srcLoc: 0, inlinedAt: 5, atom: [21, 2])
  %and.i22.2 = and i32 %a.0.i28.1, 1, !!dbgLoc(srcLoc: 2, inlinedAt: 5)
  %tobool.not.i23.2 = icmp eq i32 %and.i22.2, 0, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [22, 2])
  %shl.i24.2 = shl i32 %add1.i.i.2, 2, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [22, 1])
  %xor.i25.2 = xor i32 %mul.i21.2, %shl.i24.2, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [22, 1])
  %shr.i26.2 = ashr i32 %add1.i.i.2, 3, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [22, 1])
  %add.i27.2 = add nsw i32 %mul.i21.2, %shr.i26.2, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [22, 1])
  %a.0.i28.2 = select i1 %tobool.not.i23.2, i32 %add.i27.2, i32 %xor.i25.2, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [22, 1])
  %add1.i.i.3 = add nsw i32 %a.0.i28.2, 3, !!dbgLoc(srcLoc: 0, inlinedAt: 0)
  %mul.i21.3 = mul nsw i32 %add1.i.i.3, 5, !!dbgLoc(srcLoc: 0, inlinedAt: 5, atom: [23, 2])
  %and.i22.3 = and i32 %add1.i.i.3, 1, !!dbgLoc(srcLoc: 2, inlinedAt: 5)
  %tobool.not.i23.3 = icmp eq i32 %and.i22.3, 0, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [24, 2])
  %shl.i24.3 = shl i32 %add1.i.i.3, 2, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [24, 1])
  %xor.i25.3 = xor i32 %mul.i21.3, %shl.i24.3, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [24, 1])
  %shr.i26.3 = ashr i32 %add1.i.i.3, 3, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [24, 1])
  %add.i27.3 = add nsw i32 %mul.i21.3, %shr.i26.3, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [24, 1])
  %a.0.i28.3 = select i1 %tobool.not.i23.3, i32 %add.i27.3, i32 %xor.i25.3, !!dbgLoc(srcLoc: 1, inlinedAt: 5, atom: [24, 1])
  %mul.i13 = mul nsw i32 %a.0.i28.3, 5, !!dbgLoc(srcLoc: 0, inlinedAt: 7, atom: [1, 2])
  %and.i14 = and i32 %a.0.i28.3, 1, !!dbgLoc(srcLoc: 2, inlinedAt: 7)
  %tobool.not.i15 = icmp eq i32 %and.i14, 0, !!dbgLoc(srcLoc: 1, inlinedAt: 7, atom: [2, 2])
  %shl.i16 = shl i32 %a.0.i28.3, 2, !!dbgLoc(srcLoc: 1, inlinedAt: 7, atom: [2, 1])
  %xor.i17 = xor i32 %mul.i13, %shl.i16, !!dbgLoc(srcLoc: 1, inlinedAt: 7, atom: [2, 1])
  %shr.i18 = ashr i32 %a.0.i28.3, 3, !!dbgLoc(srcLoc: 1, inlinedAt: 7, atom: [2, 1])
  %add.i19 = add nsw i32 %mul.i13, %shr.i18, !!dbgLoc(srcLoc: 1, inlinedAt: 7, atom: [2, 1])
  %a.0.i20 = select i1 %tobool.not.i15, i32 %add.i19, i32 %xor.i17, !!dbgLoc(srcLoc: 1, inlinedAt: 7, atom: [2, 1])
  %xor.i33 = xor i32 %a.0.i20, 7, !!dbgLoc(srcLoc: 0, inlinedAt: 8, atom: [1, 2])
  %shr.i35 = ashr i32 %xor.i33, 1, !!dbgLoc(srcLoc: 1, inlinedAt: 8)
  %xor.i41 = xor i32 %a.0.i28.3, 13, !!dbgLoc(srcLoc: 0, inlinedAt: 9, atom: [1, 2])
  %shr.i43 = ashr i32 %xor.i41, 1, !!dbgLoc(srcLoc: 1, inlinedAt: 9)
  %reass.add45 = add i32 %xor.i33, %xor.i41, !!dbgLoc(srcLoc: 3, inlinedAt: 6, atom: [3, 2])
  %reass.mul46 = mul i32 %reass.add45, 3, !!dbgLoc(srcLoc: 3, inlinedAt: 6, atom: [3, 2])
  %add.i44 = add nsw i32 %shr.i35, %shr.i43, !!dbgLoc(srcLoc: 2, inlinedAt: 9, atom: [2, 2])
  %add.i = add i32 %add.i44, %reass.mul46, !!dbgLoc(srcLoc: 3, inlinedAt: 6, atom: [3, 2])
  %xor.i.i = xor i32 %add.i, %a.0.i28.3, !!dbgLoc(srcLoc: 0, inlinedAt: 0)
  %call1 = tail call noundef i32 @_Z4coldi(i32 noundef %i.050), !!dbgLoc(srcLoc: 8)
  %add = add i32 %xor.i.i, %v.049, !!dbgLoc(srcLoc: 0)
  %add2 = add i32 %add, %call1, !!dbgLoc(srcLoc: 1, atom: [5, 2])
  %exitcond.not = icmp eq i32 %add.i.i, 6, !!dbgLoc(srcLoc: 2, atom: [3, 1])
  br i1 %exitcond.not, label %for.cond.cleanup, label %for.body, !!dbgLoc(srcLoc: 3, atom: [4, 1]), !!loop 0
}


attributes #0 = { mustprogress nofree noinline norecurse nosync nounwind willreturn memory(none) uwtable "min-legal-vector-width"="0" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
attributes #1 = { mustprogress nofree norecurse nounwind memory(readwrite, argmem: none, target_mem: none) uwtable "min-legal-vector-width"="0" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }

!llvm.dbg.cu = !{!0}
!llvm.module.flags = !{!2, !3, !4, !5, !6}
!llvm.ident = !{!7}
!llvm.errno.tbaa = !{!8}

!0 = distinct !DICompileUnit(language: DW_LANG_C_plus_plus_14, file: !1, producer: "clang version 23.0.0git (https://github.com/llvm/llvm-project.git 6900ebe0ff52507e63bfa9a225c6b4da015fac0b)", isOptimized: true, runtimeVersion: 0, emissionKind: LineTablesOnly, splitDebugInlining: false, nameTableKind: None)
!1 = !DIFile(filename: "test.cpp", directory: "/home/gbtozers/dev/upstream-llvm", checksumkind: CSK_MD5, checksum: "0db23f7c0d46a39e326a4a19f3aa25b3")
!2 = !{i32 7, !"Dwarf Version", i32 5}
!3 = !{i32 2, !"Debug Info Version", i32 3}
!4 = !{i32 8, !"PIC Level", i32 2}
!5 = !{i32 7, !"PIE Level", i32 2}
!6 = !{i32 7, !"uwtable", i32 2}
!7 = !{!"clang version 23.0.0git (https://github.com/llvm/llvm-project.git 6900ebe0ff52507e63bfa9a225c6b4da015fac0b)"}
!8 = !{!9, !9, i64 0}
!9 = !{!"int", !10, i64 0}
!10 = !{!"omnipotent char", !11, i64 0}
!11 = !{!"Simple C++ TBAA"}
!12 = distinct !DISubprogram(name: "cold", scope: !1, file: !1, line: 36, type: !13, scopeLine: 36, flags: DIFlagPrototyped | DIFlagAllCallsDescribed, spFlags: DISPFlagDefinition | DISPFlagOptimized, unit: !0, keyInstructions: true, functionLocalMetadata: !136)
!13 = !DISubroutineType(types: !14)
!14 = !{}
!17 = distinct !DISubprogram(name: "leaf", scope: !1, file: !1, line: 14, type: !13, scopeLine: 14, flags: DIFlagPrototyped | DIFlagAllCallsDescribed, spFlags: DISPFlagDefinition | DISPFlagOptimized, unit: !0, keyInstructions: true, functionLocalMetadata: !138)
!19 = distinct !DISubprogram(name: "dbg_inline", scope: !1, file: !1, line: 20, type: !13, scopeLine: 20, flags: DIFlagPrototyped | DIFlagAllCallsDescribed, spFlags: DISPFlagDefinition | DISPFlagOptimized, unit: !0, keyInstructions: true, functionLocalMetadata: !137)
!24 = distinct !DISubprogram(name: "t<7>", scope: !1, file: !1, line: 12, type: !13, scopeLine: 12, flags: DIFlagPrototyped | DIFlagAllCallsDescribed, spFlags: DISPFlagDefinition | DISPFlagOptimized, unit: !0, keyInstructions: true, functionLocalMetadata: !139)
!28 = distinct !DISubprogram(name: "t<13>", scope: !1, file: !1, line: 12, type: !13, scopeLine: 12, flags: DIFlagPrototyped | DIFlagAllCallsDescribed, spFlags: DISPFlagDefinition | DISPFlagOptimized, unit: !0, keyInstructions: true, functionLocalMetadata: !140)
!50 = distinct !DISubprogram(name: "operator()", scope: !1, file: !1, line: 34, type: !13, scopeLine: 34, flags: DIFlagPrototyped | DIFlagAllCallsDescribed, spFlags: DISPFlagDefinition | DISPFlagOptimized, unit: !0, keyInstructions: true, functionLocalMetadata: !141)
!78 = distinct !DISubprogram(name: "main", scope: !1, file: !1, line: 38, type: !13, scopeLine: 38, flags: DIFlagPrototyped | DIFlagAllCallsDescribed, spFlags: DISPFlagDefinition | DISPFlagOptimized, unit: !0, keyInstructions: true, functionLocalMetadata: !142)
!84 = distinct !DISubprogram(name: "mix", scope: !1, file: !1, line: 32, type: !13, scopeLine: 32, flags: DIFlagPrototyped | DIFlagAllCallsDescribed, spFlags: DISPFlagDefinition | DISPFlagOptimized, unit: !0, keyInstructions: true, functionLocalMetadata: !143)
!135 = !{!"llvm.loop.mustprogress"}
!136 = distinct !DIFunctionLocalMetadata(
  srcLocs: [
    !!srcLoc(line: 36, column: 49, scope: !12), ; 0
    !!srcLoc(line: 36, column: 42, scope: !12), ; 1
    !!srcLoc(line: 36, column: 47, scope: !12), ; 2
    !!srcLoc(line: 36, column: 35, scope: !12) ; 3
  ],
  inlinedCallLocs: [
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 0), inlinedFLMD: !137), ; 0
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 0, inlinedAt: 0), inlinedFLMD: !138), ; 1
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 1, inlinedAt: 0), inlinedFLMD: !139), ; 2
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 2, inlinedAt: 0), inlinedFLMD: !140), ; 3
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 0), inlinedFLMD: !138), ; 4
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 1), inlinedFLMD: !141), ; 5
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 0, inlinedAt: 5), inlinedFLMD: !137), ; 6
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 0, inlinedAt: 6), inlinedFLMD: !138), ; 7
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 1, inlinedAt: 6), inlinedFLMD: !139), ; 8
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 2, inlinedAt: 6), inlinedFLMD: !140), ; 9
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 0), inlinedFLMD: !137), ; 10
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 0, inlinedAt: 10), inlinedFLMD: !138), ; 11
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 1, inlinedAt: 10), inlinedFLMD: !139), ; 12
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 2, inlinedAt: 10), inlinedFLMD: !140) ; 13
  ],
)
!137 = distinct !DIFunctionLocalMetadata(
  srcLocs: [
    !!srcLoc(line: 21, column: 11, scope: !19), ; 0
    !!srcLoc(line: 22, column: 10, scope: !19), ; 1
    !!srcLoc(line: 22, column: 20, scope: !19), ; 2
    !!srcLoc(line: 22, column: 18, scope: !19) ; 3
  ],
)
!138 = distinct !DIFunctionLocalMetadata(
  srcLocs: [
    !!srcLoc(line: 15, column: 13, scope: !17), ; 0
    !!srcLoc(line: 16, column: 7, scope: !17), ; 1
    !!srcLoc(line: 16, column: 9, scope: !17) ; 2
  ],
)
!139 = distinct !DIFunctionLocalMetadata(
  srcLocs: [
    !!srcLoc(line: 12, column: 37, scope: !24), ; 0
    !!srcLoc(line: 12, column: 61, scope: !24) ; 1
  ],
)
!140 = distinct !DIFunctionLocalMetadata(
  srcLocs: [
    !!srcLoc(line: 12, column: 37, scope: !28), ; 0
    !!srcLoc(line: 12, column: 61, scope: !28), ; 1
    !!srcLoc(line: 12, column: 56, scope: !28) ; 2
  ],
)
!141 = distinct !DIFunctionLocalMetadata(
  srcLocs: [
    !!srcLoc(line: 34, column: 54, scope: !50), ; 0
    !!srcLoc(line: 34, column: 68, scope: !50) ; 1
  ],
)
!142 = distinct !DIFunctionLocalMetadata(
  srcLocs: [
    !!srcLoc(line: 41, column: 15, scope: !78), ; 0
    !!srcLoc(line: 41, column: 7, scope: !78), ; 1
    !!srcLoc(line: 40, column: 21, scope: !78), ; 2
    !!srcLoc(line: 40, column: 3, scope: !78), ; 3
    !!srcLoc(line: 43, column: 8, scope: !78), ; 4
    !!srcLoc(line: 44, column: 12, scope: !78), ; 5
    !!srcLoc(line: 44, column: 3, scope: !78), ; 6
    !!srcLoc(line: 41, column: 10, scope: !78), ; 7
    !!srcLoc(line: 41, column: 17, scope: !78), ; 8
    !!srcLoc(line: 42, column: 3, scope: !78) ; 9
  ],
  inlinedCallLocs: [
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 7), inlinedFLMD: !143), ; 0
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 0, inlinedAt: 0), inlinedFLMD: !137), ; 1
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 0, inlinedAt: 1), inlinedFLMD: !138), ; 2
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 1, inlinedAt: 1), inlinedFLMD: !139), ; 3
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 2, inlinedAt: 1), inlinedFLMD: !140), ; 4
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 0, inlinedAt: 0), inlinedFLMD: !138), ; 5
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 0, inlinedAt: 0), inlinedFLMD: !137), ; 6
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 0, inlinedAt: 6), inlinedFLMD: !138), ; 7
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 1, inlinedAt: 6), inlinedFLMD: !139), ; 8
    !!inlinedCallLoc(dbgLoc: !!dbgLoc(srcLoc: 2, inlinedAt: 6), inlinedFLMD: !140) ; 9
  ],
  loops: [
    !!loop(start: !!dbgLoc(srcLoc: 3), end: !!dbgLoc(srcLoc: 9), properties: !135) ; 0
  ]
)
!143 = distinct !DIFunctionLocalMetadata(
  srcLocs: [
    !!srcLoc(line: 32, column: 49, scope: !84) ; 0
  ],
)
