// Tests that labels (!dex_label/!label) work, including across files.

// RUN: %dexter_regression_test_cxx_build %s -o %t
// RUN: %dexter_regression_test_run --binary %t -- %s | FileCheck %s

// CHECK: correct_steps: 2
// CHECK: incorrect_steps: 0

#include "Inputs/header.h"

__attribute__((noinline)) void foo(int) {}

int main() {
    int total = 1;
    foo(total); // !dex_label start_line
    for (int i = 1; i <= 5; ++i) {
        total = multiply(total, i);
        foo(total); // !dex_label loop_line
    }
    return total; // !dex_label return_line
}

/*
---
!where {file: "labels.cpp", lines: !range [!label start_line, !label return_line]}:
    !value total: [1, 2, 6, 24, 120]
    !where {lines: !label return_line}:
        !value total: 120
    !where {file: "Inputs/header.h", lines: !label return_line}:
        !value result: [1, 2, 6, 24, 120]
...
*/
