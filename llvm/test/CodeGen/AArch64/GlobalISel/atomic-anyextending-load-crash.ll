; NOTE: Assertions have been autogenerated by utils/update_llc_test_checks.py UTC_ARGS: --version 4
; RUN: llc -global-isel -global-isel-abort=1 -O0 -o - %s | FileCheck %s
target datalayout = "e-m:o-i64:64-i128:128-n32:64-S128"
target triple = "arm64e-apple-macosx14.0.0"

define void @test(ptr %0) {
; CHECK-LABEL: test:
; CHECK:       ; %bb.0: ; %entry
; CHECK-NEXT:    sub sp, sp, #144
; CHECK-NEXT:    stp x29, x30, [sp, #128] ; 16-byte Folded Spill
; CHECK-NEXT:    .cfi_def_cfa_offset 144
; CHECK-NEXT:    .cfi_offset w30, -8
; CHECK-NEXT:    .cfi_offset w29, -16
; CHECK-NEXT:    ldar w8, [x0]
; CHECK-NEXT:    str w8, [sp, #116] ; 4-byte Folded Spill
; CHECK-NEXT:    mov x8, #0 ; =0x0
; CHECK-NEXT:    str x8, [sp, #120] ; 8-byte Folded Spill
; CHECK-NEXT:    blr x8
; CHECK-NEXT:    ldr w11, [sp, #116] ; 4-byte Folded Reload
; CHECK-NEXT:    ldr x8, [sp, #120] ; 8-byte Folded Reload
; CHECK-NEXT:    mov x9, sp
; CHECK-NEXT:    str xzr, [x9]
; CHECK-NEXT:    str xzr, [x9, #8]
; CHECK-NEXT:    str xzr, [x9, #16]
; CHECK-NEXT:    str xzr, [x9, #24]
; CHECK-NEXT:    str xzr, [x9, #32]
; CHECK-NEXT:    str xzr, [x9, #40]
; CHECK-NEXT:    ; implicit-def: $x10
; CHECK-NEXT:    mov x10, x11
; CHECK-NEXT:    str x10, [x9, #48]
; CHECK-NEXT:    str xzr, [x9, #56]
; CHECK-NEXT:    str xzr, [x9, #64]
; CHECK-NEXT:    str xzr, [x9, #72]
; CHECK-NEXT:    str xzr, [x9, #80]
; CHECK-NEXT:    str xzr, [x9, #88]
; CHECK-NEXT:    str xzr, [x9, #96]
; CHECK-NEXT:    mov x0, x8
; CHECK-NEXT:    blr x8
; CHECK-NEXT:    ldp x29, x30, [sp, #128] ; 16-byte Folded Reload
; CHECK-NEXT:    add sp, sp, #144
; CHECK-NEXT:    ret
entry:
  %atomic-load = load atomic i32, ptr %0 seq_cst, align 4
  %call10 = call ptr null()
  call void (ptr, ...) null(ptr null, ptr null, i32 0, ptr null, ptr null, i32 0, i32 0, i32 %atomic-load, i32 0, i32 0, i32 0, i32 0, i64 0, ptr null)
  ret void
}
