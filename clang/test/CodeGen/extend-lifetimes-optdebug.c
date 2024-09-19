// RUN: %clang_cc1 %s -emit-llvm -O2 -fextend-lifetimes -o - | FileCheck %s
// RUN: %clang_cc1 %s -emit-llvm -O0 -fextend-lifetimes -o - | not FileCheck %s

// Checks that we emit the function attribute optdebug when -fextend-lifetimes
// is on and optimizations are enabled, and that it does not when optimizations
// are disabled.

// CHECK: attributes #0 = {{{.*}}optdebug

void foo() {}
